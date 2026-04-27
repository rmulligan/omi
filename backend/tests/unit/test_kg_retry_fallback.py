"""
Tests for issue #6557: KG extraction retry and fallback.

Verifies that knowledge_graph.py retries LLM invoke+parse as a unit
(3 attempts with exponential backoff) and falls back gracefully when
all attempts are exhausted.
"""

import importlib.util
import json
import os
import sys
import types
from concurrent.futures import Future
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
import tenacity.nap

# Disable tenacity sleep globally for this test module
tenacity.nap.time.sleep = lambda seconds: None

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

# ---------------------------------------------------------------------------
# Stub heavy dependencies before loading knowledge_graph via spec_from_file_location
# ---------------------------------------------------------------------------

# database.knowledge_graph
_kg_db_stub = types.ModuleType("database.knowledge_graph")
_kg_db_stub.get_knowledge_nodes = MagicMock(return_value=[])
_kg_db_stub.upsert_knowledge_node = MagicMock(side_effect=lambda uid, data: data)
_kg_db_stub.upsert_knowledge_edge = MagicMock(side_effect=lambda uid, data: data)
_kg_db_stub.delete_knowledge_graph = MagicMock()
_kg_db_stub.get_knowledge_graph = MagicMock(return_value={'nodes': [], 'edges': []})

if "database" not in sys.modules or getattr(sys.modules["database"], "__file__", None) is None:
    sys.modules["database"] = types.ModuleType("database")
sys.modules["database.knowledge_graph"] = _kg_db_stub

# utils.executors
_executors_stub = types.ModuleType("utils.executors")
_executors_stub.critical_executor = MagicMock()


def _sync_submit(fn, *args, **kwargs):
    f = Future()
    try:
        result = fn(*args, **kwargs)
        f.set_result(result)
    except Exception as e:
        f.set_exception(e)
    return f


_mock_storage = MagicMock()
_mock_storage.submit = _sync_submit
_executors_stub.storage_executor = _mock_storage
sys.modules["utils.executors"] = _executors_stub

# utils.llm.clients — mock get_llm
_mock_llm = MagicMock()
_clients_stub = types.ModuleType("utils.llm.clients")
_clients_stub.get_llm = MagicMock(return_value=_mock_llm)

# utils.llm.usage_tracker — noop track_usage
_tracker_stub = types.ModuleType("utils.llm.usage_tracker")


@contextmanager
def _noop_track(*args, **kwargs):
    yield


_tracker_stub.track_usage = _noop_track
_features = MagicMock()
_features.KNOWLEDGE_GRAPH = "knowledge_graph"
_tracker_stub.Features = _features

# Register utils.llm package stubs so relative imports in knowledge_graph.py resolve
if "utils" not in sys.modules or getattr(sys.modules["utils"], "__file__", None) is None:
    _utils_pkg = types.ModuleType("utils")
    _utils_pkg.__path__ = []
    sys.modules["utils"] = _utils_pkg
if "utils.llm" not in sys.modules or getattr(sys.modules["utils.llm"], "__file__", None) is None:
    _utils_llm_pkg = types.ModuleType("utils.llm")
    _utils_llm_pkg.__path__ = []
    sys.modules["utils.llm"] = _utils_llm_pkg
sys.modules["utils.llm.clients"] = _clients_stub
sys.modules["utils.llm.usage_tracker"] = _tracker_stub

# Load knowledge_graph.py directly via spec_from_file_location
_KG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "utils", "llm", "knowledge_graph.py")
_KG_PATH = os.path.normpath(_KG_PATH)
_spec = importlib.util.spec_from_file_location("utils.llm.knowledge_graph", _KG_PATH)
_kg_mod = importlib.util.module_from_spec(_spec)
sys.modules["utils.llm.knowledge_graph"] = _kg_mod
_spec.loader.exec_module(_kg_mod)

# Pull out the symbols we need
KG_RETRY_ATTEMPTS = _kg_mod.KG_RETRY_ATTEMPTS
KnowledgeGraphExtraction = _kg_mod.KnowledgeGraphExtraction
_extract_with_retry = _kg_mod._extract_with_retry
extract_knowledge_from_memory = _kg_mod.extract_knowledge_from_memory
rebuild_knowledge_graph = _kg_mod.rebuild_knowledge_graph

# Valid JSON that PydanticOutputParser produces
VALID_EXTRACTION_JSON = json.dumps(
    {
        "nodes": [
            {"label": "Alice", "node_type": "person", "aliases": []},
            {"label": "Paris", "node_type": "place", "aliases": ["City of Light"]},
        ],
        "edges": [
            {"source_label": "Alice", "target_label": "Paris", "label": "lives in"},
        ],
    }
)


def _make_response(content):
    """Create a mock LLM response with .content attribute."""
    resp = MagicMock()
    resp.content = content
    return resp


class TestExtractWithRetry:
    """Tests for extract_knowledge_from_memory with retry behavior."""

    def setup_method(self):
        _mock_llm.reset_mock()
        _mock_llm.invoke.side_effect = None
        _kg_db_stub.get_knowledge_nodes.reset_mock()
        _kg_db_stub.upsert_knowledge_node.reset_mock()
        _kg_db_stub.upsert_knowledge_edge.reset_mock()
        _kg_db_stub.get_knowledge_nodes.return_value = []
        _kg_db_stub.upsert_knowledge_node.side_effect = lambda uid, data: data
        _kg_db_stub.upsert_knowledge_edge.side_effect = lambda uid, data: data

    def test_happy_path_no_retry(self):
        """Valid first response is parsed without retry."""
        _mock_llm.invoke.return_value = _make_response(VALID_EXTRACTION_JSON)

        result = extract_knowledge_from_memory("uid1", "Alice lives in Paris", "mem1", "Alice")

        assert result is not None
        assert len(result['nodes']) == 2
        assert len(result['edges']) == 1
        assert _mock_llm.invoke.call_count == 1

    def test_transient_failure_retries_then_succeeds(self):
        """First invoke fails, second succeeds — extraction completes."""
        _mock_llm.invoke.side_effect = [
            Exception("rate limit"),
            _make_response(VALID_EXTRACTION_JSON),
        ]

        result = extract_knowledge_from_memory("uid1", "Alice lives in Paris", "mem1", "Alice")

        assert result is not None
        assert len(result['nodes']) == 2
        assert _mock_llm.invoke.call_count == 2

    def test_parse_failure_retries_invoke(self):
        """Malformed JSON triggers re-invoke (not re-parse of same bad content)."""
        _mock_llm.invoke.side_effect = [
            _make_response("not valid json at all"),
            _make_response(VALID_EXTRACTION_JSON),
        ]

        result = extract_knowledge_from_memory("uid1", "Alice lives in Paris", "mem1", "Alice")

        assert result is not None
        assert _mock_llm.invoke.call_count == 2

    def test_exhausted_retries_returns_none(self):
        """All 3 attempts fail — returns None, no DB writes."""
        _mock_llm.invoke.side_effect = Exception("persistent failure")

        result = extract_knowledge_from_memory("uid1", "Alice lives in Paris", "mem1", "Alice")

        assert result is None
        assert _mock_llm.invoke.call_count == KG_RETRY_ATTEMPTS
        _kg_db_stub.upsert_knowledge_node.assert_not_called()
        _kg_db_stub.upsert_knowledge_edge.assert_not_called()

    def test_no_db_writes_before_successful_parse(self):
        """DB upserts happen only after successful parse, not during retries."""
        _mock_llm.invoke.side_effect = [
            Exception("transient"),
            _make_response(VALID_EXTRACTION_JSON),
        ]

        result = extract_knowledge_from_memory("uid1", "Alice lives in Paris", "mem1", "Alice")

        assert result is not None
        assert _kg_db_stub.upsert_knowledge_node.call_count == 2
        assert _kg_db_stub.upsert_knowledge_edge.call_count == 1


class TestRebuildKnowledgeGraph:
    """Tests for rebuild_knowledge_graph with retry behavior."""

    def setup_method(self):
        _mock_llm.reset_mock()
        _mock_llm.invoke.side_effect = None
        _kg_db_stub.get_knowledge_nodes.reset_mock()
        _kg_db_stub.upsert_knowledge_node.reset_mock()
        _kg_db_stub.upsert_knowledge_edge.reset_mock()
        _kg_db_stub.delete_knowledge_graph.reset_mock()
        _kg_db_stub.get_knowledge_graph.reset_mock()
        _kg_db_stub.get_knowledge_nodes.return_value = []
        _kg_db_stub.get_knowledge_graph.return_value = {'nodes': [], 'edges': []}
        _kg_db_stub.upsert_knowledge_node.side_effect = lambda uid, data: data
        _kg_db_stub.upsert_knowledge_edge.side_effect = lambda uid, data: data

    def test_rebuild_one_fails_one_succeeds(self):
        """One memory exhausts retries, another succeeds — batch completes."""
        _mock_llm.invoke.side_effect = [
            Exception("fail1"),
            Exception("fail2"),
            Exception("fail3"),
            _make_response(VALID_EXTRACTION_JSON),
        ]

        memories = [
            {'id': 'mem_bad', 'content': 'bad memory'},
            {'id': 'mem_good', 'content': 'Alice lives in Paris'},
        ]

        result = rebuild_knowledge_graph("uid1", memories, "Alice")

        assert result is not None
        assert _mock_llm.invoke.call_count == 4

    def test_rebuild_empty_content_skipped(self):
        """Memories with empty content are skipped without LLM call."""
        _mock_llm.invoke.return_value = _make_response(VALID_EXTRACTION_JSON)

        memories = [
            {'id': 'mem_empty', 'content': ''},
            {'id': 'mem_good', 'content': 'Alice lives in Paris'},
        ]

        rebuild_knowledge_graph("uid1", memories, "Alice")

        assert _mock_llm.invoke.call_count == 1


class TestRetryConfig:
    """Tests for retry configuration constants."""

    def test_retry_attempts_is_three(self):
        assert KG_RETRY_ATTEMPTS == 3

    def test_extract_with_retry_has_retry_decorator(self):
        """Verify the retry decorator is applied."""
        assert hasattr(_extract_with_retry, 'retry')
