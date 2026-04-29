class AnalyticsManager {
  static final AnalyticsManager _instance = AnalyticsManager._internal();

  factory AnalyticsManager() {
    return _instance;
  }

  AnalyticsManager._internal();

  void setUserAttributes() {}
  void setUserAttribute(String key, dynamic value) {}
  void trackEvent(String eventName, {Map<String, dynamic>? properties}) {}
}
