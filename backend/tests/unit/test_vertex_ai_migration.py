"""Tests for Gemini AI Studio → Vertex AI migration (issue #6935).

Covers:
  - _get_or_create_gemini_llm routes to ChatGoogleGenerativeAI (SDK) vs AI Studio
  - gemini_embed_query routing (BYOK via httpx vs Vertex via google-genai SDK)
  - GCP project resolution
  - Helm chart GEMINI_API_KEY removal
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-fake-for-unit-tests')
os.environ.setdefault('DEEPGRAM_API_KEY', 'dg-test-fake-for-unit-tests')
os.environ.setdefault('ANTHROPIC_API_KEY', 'ant-test-fake-for-unit-tests')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

sys.modules.setdefault('database._client', MagicMock())
sys.modules.setdefault('database.redis_db', MagicMock())
sys.modules.setdefault('database.users', MagicMock())
sys.modules.setdefault('database.user_usage', MagicMock())
sys.modules.setdefault('database.llm_usage', MagicMock())
sys.modules.setdefault('database.announcements', MagicMock())
sys.modules.setdefault('utils.other.storage', MagicMock())


# ---------------------------------------------------------------------------
# 1. Gemini LLM factory routing (Vertex AI SDK vs AI Studio)
# ---------------------------------------------------------------------------


class TestGeminiLlmFactory:
    def test_platform_routes_to_vertex_sdk_when_project_set(self):
        """When GCP project is set, default Gemini client is ChatGoogleGenerativeAI with Vertex config."""
        from langchain_google_genai import ChatGoogleGenerativeAI

        import utils.llm.clients as mod

        orig_project = mod._GCP_PROJECT
        orig_cache = dict(mod._llm_cache)
        try:
            mod._GCP_PROJECT = 'test-project'
            mod._llm_cache.clear()
            llm = mod._get_or_create_gemini_llm('gemini-2.5-flash-lite')
            default = llm._default
            # SDK client should be ChatGoogleGenerativeAI, not ChatOpenAI
            assert isinstance(default, ChatGoogleGenerativeAI)
        finally:
            mod._GCP_PROJECT = orig_project
            mod._llm_cache.clear()
            mod._llm_cache.update(orig_cache)

    @patch.dict(os.environ, {'GEMINI_API_KEY': 'test-ai-studio-key'})
    def test_no_project_uses_ai_studio_sdk(self):
        """Without GCP project, Gemini client uses AI Studio via SDK (api_key mode)."""
        from langchain_google_genai import ChatGoogleGenerativeAI

        import utils.llm.clients as mod

        orig_project = mod._GCP_PROJECT
        orig_cache = dict(mod._llm_cache)
        try:
            mod._GCP_PROJECT = ''
            mod._llm_cache.clear()
            llm = mod._get_or_create_gemini_llm('gemini-2.5-flash-lite')
            default = llm._default
            assert isinstance(default, ChatGoogleGenerativeAI)
        finally:
            mod._GCP_PROJECT = orig_project
            mod._llm_cache.clear()
            mod._llm_cache.update(orig_cache)

    @patch.dict(os.environ, {'GEMINI_API_KEY': ''}, clear=False)
    def test_no_project_no_key_falls_back_to_chatopen_ai(self):
        """Without GCP project or GEMINI_API_KEY, factory returns ChatOpenAI placeholder."""
        from langchain_openai import ChatOpenAI

        import utils.llm.clients as mod

        orig_project = mod._GCP_PROJECT
        orig_cache = dict(mod._llm_cache)
        try:
            mod._GCP_PROJECT = ''
            mod._llm_cache.clear()
            llm = mod._get_or_create_gemini_llm('gemini-2.5-flash-lite')
            default = llm._default
            assert isinstance(default, ChatOpenAI)
            assert 'generativelanguage.googleapis.com' in default.openai_api_base
        finally:
            mod._GCP_PROJECT = orig_project
            mod._llm_cache.clear()
            mod._llm_cache.update(orig_cache)

    def test_byok_resolves_to_chatopen_ai_with_ai_studio(self):
        """BYOK users get ChatOpenAI routed to AI Studio, not the Vertex SDK client."""
        from langchain_openai import ChatOpenAI

        import utils.llm.clients as mod

        orig_project = mod._GCP_PROJECT
        orig_cache = dict(mod._llm_cache)
        try:
            mod._GCP_PROJECT = 'test-project'
            mod._llm_cache.clear()
            llm = mod._get_or_create_gemini_llm('gemini-2.5-flash-lite')
            # Simulate BYOK resolution
            byok_client = llm._byok_factory('user-gemini-key')
            assert isinstance(byok_client, ChatOpenAI)
            assert 'generativelanguage.googleapis.com' in byok_client.openai_api_base
        finally:
            mod._GCP_PROJECT = orig_project
            mod._llm_cache.clear()
            mod._llm_cache.update(orig_cache)

    def test_wrapper_has_no_default_factory(self):
        """SDK handles token refresh internally — no default_factory needed on wrapper."""
        import utils.llm.clients as mod

        orig_project = mod._GCP_PROJECT
        orig_cache = dict(mod._llm_cache)
        try:
            mod._GCP_PROJECT = 'test-project'
            mod._llm_cache.clear()
            llm = mod._get_or_create_gemini_llm('gemini-2.5-flash-lite')
            assert not hasattr(llm, '_default_factory')
        finally:
            mod._GCP_PROJECT = orig_project
            mod._llm_cache.clear()
            mod._llm_cache.update(orig_cache)

    def test_cached_across_calls(self):
        """Same (model, streaming, provider) key returns cached wrapper."""
        import utils.llm.clients as mod

        orig_project = mod._GCP_PROJECT
        orig_cache = dict(mod._llm_cache)
        try:
            mod._GCP_PROJECT = 'test-project'
            mod._llm_cache.clear()
            llm1 = mod._get_or_create_gemini_llm('gemini-2.5-flash-lite')
            llm2 = mod._get_or_create_gemini_llm('gemini-2.5-flash-lite')
            assert llm1 is llm2
        finally:
            mod._GCP_PROJECT = orig_project
            mod._llm_cache.clear()
            mod._llm_cache.update(orig_cache)


# ---------------------------------------------------------------------------
# 2. gemini_embed_query routing
# ---------------------------------------------------------------------------


class TestGeminiEmbedRouting:
    @patch('utils.llm.clients._get_vertex_embed_client')
    @patch('utils.llm.clients.get_byok_key', return_value=None)
    def test_platform_embed_uses_vertex_sdk(self, mock_byok, mock_client):
        """Platform embedding uses google-genai SDK client."""
        import utils.llm.clients as mod

        orig_project = mod._GCP_PROJECT
        try:
            mod._GCP_PROJECT = 'test-project'
            mock_embed_result = MagicMock()
            mock_embed_result.embeddings = [MagicMock(values=[0.1] * 3072)]
            mock_client.return_value.models.embed_content.return_value = mock_embed_result

            result = mod.gemini_embed_query('test query')

            mock_client.assert_called_once_with('us-central1')
            mock_client.return_value.models.embed_content.assert_called_once()
            call_kwargs = mock_client.return_value.models.embed_content.call_args
            assert call_kwargs[1]['model'] == 'gemini-embedding-001'
            assert call_kwargs[1]['contents'] == 'test query'
            assert len(result) == 3072
        finally:
            mod._GCP_PROJECT = orig_project

    @patch('utils.llm.clients.httpx.post')
    @patch('utils.llm.clients.get_byok_key', return_value='byok-gem-key')
    def test_byok_embed_uses_ai_studio_endpoint(self, mock_byok, mock_post):
        """BYOK users get AI Studio embedding via httpx (not the Vertex SDK)."""
        from utils.llm.clients import gemini_embed_query

        mock_response = MagicMock()
        mock_response.json.return_value = {'embedding': {'values': [0.2] * 3072}}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = gemini_embed_query('test query')

        call_args = mock_post.call_args
        url = call_args[0][0]
        assert 'generativelanguage.googleapis.com' in url
        assert 'aiplatform.googleapis.com' not in url
        headers = call_args[1].get('headers', {})
        assert headers.get('x-goog-api-key') == 'byok-gem-key'
        assert len(result) == 3072

    @patch('utils.llm.clients.get_byok_key', return_value=None)
    def test_embed_no_project_raises_clear_error(self, mock_byok):
        """Without BYOK or GCP project, embedding raises RuntimeError."""
        import utils.llm.clients as mod

        orig_project = mod._GCP_PROJECT
        try:
            mod._GCP_PROJECT = ''
            with pytest.raises(RuntimeError, match='BYOK key or GCP project'):
                mod.gemini_embed_query('test query')
        finally:
            mod._GCP_PROJECT = orig_project

    @patch('utils.llm.clients._get_vertex_embed_client')
    @patch('utils.llm.clients.get_byok_key', return_value=None)
    def test_embedding_location_override(self, mock_byok, mock_client):
        """GCP_EMBEDDING_LOCATION env var overrides default us-central1."""
        import utils.llm.clients as mod

        orig_project = mod._GCP_PROJECT
        try:
            mod._GCP_PROJECT = 'test-project'
            mock_embed_result = MagicMock()
            mock_embed_result.embeddings = [MagicMock(values=[0.1] * 3072)]
            mock_client.return_value.models.embed_content.return_value = mock_embed_result

            with patch.dict(os.environ, {'GCP_EMBEDDING_LOCATION': 'europe-west4'}):
                mod.gemini_embed_query('test query')

            mock_client.assert_called_once_with('europe-west4')
        finally:
            mod._GCP_PROJECT = orig_project


# ---------------------------------------------------------------------------
# 3. Vertex embed client caching
# ---------------------------------------------------------------------------


class TestVertexEmbedClient:
    def test_client_cached_per_location(self):
        """_get_vertex_embed_client caches clients per location."""
        import utils.llm.clients as mod

        orig_clients = dict(mod._vertex_embed_clients)
        orig_project = mod._GCP_PROJECT
        try:
            mod._GCP_PROJECT = 'test-project'
            mod._vertex_embed_clients.clear()

            client_a = mod._get_vertex_embed_client('us-central1')
            client_b = mod._get_vertex_embed_client('us-central1')
            assert client_a is client_b  # same location → cached

            client_c = mod._get_vertex_embed_client('europe-west4')
            assert client_c is not client_a  # different location → new client
        finally:
            mod._vertex_embed_clients.clear()
            mod._vertex_embed_clients.update(orig_clients)
            mod._GCP_PROJECT = orig_project


# ---------------------------------------------------------------------------
# 4. Helm config: GEMINI_API_KEY removed
# ---------------------------------------------------------------------------


class TestHelmGeminiKeyRemoved:
    """Verify GEMINI_API_KEY is no longer referenced in backend Helm charts."""

    def test_no_gemini_api_key_in_backend_listen_dev(self):
        chart_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'charts', 'backend-listen', 'dev_omi_backend_listen_values.yaml'
        )
        if os.path.exists(chart_path):
            with open(chart_path) as f:
                content = f.read()
            assert 'GEMINI_API_KEY' not in content

    def test_no_gemini_api_key_in_backend_listen_prod(self):
        chart_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'charts', 'backend-listen', 'prod_omi_backend_listen_values.yaml'
        )
        if os.path.exists(chart_path):
            with open(chart_path) as f:
                content = f.read()
            assert 'GEMINI_API_KEY' not in content

    def test_no_gemini_api_key_in_backend_secrets_dev(self):
        chart_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'charts', 'backend-secrets', 'dev_omi_backend_secrets_values.yaml'
        )
        if os.path.exists(chart_path):
            with open(chart_path) as f:
                content = f.read()
            assert 'GEMINI_API_KEY' not in content

    def test_no_gemini_api_key_in_backend_secrets_prod(self):
        chart_path = os.path.join(
            os.path.dirname(__file__),
            '..',
            '..',
            'charts',
            'backend-secrets',
            'prod_omi_backend_secrets_values.yaml',
        )
        if os.path.exists(chart_path):
            with open(chart_path) as f:
                content = f.read()
            assert 'GEMINI_API_KEY' not in content

    def test_gcp_location_in_backend_listen_dev(self):
        """GCP_LOCATION env var must be set in dev Helm chart."""
        chart_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'charts', 'backend-listen', 'dev_omi_backend_listen_values.yaml'
        )
        if os.path.exists(chart_path):
            with open(chart_path) as f:
                content = f.read()
            assert 'GCP_LOCATION' in content

    def test_gcp_location_in_backend_listen_prod(self):
        """GCP_LOCATION env var must be set in prod Helm chart."""
        chart_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'charts', 'backend-listen', 'prod_omi_backend_listen_values.yaml'
        )
        if os.path.exists(chart_path):
            with open(chart_path) as f:
                content = f.read()
            assert 'GCP_LOCATION' in content


# ---------------------------------------------------------------------------
# 5. AI Studio URL preserved for BYOK
# ---------------------------------------------------------------------------


class TestAIStudioUrlPreserved:
    def test_ai_studio_base_url_constant_exists(self):
        from utils.llm.clients import _GEMINI_AI_STUDIO_BASE_URL

        assert 'generativelanguage.googleapis.com' in _GEMINI_AI_STUDIO_BASE_URL


# ---------------------------------------------------------------------------
# 6. SDK dependency
# ---------------------------------------------------------------------------


class TestSDKAvailable:
    def test_langchain_google_genai_importable(self):
        """langchain-google-genai SDK must be importable."""
        from langchain_google_genai import ChatGoogleGenerativeAI

        assert ChatGoogleGenerativeAI is not None

    def test_google_genai_importable(self):
        """google-genai SDK must be importable (used for embeddings)."""
        from google import genai

        assert genai.Client is not None

    def test_requirements_includes_sdk(self):
        """requirements.txt includes langchain-google-genai."""
        req_path = os.path.join(os.path.dirname(__file__), '..', '..', 'requirements.txt')
        with open(req_path) as f:
            content = f.read()
        assert 'langchain-google-genai' in content
