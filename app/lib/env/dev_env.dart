import 'env.dart';

const _localLillyApiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://100.83.194.65:8010/',
);

const _localLillyStagingApiUrl = String.fromEnvironment(
  'STAGING_API_URL',
  defaultValue: _localLillyApiBaseUrl,
);

// Stubbed envied — Firebase and envied codegen were stripped from this fork.
final class DevEnv implements EnvFields {
  DevEnv();

  @override
  String? get openAIAPIKey => null;
  @override
  String? get mixpanelProjectToken => null;
  @override
  String? get apiBaseUrl => _localLillyApiBaseUrl;
  @override
  String? get growthbookApiKey => null;
  @override
  String? get googleMapsApiKey => null;
  @override
  String? get intercomAppId => null;
  @override
  String? get intercomIOSApiKey => null;
  @override
  String? get intercomAndroidApiKey => null;
  @override
  String? get googleClientId => null;
  @override
  String? get googleClientSecret => null;
  @override
  bool? get useWebAuth => false;
  @override
  bool? get useAuthCustomToken => false;
  @override
  String? get stagingApiUrl => _localLillyStagingApiUrl;
}
