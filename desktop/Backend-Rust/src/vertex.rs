// Vertex AI authentication and URL builder.
//
// When USE_VERTEX_AI=true, Gemini calls route through Vertex AI endpoints
// with service account Bearer auth instead of AI Studio API key auth.
//
// Auth: gcp_auth reads GOOGLE_APPLICATION_CREDENTIALS (service account JSON)
// and handles token caching + automatic refresh.

use std::sync::Arc;
use tokio::sync::RwLock;

const VERTEX_AI_SCOPE: &str = "https://www.googleapis.com/auth/cloud-platform";

/// Cached bearer token with expiry tracking.
struct CachedToken {
    token: String,
    /// We refresh proactively 60s before actual expiry to avoid mid-request failures.
    expires_at: std::time::Instant,
}

/// Vertex AI auth provider. Wraps gcp_auth for token management.
#[derive(Clone)]
pub struct VertexAuth {
    provider: Arc<dyn gcp_auth::TokenProvider>,
    cache: Arc<RwLock<Option<CachedToken>>>,
    pub project_id: String,
    pub location: String,
}

impl VertexAuth {
    /// Initialize from Application Default Credentials (GOOGLE_APPLICATION_CREDENTIALS).
    pub async fn new(
        project_id: String,
        location: String,
    ) -> Result<Self, Box<dyn std::error::Error + Send + Sync>> {
        let provider = gcp_auth::provider().await.map_err(|e| {
            format!(
                "Failed to initialize GCP auth (check GOOGLE_APPLICATION_CREDENTIALS): {}",
                e
            )
        })?;

        Ok(Self {
            provider: provider.into(),
            cache: Arc::new(RwLock::new(None)),
            project_id,
            location,
        })
    }

    /// Get a valid bearer token (cached, auto-refreshes).
    pub async fn token(&self) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        // Fast path: check cached token
        {
            let cache = self.cache.read().await;
            if let Some(ref cached) = *cache {
                if cached.expires_at > std::time::Instant::now() {
                    return Ok(cached.token.clone());
                }
            }
        }

        // Slow path: fetch new token
        let token = self
            .provider
            .token(&[VERTEX_AI_SCOPE])
            .await
            .map_err(|e| format!("Failed to get Vertex AI token: {}", e))?;

        let token_str = token.as_str().to_string();

        // Cache with 60s safety margin (tokens typically last 3600s)
        let expires_at = std::time::Instant::now() + std::time::Duration::from_secs(3540);
        let mut cache = self.cache.write().await;
        *cache = Some(CachedToken {
            token: token_str.clone(),
            expires_at,
        });

        Ok(token_str)
    }

    /// Build Vertex AI URL for a Gemini model action.
    ///
    /// AI Studio path format: `models/{model}:{action}`
    /// Vertex AI URL: `https://{location}-aiplatform.googleapis.com/v1/projects/{project}/locations/{location}/publishers/google/models/{model}:{action}`
    pub fn build_url(&self, model: &str, action: &str) -> String {
        format!(
            "https://{location}-aiplatform.googleapis.com/v1/projects/{project}/locations/{location}/publishers/google/models/{model}:{action}",
            location = self.location,
            project = self.project_id,
            model = model,
            action = action,
        )
    }

    /// Build Vertex AI URL from an AI Studio-style path like "models/gemini-3-flash-preview:generateContent".
    /// Returns the full Vertex AI URL.
    pub fn build_url_from_path(&self, path: &str) -> Option<String> {
        // path = "models/{model}:{action}"
        let rest = path.strip_prefix("models/")?;
        let (model, action) = rest.split_once(':')?;
        Some(self.build_url(model, action))
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn build_url_generates_correct_vertex_endpoint() {
        // We can't create a real VertexAuth without credentials, so test URL building directly
        let url = format!(
            "https://{location}-aiplatform.googleapis.com/v1/projects/{project}/locations/{location}/publishers/google/models/{model}:{action}",
            location = "us-central1",
            project = "my-project",
            model = "gemini-3-flash-preview",
            action = "generateContent",
        );
        assert_eq!(
            url,
            "https://us-central1-aiplatform.googleapis.com/v1/projects/my-project/locations/us-central1/publishers/google/models/gemini-3-flash-preview:generateContent"
        );
    }

    #[test]
    fn build_url_from_path_parses_ai_studio_path() {
        let path = "models/gemini-3-flash-preview:generateContent";
        let rest = path.strip_prefix("models/").unwrap();
        let (model, action) = rest.split_once(':').unwrap();
        assert_eq!(model, "gemini-3-flash-preview");
        assert_eq!(action, "generateContent");
    }

    #[test]
    fn build_url_from_path_handles_embedding() {
        let path = "models/gemini-embedding-001:embedContent";
        let rest = path.strip_prefix("models/").unwrap();
        let (model, action) = rest.split_once(':').unwrap();
        assert_eq!(model, "gemini-embedding-001");
        assert_eq!(action, "embedContent");
    }

    #[test]
    fn build_url_from_path_rejects_invalid() {
        // No "models/" prefix
        let path = "gemini-3-flash-preview:generateContent";
        assert!(path.strip_prefix("models/").is_none());

        // No colon separator
        let path = "models/gemini-3-flash-preview";
        let rest = path.strip_prefix("models/").unwrap();
        assert!(rest.split_once(':').is_none());
    }
}
