"""
dagestan.extraction.extractor
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Converts conversation text into typed graph nodes and edges
using an LLM for structured extraction.

Supports OpenAI and Anthropic clients, or any callable that
accepts a system prompt and user prompt and returns a string.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Protocol

from ..graph.schema import Edge, EdgeType, Node, NodeType
from .prompts import EXTRACTION_SYSTEM_PROMPT, EXTRACTION_USER_TEMPLATE

logger = logging.getLogger(__name__)


# Valid type values for parsing
_NODE_TYPE_MAP: dict[str, NodeType] = {t.value: t for t in NodeType}
_EDGE_TYPE_MAP: dict[str, EdgeType] = {t.value: t for t in EdgeType}


class LLMClient(Protocol):
    """
    Minimal protocol for an LLM client.

    Any callable matching this signature works:
        (system_prompt: str, user_prompt: str) -> str
    """

    def __call__(self, system_prompt: str, user_prompt: str) -> str: ...


def _make_openai_client(
    api_key: str | None = None,
    model: str = "gpt-4o-mini",
) -> LLMClient:
    """Create a simple OpenAI-based LLM callable."""

    def call(system_prompt: str, user_prompt: str) -> str:
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError(
                "openai package required. Install with: pip install dagestan[openai]"
            )

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
        )
        return response.choices[0].message.content or ""

    return call


def _make_anthropic_client(
    api_key: str | None = None,
    model: str = "claude-sonnet-4-20250514",
) -> LLMClient:
    """Create a simple Anthropic-based LLM callable."""

    def call(system_prompt: str, user_prompt: str) -> str:
        try:
            from anthropic import Anthropic
        except ImportError:
            raise ImportError(
                "anthropic package required. Install with: pip install dagestan[anthropic]"
            )

        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text

    return call


class ConversationExtractor:
    """
    Extracts typed graph nodes and edges from conversation text.

    Uses an LLM to parse conversations into structured knowledge.
    Falls back gracefully on extraction failures — partial graph
    is always better than no graph.
    """

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        provider: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        source_tag: str = "",
    ) -> None:
        """
        Args:
            llm_client: Custom callable (system_prompt, user_prompt) -> str.
            provider: "openai" or "anthropic" — used if llm_client is None.
            api_key: API key for the provider.
            model: Model name override.
            source_tag: Tag to attach to all extracted nodes (e.g., session ID).
        """
        if llm_client is not None:
            self._llm = llm_client
        elif provider == "openai":
            self._llm = _make_openai_client(api_key=api_key, model=model or "gpt-4o-mini")
        elif provider == "anthropic":
            self._llm = _make_anthropic_client(
                api_key=api_key, model=model or "claude-sonnet-4-20250514"
            )
        else:
            raise ValueError(
                "Must provide either llm_client or provider ('openai' / 'anthropic')"
            )

        self._source_tag = source_tag

    def extract(
        self,
        conversation: str | list[dict[str, str]],
    ) -> tuple[list[Node], list[Edge]]:
        """
        Extract nodes and edges from a conversation.

        Args:
            conversation: Either a plain text string, or a list of
                          {"role": ..., "content": ...} message dicts.

        Returns:
            Tuple of (nodes, edges) extracted from the conversation.
            On failure, returns ([], []) rather than raising.
        """
        # Normalize conversation to text
        if isinstance(conversation, list):
            text = self._messages_to_text(conversation)
        else:
            text = conversation

        if not text.strip():
            return [], []

        # Call LLM for extraction
        user_prompt = EXTRACTION_USER_TEMPLATE.format(conversation_text=text)

        try:
            raw_response = self._llm(EXTRACTION_SYSTEM_PROMPT, user_prompt)
        except Exception as e:
            logger.error(f"LLM call failed during extraction: {e}")
            return [], []

        # Parse LLM response
        try:
            data = self._parse_json_response(raw_response)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse LLM extraction response: {e}")
            return [], []

        # Convert to typed objects
        return self._build_graph_objects(data)

    def _messages_to_text(self, messages: list[dict[str, str]]) -> str:
        """Convert message list to readable conversation text."""
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown").capitalize()
            content = msg.get("content", "")
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def _parse_json_response(self, response: str) -> dict[str, Any]:
        """
        Parse JSON from LLM response, handling markdown code blocks.
        """
        text = response.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last fence lines
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("Expected JSON object at top level")
        return data

    def _build_graph_objects(
        self, data: dict[str, Any]
    ) -> tuple[list[Node], list[Edge]]:
        """
        Convert raw extraction dict into typed Node and Edge objects.

        Handles partial data gracefully — skips malformed entries.
        """
        nodes: list[Node] = []
        label_to_id: dict[str, str] = {}

        # Build nodes
        for raw_node in data.get("nodes", []):
            try:
                node_type_str = raw_node.get("type", "").lower()
                if node_type_str not in _NODE_TYPE_MAP:
                    logger.debug(f"Skipping node with unknown type: {node_type_str}")
                    continue

                label = raw_node.get("label", "").strip()
                if not label:
                    continue

                node = Node(
                    type=_NODE_TYPE_MAP[node_type_str],
                    label=label,
                    attributes=raw_node.get("attributes", {}),
                    source=self._source_tag,
                )
                nodes.append(node)
                label_to_id[label] = node.id
            except Exception as e:
                logger.debug(f"Skipping malformed node: {e}")
                continue

        # Build edges
        edges: list[Edge] = []
        for raw_edge in data.get("edges", []):
            try:
                source_label = raw_edge.get("source_label", "").strip()
                target_label = raw_edge.get("target_label", "").strip()
                edge_type_str = raw_edge.get("type", "").lower()

                if edge_type_str not in _EDGE_TYPE_MAP:
                    logger.debug(f"Skipping edge with unknown type: {edge_type_str}")
                    continue

                source_id = label_to_id.get(source_label)
                target_id = label_to_id.get(target_label)

                if source_id is None or target_id is None:
                    logger.debug(
                        f"Skipping edge: missing node for "
                        f"{source_label!r} -> {target_label!r}"
                    )
                    continue

                edge = Edge(
                    source_id=source_id,
                    target_id=target_id,
                    type=_EDGE_TYPE_MAP[edge_type_str],
                )
                edges.append(edge)
            except Exception as e:
                logger.debug(f"Skipping malformed edge: {e}")
                continue

        return nodes, edges
