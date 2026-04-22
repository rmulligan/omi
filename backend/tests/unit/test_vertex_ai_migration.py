"""Tests for Gemini AI Studio → Vertex AI migration (issue #6935).

Covers:
  - Vertex auth helper caches and refreshes tokens
  - _VertexGeminiProxy routes BYOK to AI Studio, platform to Vertex AI
  - gemini_embed_query routing (BYOK vs Vertex)
  - OpenRouter kwargs stripped for Vertex clients
  - GCP project resolution
  - Helm chart GEMINI_API_KEY removal
"""

import os
import sys
import types
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
# 3. _VertexGeminiProxy routing
# ---------------------------------------------------------------------------


class TestVertexGeminiProxy:
    @patch('utils.llm.clients._get_vertex_access_token', return_value='vertex-tok')
    @patch('utils.llm.clients.get_byok_key', return_value=None)
    def test_platform_routes_to_vertex(self, mock_byok, mock_token):
        """Without BYOK key, proxy should route to Vertex AI."""
        import utils.llm.clients as mod

        orig_project = mod._GCP_PROJECT
        try:
            mod._GCP_PROJECT = 'test-project'
            mock_default = MagicMock()
            proxy = mod._VertexGeminiProxy(
                default=mock_default,
                direct_model='gemini-3-flash-preview',
                ctor_kwargs={
                    'api_key': 'openrouter-key',
                    'base_url': 'https://openrouter.ai/api/v1',
                    'default_headers': {'X-Title': 'Omi Chat'},
                    'callbacks': [],
                },
            )
            resolved = proxy._resolve()
            # Should NOT be the OpenRouter default
            assert resolved is not mock_default
        finally:
            mod._GCP_PROJECT = orig_project

    @patch('utils.llm.clients.get_byok_key', return_value='user-gemini-key')
    def test_byok_routes_to_ai_studio(self, mock_byok):
        """With BYOK key, proxy should route to AI Studio."""
        import utils.llm.clients as mod

        mock_default = MagicMock()
        proxy = mod._VertexGeminiProxy(
            default=mock_default,
            direct_model='gemini-3-flash-preview',
            ctor_kwargs={'callbacks': []},
        )
        resolved = proxy._resolve()
        # Should NOT be the OpenRouter default (it's a cached AI Studio client)
        assert resolved is not mock_default

    @patch('utils.llm.clients.get_byok_key', return_value=None)
    def test_no_vertex_config_falls_back_to_openrouter(self, mock_byok):
        """Without GCP project, proxy falls back to OpenRouter default."""
        import utils.llm.clients as mod

        orig_project = mod._GCP_PROJECT
        try:
            mod._GCP_PROJECT = ''
            mock_default = MagicMock()
            proxy = mod._VertexGeminiProxy(
                default=mock_default,
                direct_model='gemini-3-flash-preview',
                ctor_kwargs={'callbacks': []},
            )
            resolved = proxy._resolve()
            assert resolved is mock_default
        finally:
            mod._GCP_PROJECT = orig_project

    @patch('utils.llm.clients._get_vertex_access_token', return_value='vertex-tok')
    @patch('utils.llm.clients.get_byok_key', return_value=None)
    def test_vertex_client_strips_openrouter_kwargs(self, mock_byok, mock_token):
        """Verify OpenRouter-specific kwargs (api_key, default_headers) are NOT passed to Vertex client."""
        import utils.llm.clients as mod

        orig_project = mod._GCP_PROJECT
        orig_cache = dict(mod._openai_cache)
        try:
            mod._GCP_PROJECT = 'test-project'
            mod._openai_cache.clear()

            captured = {}
            orig_cached_fn = mod._cached_openai_chat

            def capturing_cached_openai_chat(model, api_key, ctor_kwargs):
                captured['model'] = model
                captured['api_key'] = api_key
                captured['ctor_kwargs'] = ctor_kwargs
                return MagicMock()

            with patch.object(mod, '_cached_openai_chat', capturing_cached_openai_chat):
                proxy = mod._VertexGeminiProxy(
                    default=MagicMock(),
                    direct_model='gemini-3-flash-preview',
                    ctor_kwargs={
                        'api_key': 'openrouter-key-LEAKED',
                        'base_url': 'https://openrouter.ai/api/v1',
                        'default_headers': {'X-Title': 'Omi Chat'},
                        'callbacks': ['cb1'],
                        'temperature': 0.7,
                    },
                )
                proxy._resolve()

            assert 'openrouter-key-LEAKED' not in str(captured.get('ctor_kwargs', {}))
            assert captured['ctor_kwargs'].get('callbacks') == ['cb1']
            assert captured['ctor_kwargs'].get('temperature') == 0.7
            assert 'aiplatform.googleapis.com' in captured['ctor_kwargs']['base_url']
        finally:
            mod._GCP_PROJECT = orig_project
            mod._openai_cache.clear()
            mod._openai_cache.update(orig_cache)


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
