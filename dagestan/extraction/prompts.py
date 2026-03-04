"""
dagestan.extraction.prompts
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Prompt templates for LLM-based knowledge extraction.

The extraction prompt asks the LLM to parse conversation text into
structured JSON representing typed graph nodes and edges.
"""

EXTRACTION_SYSTEM_PROMPT = """\
You are a knowledge extraction engine. Your job is to read conversation text \
and extract structured knowledge as a JSON object.

You must extract:
1. **Entities** — people, places, objects, systems mentioned
2. **Concepts** — ideas, topics, domains discussed
3. **Events** — things that happened or were decided
4. **Preferences** — likes, dislikes, values expressed by any entity
5. **Goals** — what someone wants to do or achieve

For each extracted item, also extract **relationships** between them.

RESPOND WITH ONLY valid JSON matching this exact schema — no markdown, no explanation:

{
  "nodes": [
    {
      "type": "entity" | "concept" | "event" | "preference" | "goal",
      "label": "short descriptive name",
      "attributes": {"key": "value"}
    }
  ],
  "edges": [
    {
      "source_label": "label of source node",
      "target_label": "label of target node",
      "type": "relates_to" | "caused" | "contradicts" | "happened_before" | "has_preference" | "wants"
    }
  ]
}

Rules:
- Use lowercase for all type values.
- The "label" field should be concise but specific (e.g., "User" not "the user").
- source_label and target_label must exactly match a node label in the nodes list.
- Extract only what is explicitly stated or strongly implied. Do not hallucinate.
- If the conversation is empty or trivial, return {"nodes": [], "edges": []}.
- Keep labels deduplicated — don't create two nodes for the same thing.
"""

EXTRACTION_USER_TEMPLATE = """\
Extract structured knowledge from this conversation:

---
{conversation_text}
---

Return ONLY the JSON object. No other text.
"""


CONTRADICTION_RESOLUTION_SYSTEM_PROMPT = """\
You are a knowledge curator. You are given two pieces of knowledge about the \
same entity that appear to contradict each other, along with their timestamps.

Your job is to decide which one is more likely to be currently true, and explain \
your reasoning briefly.

Respond with ONLY valid JSON:

{
  "keep_node_label": "label of the node to keep at higher confidence",
  "reduce_node_label": "label of the node to reduce confidence for",
  "reasoning": "one sentence explaining your decision",
  "new_confidence_for_kept": 0.9,
  "new_confidence_for_reduced": 0.3
}
"""

CONTRADICTION_RESOLUTION_USER_TEMPLATE = """\
Entity: {entity_label}

Node A: "{node_a_label}" (created: {node_a_created}, confidence: {node_a_confidence})
Node B: "{node_b_label}" (created: {node_b_created}, confidence: {node_b_confidence})

These two nodes appear to contradict each other. Which is more likely to be \
currently true? Respond with ONLY the JSON object.
"""
