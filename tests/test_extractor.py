"""Tests for dagestan.extraction.extractor — Conversation extraction."""

import json

import pytest

from dagestan.extraction.extractor import ConversationExtractor
from dagestan.graph.schema import EdgeType, NodeType


def _mock_llm_client(response_data: dict):
    """Create a mock LLM that returns a fixed JSON response."""

    def mock_call(system_prompt: str, user_prompt: str) -> str:
        return json.dumps(response_data)

    return mock_call


class TestConversationExtractor:
    def test_basic_extraction(self):
        mock_response = {
            "nodes": [
                {"type": "entity", "label": "User", "attributes": {}},
                {"type": "preference", "label": "Loves Python", "attributes": {}},
            ],
            "edges": [
                {
                    "source_label": "User",
                    "target_label": "Loves Python",
                    "type": "has_preference",
                }
            ],
        }

        extractor = ConversationExtractor(llm_client=_mock_llm_client(mock_response))
        nodes, edges = extractor.extract("User said they love Python.")

        assert len(nodes) == 2
        assert len(edges) == 1
        assert nodes[0].type == NodeType.ENTITY
        assert nodes[0].label == "User"
        assert nodes[1].type == NodeType.PREFERENCE
        assert edges[0].type == EdgeType.HAS_PREFERENCE

    def test_empty_conversation(self):
        extractor = ConversationExtractor(llm_client=_mock_llm_client({"nodes": [], "edges": []}))
        nodes, edges = extractor.extract("")
        assert nodes == []
        assert edges == []

    def test_message_list_input(self):
        mock_response = {
            "nodes": [
                {"type": "entity", "label": "Alice", "attributes": {}},
            ],
            "edges": [],
        }

        extractor = ConversationExtractor(llm_client=_mock_llm_client(mock_response))
        messages = [
            {"role": "user", "content": "My name is Alice"},
            {"role": "assistant", "content": "Nice to meet you, Alice!"},
        ]
        nodes, edges = extractor.extract(messages)
        assert len(nodes) == 1
        assert nodes[0].label == "Alice"

    def test_handles_malformed_nodes(self):
        mock_response = {
            "nodes": [
                {"type": "entity", "label": "Good node", "attributes": {}},
                {"type": "invalid_type", "label": "Bad node", "attributes": {}},
                {"type": "concept", "label": "", "attributes": {}},  # Empty label
            ],
            "edges": [],
        }

        extractor = ConversationExtractor(llm_client=_mock_llm_client(mock_response))
        nodes, edges = extractor.extract("Some conversation")
        # Only the valid node should be extracted
        assert len(nodes) == 1
        assert nodes[0].label == "Good node"

    def test_handles_edges_with_missing_nodes(self):
        mock_response = {
            "nodes": [
                {"type": "entity", "label": "Alice", "attributes": {}},
            ],
            "edges": [
                {
                    "source_label": "Alice",
                    "target_label": "Nonexistent",
                    "type": "relates_to",
                }
            ],
        }

        extractor = ConversationExtractor(llm_client=_mock_llm_client(mock_response))
        nodes, edges = extractor.extract("Alice mentioned something")
        assert len(nodes) == 1
        assert len(edges) == 0  # Edge should be skipped

    def test_handles_llm_failure(self):
        def failing_llm(system: str, user: str) -> str:
            raise Exception("API error")

        extractor = ConversationExtractor(llm_client=failing_llm)
        nodes, edges = extractor.extract("Some conversation")
        assert nodes == []
        assert edges == []

    def test_handles_markdown_wrapped_json(self):
        def markdown_llm(system: str, user: str) -> str:
            return '```json\n{"nodes": [{"type": "entity", "label": "Test", "attributes": {}}], "edges": []}\n```'

        extractor = ConversationExtractor(llm_client=markdown_llm)
        nodes, edges = extractor.extract("Test conversation")
        assert len(nodes) == 1
        assert nodes[0].label == "Test"

    def test_no_provider_raises(self):
        with pytest.raises(ValueError, match="Must provide"):
            ConversationExtractor()

    def test_source_tag(self):
        mock_response = {
            "nodes": [
                {"type": "entity", "label": "User", "attributes": {}},
            ],
            "edges": [],
        }

        extractor = ConversationExtractor(
            llm_client=_mock_llm_client(mock_response),
            source_tag="session_42",
        )
        nodes, _ = extractor.extract("Hello")
        assert nodes[0].source == "session_42"
