abstract class Env {
  static late final EnvFields _instance;
  static String? _apiBaseUrlOverride;
  static String? _agentProxyWsUrlOverride;
  static bool isTestFlight = false;

  static void init(EnvFields instance) {
    _instance = instance;
  }

  static void overrideApiBaseUrl(String url) {
    _apiBaseUrlOverride = url;
  }

  static void overrideAgentProxyWsUrl(String url) {
    _agentProxyWsUrlOverride = url;
  }

  static String? get openAIAPIKey => _instance.openAIAPIKey;

  static String? get mixpanelProjectToken => _instance.mixpanelProjectToken;

  // static String? get apiBaseUrl => 'https://omi-backend.ngrok.app/';
  static String? get apiBaseUrl => _withTrailingSlash(_apiBaseUrlOverride ?? _instance.apiBaseUrl);

  /// Staging API URL from STAGING_API_URL env var. Null when not configured.
  static String? get stagingApiUrl {
    final url = _withTrailingSlash(_instance.stagingApiUrl);
    if (url == null || url.isEmpty) return null;
    return url;
  }

  /// Whether STAGING_API_URL is configured in the environment.
  static bool get isStagingConfigured => stagingApiUrl != null;

  static bool get isUsingStagingApi {
    final effective = apiBaseUrl;
    final staging = stagingApiUrl;
    if (effective == null || staging == null) return false;
    return _normalizeUrl(effective) == _normalizeUrl(staging);
  }

  static String _normalizeUrl(String url) {
    var s = url.trim().toLowerCase();
    while (s.endsWith('/')) {
      s = s.substring(0, s.length - 1);
    }
    return s;
  }

  static String? _withTrailingSlash(String? url) {
    final trimmed = url?.trim();
    if (trimmed == null || trimmed.isEmpty) return null;
    return trimmed.endsWith('/') ? trimmed : '$trimmed/';
  }

  /// WebSocket URL for the agent proxy service.
  /// Derives from apiBaseUrl: api.omi.me → agent.omi.me, api.omiapi.com → agent.omiapi.com.
  /// Can be overridden via Env.overrideAgentProxyWsUrl() for local testing.
  static String get agentProxyWsUrl {
    if (_agentProxyWsUrlOverride != null) return _agentProxyWsUrlOverride!;
    final base = apiBaseUrl ?? 'https://api.omi.me';
    final uri = Uri.parse(base);
    final host = uri.host.replaceFirst('api.', 'agent.');
    final authority = uri.hasPort ? '$host:${uri.port}' : host;
    return 'wss://$authority/v1/agent/ws';
  }

  static String? get growthbookApiKey => _instance.growthbookApiKey;

  static String? get googleMapsApiKey => _instance.googleMapsApiKey;

  static String? get intercomAppId => _instance.intercomAppId;

  static String? get intercomIOSApiKey => _instance.intercomIOSApiKey;

  static String? get intercomAndroidApiKey => _instance.intercomAndroidApiKey;

  static String? get googleClientId => _instance.googleClientId;

  static String? get googleClientSecret => _instance.googleClientSecret;

  static bool get useWebAuth => _instance.useWebAuth ?? false;

  static bool get useAuthCustomToken => _instance.useAuthCustomToken ?? false;
}

abstract class EnvFields {
  String? get openAIAPIKey;

  String? get mixpanelProjectToken;

  String? get apiBaseUrl;

  String? get growthbookApiKey;

  String? get googleMapsApiKey;

  String? get intercomAppId;

  String? get intercomIOSApiKey;

  String? get intercomAndroidApiKey;

  String? get googleClientId;

  String? get googleClientSecret;

  bool? get useWebAuth;

  bool? get useAuthCustomToken;

  String? get stagingApiUrl;
}
