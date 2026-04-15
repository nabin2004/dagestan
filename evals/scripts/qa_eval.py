"""
evals/scripts/qa_eval.py
========================
Question Answering evaluator for the LOCOMO benchmark.

Mirrors the five reasoning categories from Maharana et al. (2024):
  1. single_hop     — answer from a single session
  2. multi_hop      — synthesise across multiple sessions
  3. temporal       — time-aware reasoning
  4. open_domain    — external / commonsense knowledge + conversation
  5. adversarial    — unanswerable questions (model should say so)

Scoring: token-level F1 (partial match), identical to LOCOMO paper.
"""

from __future__ import annotations

import logging
import os
import re
import string
from collections import Counter, defaultdict
from typing import Any, Optional

log = logging.getLogger(__name__)

CATEGORIES = ["single_hop", "multi_hop", "temporal", "open_domain", "adversarial"]

# Prompt used to generate answers from retrieved context
QA_SYSTEM_PROMPT = """\
You are an assistant answering questions about a conversation between two people.
Use ONLY the provided context. If the question cannot be answered from the context,
say exactly: "I cannot answer this from the available information."
Replicate exact wording from the conversation where possible.
Answer concisely — one or two sentences maximum.
"""

QA_USER_TEMPLATE = """\
Context from conversation memory:
{context}

Question: {question}

Answer:"""


class QAEvaluator:
    def __init__(self, provider: str = "gemini", model: str = "gemini-1.5-flash"):
        self.provider = provider
        self.model = model
        self._client = _build_llm_client(provider, model)

    # ------------------------------------------------------------------

    def answer(self, question: str, context: str) -> str:
        """Generate an answer given retrieved context."""
        if not context.strip():
            return "I cannot answer this from the available information."
        prompt = QA_USER_TEMPLATE.format(context=context, question=question)
        try:
            return self._client.complete(system=QA_SYSTEM_PROMPT, user=prompt)
        except Exception as e:
            log.warning("LLM call failed: %s", e)
            return ""

    def score(
        self,
        predicted: str,
        ground_truth: str,
        category: str = "unknown",
    ) -> dict:
        """Compute token-level F1 and exact-match for a single QA pair."""
        f1, precision, recall = token_f1(predicted, ground_truth)

        # Special handling for adversarial — model should refuse to answer
        if category == "adversarial":
            refused = _is_refusal(predicted)
            adversarial_score = 1.0 if refused else 0.0
        else:
            adversarial_score = None

        return {
            "f1": f1,
            "precision": precision,
            "recall": recall,
            "adversarial_correct": adversarial_score,
            "category": category,
        }

    def aggregate(self, scores: list[dict]) -> dict:
        """Aggregate per-item scores into category-level and overall F1."""
        by_category: dict[str, list[float]] = defaultdict(list)
        all_f1: list[float] = []

        for s in scores:
            cat = s.get("category", "unknown")
            # For adversarial questions use the binary correct score
            if cat == "adversarial" and s.get("adversarial_correct") is not None:
                f = s["adversarial_correct"]
            else:
                f = s["f1"]
            by_category[cat].append(f)
            all_f1.append(f)

        cat_scores = {cat: _mean(vals) for cat, vals in by_category.items()}
        return {
            "overall_f1": _mean(all_f1),
            "by_category": cat_scores,
            "n_questions": len(scores),
            "per_item": scores,
        }


# ---------------------------------------------------------------------------
# Scoring utilities
# ---------------------------------------------------------------------------

def normalise_answer(s: str) -> list[str]:
    """Lowercase, strip punctuation and articles, tokenise."""
    s = s.lower()
    s = s.translate(str.maketrans("", "", string.punctuation))
    tokens = s.split()
    stopwords = {"a", "an", "the"}
    return [t for t in tokens if t not in stopwords]


def token_f1(predicted: str, ground_truth: str) -> tuple[float, float, float]:
    pred_tokens = normalise_answer(predicted)
    truth_tokens = normalise_answer(ground_truth)

    if not pred_tokens and not truth_tokens:
        return 1.0, 1.0, 1.0
    if not pred_tokens or not truth_tokens:
        return 0.0, 0.0, 0.0

    common = Counter(pred_tokens) & Counter(truth_tokens)
    num_common = sum(common.values())

    if num_common == 0:
        return 0.0, 0.0, 0.0

    precision = num_common / len(pred_tokens)
    recall = num_common / len(truth_tokens)
    f1 = 2 * precision * recall / (precision + recall)
    return f1, precision, recall


def _is_refusal(text: str) -> bool:
    """Check if model correctly refused to answer an adversarial question."""
    refusal_patterns = [
        r"cannot answer",
        r"can't answer",
        r"not mentioned",
        r"not in the",
        r"no information",
        r"unanswerable",
        r"not enough information",
        r"i don't know",
        r"unable to answer",
        r"not available",
    ]
    text_lower = text.lower()
    return any(re.search(p, text_lower) for p in refusal_patterns)


def _mean(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


# ---------------------------------------------------------------------------
# LLM client factory
# ---------------------------------------------------------------------------

def _openrouter_api_key() -> str:
    """OPENROUTER_API_KEY or OPENAI_API_KEY, loading .env if needed."""
    key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ValueError(
            "OpenRouter: set OPENROUTER_API_KEY in .env (or OPENAI_API_KEY on OpenRouter)."
        )
    return key


def _build_llm_client(provider: str, model: str) -> "_LLMClient":
    if provider == "gemini":
        return _GeminiClient(model)
    elif provider == "openai":
        return _OpenAIClient(model)
    elif provider == "openrouter":
        return _OpenRouterClient(model)
    elif provider == "anthropic":
        return _AnthropicClient(model)
    elif provider == "stub":
        return _StubClient()
    else:
        raise ValueError(f"Unknown provider: {provider}")


class _LLMClient:
    def complete(self, system: str, user: str) -> str:
        raise NotImplementedError


class _GeminiClient(_LLMClient):
    def __init__(self, model: str):
        self.model = model
        try:
            import google.generativeai as genai  # type: ignore
            genai.configure(api_key=os.environ["GEMINI_API_KEY"])
            self._genai = genai
        except ImportError:
            raise RuntimeError("pip install google-generativeai")

    def complete(self, system: str, user: str) -> str:
        m = self._genai.GenerativeModel(
            self.model,
            system_instruction=system,
        )
        resp = m.generate_content(user)
        return resp.text.strip()


class _OpenAIClient(_LLMClient):
    def __init__(self, model: str):
        self.model = model
        try:
            from openai import OpenAI  # type: ignore
        except ImportError:
            raise RuntimeError("pip install openai")
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            try:
                from dotenv import load_dotenv

                load_dotenv()
            except ImportError:
                pass
            key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError("Set OPENAI_API_KEY for provider=openai.")
        self._client = OpenAI(api_key=key)

    def complete(self, system: str, user: str) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
        )
        content = resp.choices[0].message.content or ""
        return content.strip()


class _OpenRouterClient(_LLMClient):
    """OpenAI-compatible chat API at openrouter.ai (use provider/model ids)."""

    def __init__(self, model: str):
        self.model = model
        try:
            from openai import OpenAI  # type: ignore
        except ImportError:
            raise RuntimeError("pip install openai")
        key = _openrouter_api_key()
        self._client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=key,
            default_headers={
                "HTTP-Referer": os.environ.get(
                    "OPENROUTER_HTTP_REFERER", "https://github.com/nabin/dagestan"
                ),
                "X-Title": os.environ.get("OPENROUTER_APP_TITLE", "Dagestan LOCOMO eval"),
            },
        )

    def complete(self, system: str, user: str) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
        )
        content = resp.choices[0].message.content or ""
        return content.strip()


class _AnthropicClient(_LLMClient):
    def __init__(self, model: str):
        self.model = model
        try:
            import anthropic  # type: ignore
            self._client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        except ImportError:
            raise RuntimeError("pip install anthropic")

    def complete(self, system: str, user: str) -> str:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=512,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text.strip()


class _StubClient(_LLMClient):
    """Returns empty string — used in dry runs and tests."""
    def complete(self, system: str, user: str) -> str:
        return ""
