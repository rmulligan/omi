import 'env.dart';

// Stubbed envied — Firebase and envied codegen were stripped from this fork.
// All values are null so the app compiles without the generated .g.dart file.
final class DevEnv implements EnvFields {
  DevEnv();

  @override
  String? get openAIAPIKey => null;
  @override
  String? get mixpanelProjectToken => null;
  @override
  String? get apiBaseUrl => null;
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
  String? get stagingApiUrl => null;
}
