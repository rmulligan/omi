"""Tests for Gemini AI Studio → Vertex AI migration (issue #6935).

Covers:
  - Vertex auth helper caches and refreshes tokens
  - _get_or_create_gemini_llm routes platform to Vertex AI, falls back to AI Studio
  - gemini_embed_query routing (BYOK vs Vertex)
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
# 1. Vertex access token helper
# ---------------------------------------------------------------------------


class TestVertexAccessToken:
    def test_returns_token_when_creds_valid(self):
        """When credentials are valid, return cached token without refresh."""
        import utils.llm.clients as mod

        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds.token = 'cached-token-abc'

        orig_creds = mod._vertex_credentials
        try:
            mod._vertex_credentials = mock_creds
            token = mod._get_vertex_access_token()
            assert token == 'cached-token-abc'
            mock_creds.refresh.assert_not_called()
        finally:
            mod._vertex_credentials = orig_creds

    def test_refreshes_expired_token(self):
        """When credentials are expired, refresh and return new token."""
        import utils.llm.clients as mod

        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.token = 'refreshed-token-xyz'

        orig_creds = mod._vertex_credentials
        try:
            mod._vertex_credentials = mock_creds
            token = mod._get_vertex_access_token()
            assert token == 'refreshed-token-xyz'
            mock_creds.refresh.assert_called_once()
        finally:
            mod._vertex_credentials = orig_creds

    def test_raises_when_no_credentials(self):
        """When no ADC credentials available, raise RuntimeError."""
        import utils.llm.clients as mod

        orig_creds = mod._vertex_credentials
        try:
            mod._vertex_credentials = None
            with pytest.raises(RuntimeError, match='Vertex AI credentials not available'):
                mod._get_vertex_access_token()
        finally:
            mod._vertex_credentials = orig_creds


# ---------------------------------------------------------------------------
# 2. Vertex OpenAI base URL construction
# ---------------------------------------------------------------------------


class TestVertexBaseUrl:
    def test_default_location(self):
        import utils.llm.clients as mod

        orig_project = mod._GCP_PROJECT
        try:
            mod._GCP_PROJECT = 'test-project-123'
            url = mod._vertex_openai_base_url()
            assert 'aiplatform.googleapis.com' in url
            assert 'test-project-123' in url
            assert '/endpoints/openapi' in url
        finally:
            mod._GCP_PROJECT = orig_project

    def test_custom_location(self):
        import utils.llm.clients as mod

        orig_project = mod._GCP_PROJECT
        try:
            mod._GCP_PROJECT = 'test-project-456'
            url = mod._vertex_openai_base_url(location='us-east1')
            assert 'us-east1' in url
            assert 'test-project-456' in url
        finally:
            mod._GCP_PROJECT = orig_project


# ---------------------------------------------------------------------------
# 3. Gemini LLM factory routing (Vertex AI vs AI Studio fallback)
# ---------------------------------------------------------------------------


class TestGeminiLlmFactory:
    @patch('utils.llm.clients._get_vertex_access_token', return_value='vertex-tok')
    def test_platform_routes_to_vertex_when_project_set(self, mock_token):
        """When GCP project is set, default Gemini client uses Vertex AI base URL."""
        import utils.llm.clients as mod

        orig_project = mod._GCP_PROJECT
        orig_cache = dict(mod._llm_cache)
        try:
            mod._GCP_PROJECT = 'test-project'
            mod._llm_cache.clear()
            llm = mod._get_or_create_gemini_llm('gemini-2.5-flash-lite')
            # The wrapper's initial default should use Vertex base URL
            default = llm._default
            assert 'aiplatform.googleapis.com' in default.openai_api_base
            # default_factory must be set for per-request token refresh
            assert llm._default_factory is not None
        finally:
            mod._GCP_PROJECT = orig_project
            mod._llm_cache.clear()
            mod._llm_cache.update(orig_cache)

    @patch('utils.llm.clients._get_vertex_access_token', side_effect=RuntimeError('ADC broken'))
    def test_vertex_creds_failure_falls_back_to_ai_studio(self, mock_token):
        """When GCP project is set but ADC fails, falls back to GEMINI_API_KEY."""
        import utils.llm.clients as mod

        orig_project = mod._GCP_PROJECT
        orig_cache = dict(mod._llm_cache)
        try:
            mod._GCP_PROJECT = 'test-project'
            mod._llm_cache.clear()
            llm = mod._get_or_create_gemini_llm('gemini-2.5-flash-lite')
            default = llm._default
            assert 'generativelanguage.googleapis.com' in default.openai_api_base
        finally:
            mod._GCP_PROJECT = orig_project
            mod._llm_cache.clear()
            mod._llm_cache.update(orig_cache)

    def test_no_project_uses_ai_studio(self):
        """Without GCP project, Gemini client uses AI Studio (GEMINI_API_KEY)."""
        import utils.llm.clients as mod

        orig_project = mod._GCP_PROJECT
        orig_cache = dict(mod._llm_cache)
        try:
            mod._GCP_PROJECT = ''
            mod._llm_cache.clear()
            llm = mod._get_or_create_gemini_llm('gemini-2.5-flash-lite')
            default = llm._default
            assert 'generativelanguage.googleapis.com' in default.openai_api_base
            # No default_factory for AI Studio (static API key)
            assert llm._default_factory is None
        finally:
            mod._GCP_PROJECT = orig_project
            mod._llm_cache.clear()
            mod._llm_cache.update(orig_cache)

    @patch('utils.llm.clients._get_vertex_access_token')
    def test_vertex_token_refresh_creates_new_client(self, mock_token):
        """When Vertex AI token changes, default_factory returns a new client with fresh token."""
        import utils.llm.clients as mod

        orig_project = mod._GCP_PROJECT
        orig_cache = dict(mod._llm_cache)
        orig_openai_cache = dict(mod._openai_cache)
        try:
            mod._GCP_PROJECT = 'test-project'
            mod._llm_cache.clear()
            mod._openai_cache.clear()

            # First call — token A
            mock_token.return_value = 'token-aaa'
            llm = mod._get_or_create_gemini_llm('gemini-2.5-flash-lite')
            client_a = llm._default_factory()
            assert 'aiplatform.googleapis.com' in client_a.openai_api_base

            # Second call — same token, should return cached client
            client_a2 = llm._default_factory()
            assert client_a2 is client_a

            # Third call — token refreshed (simulates ~1 hour later)
            mock_token.return_value = 'token-bbb'
            client_b = llm._default_factory()
            assert client_b is not client_a  # new client with fresh token
            assert 'aiplatform.googleapis.com' in client_b.openai_api_base
        finally:
            mod._GCP_PROJECT = orig_project
            mod._llm_cache.clear()
            mod._llm_cache.update(orig_cache)
            mod._openai_cache.clear()
            mod._openai_cache.update(orig_openai_cache)


# ---------------------------------------------------------------------------
# 4. gemini_embed_query routing
# ---------------------------------------------------------------------------


class TestGeminiEmbedRouting:
    @patch('utils.llm.clients.httpx.post')
    @patch('utils.llm.clients._get_vertex_access_token', return_value='vx-token')
    @patch('utils.llm.clients.get_byok_key', return_value=None)
    def test_platform_embed_uses_vertex_endpoint(self, mock_byok, mock_token, mock_post):
        import utils.llm.clients as mod

        orig_project = mod._GCP_PROJECT
        try:
            mod._GCP_PROJECT = 'test-project'
            mock_response = MagicMock()
            mock_response.json.return_value = {'embedding': {'values': [0.1] * 3072}}
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            result = mod.gemini_embed_query('test query')

            call_args = mock_post.call_args
            url = call_args[0][0]
            assert 'aiplatform.googleapis.com' in url
            assert 'gemini-embedding-001' in url
            headers = call_args[1].get('headers', {})
            assert headers.get('Authorization') == 'Bearer vx-token'
            assert 'x-goog-api-key' not in headers
            assert len(result) == 3072
        finally:
            mod._GCP_PROJECT = orig_project

    @patch('utils.llm.clients.httpx.post')
    @patch('utils.llm.clients.get_byok_key', return_value='byok-gem-key')
    def test_byok_embed_uses_ai_studio_endpoint(self, mock_byok, mock_post):
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


# ---------------------------------------------------------------------------
# 5. Helm config: GEMINI_API_KEY removed
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


# ---------------------------------------------------------------------------
# 6. AI Studio URL preserved for BYOK
# ---------------------------------------------------------------------------


class TestAIStudioUrlPreserved:
    def test_ai_studio_base_url_constant_exists(self):
        from utils.llm.clients import _GEMINI_AI_STUDIO_BASE_URL

        assert 'generativelanguage.googleapis.com' in _GEMINI_AI_STUDIO_BASE_URL


# ---------------------------------------------------------------------------
# 7. Boundary tests
# ---------------------------------------------------------------------------


class TestBoundaryBehavior:
    def test_concurrent_token_refresh_serialized(self):
        """Concurrent calls to _get_vertex_access_token serialize through _vertex_lock."""
        import utils.llm.clients as mod

        mock_creds = MagicMock()
        mock_creds.valid = False
        refresh_count = {'n': 0}

        def counting_refresh(request):
            refresh_count['n'] += 1

        mock_creds.refresh = counting_refresh
        mock_creds.token = 'refreshed-tok'

        orig_creds = mod._vertex_credentials
        try:
            mod._vertex_credentials = mock_creds
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                futures = [pool.submit(mod._get_vertex_access_token) for _ in range(4)]
                results = [f.result() for f in futures]
            assert all(r == 'refreshed-tok' for r in results)
            assert refresh_count['n'] >= 1
        finally:
            mod._vertex_credentials = orig_creds

    @patch('utils.llm.clients.httpx.post')
    @patch('utils.llm.clients._get_vertex_access_token', return_value='vx-token')
    @patch('utils.llm.clients.get_byok_key', return_value=None)
    def test_embedding_location_override(self, mock_byok, mock_token, mock_post):
        """GCP_EMBEDDING_LOCATION env var overrides default us-central1."""
        import utils.llm.clients as mod

        orig_project = mod._GCP_PROJECT
        try:
            mod._GCP_PROJECT = 'test-project'
            mock_response = MagicMock()
            mock_response.json.return_value = {'embedding': {'values': [0.1] * 3072}}
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            with patch.dict(os.environ, {'GCP_EMBEDDING_LOCATION': 'europe-west4'}):
                mod.gemini_embed_query('test query')

            url = mock_post.call_args[0][0]
            assert 'europe-west4' in url
            assert 'us-central1' not in url
        finally:
            mod._GCP_PROJECT = orig_project

    @patch('utils.llm.clients._get_vertex_access_token', side_effect=RuntimeError('token refresh failed'))
    @patch('utils.llm.clients.get_byok_key', return_value=None)
    def test_embed_token_refresh_failure_raises(self, mock_byok, mock_token):
        """Embedding with GCP project set but token refresh failure raises."""
        import utils.llm.clients as mod

        orig_project = mod._GCP_PROJECT
        try:
            mod._GCP_PROJECT = 'test-project'
            with pytest.raises(RuntimeError, match='token refresh failed'):
                mod.gemini_embed_query('test query')
        finally:
            mod._GCP_PROJECT = orig_project
