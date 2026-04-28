import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'package:omi/utils/debugging/crash_reporter.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_service.dart';

class CrashlyticsManager implements CrashReporter {
  static final CrashlyticsManager _instance = CrashlyticsManager._internal();
  static CrashlyticsManager get instance => _instance;

  CrashlyticsManager._internal();

  factory CrashlyticsManager() {
    return _instance;
  }

  static Future<void> init() async {
    // NOTE: Firebase Crashlytics removed for local dev
    Logger.debug('CrashlyticsManager initialized (local dev mode)');
  }

  @override
  void identifyUser(String email, String name, String userId) {
    Logger.debug('Crashlytics identify: userId=$userId, email=$email, name=$name');
  }

  @override
  void logInfo(String message) {
    Logger.info(message);
  }

  @override
  void logError(String message) {
    Logger.error(message);
  }

  @override
  void logWarn(String message) {
    Logger.warn(message);
  }

  @override
  void logDebug(String message) {
    Logger.debug(message);
  }

  @override
  void logVerbose(String message) {
    Logger.debug(message);
  }

  @override
  void setUserAttribute(String key, String value) {
    Logger.debug('Crashlytics setUserAttribute: $key=$value');
  }

  @override
  void setEnabled(bool isEnabled) {
    Logger.debug('Crashlytics setEnabled: $isEnabled');
  }

  @override
  Future<void> reportCrash(Object exception, StackTrace stackTrace, {Map<String, String>? userAttributes}) async {
    Logger.debug('Crashlytics reportCrash: $exception');
    if (userAttributes != null) {
      for (final entry in userAttributes.entries) {
        Logger.debug('Crashlytics attribute: ${entry.key}=${entry.value}');
      }
    }
  }

  @override
  NavigatorObserver? getNavigatorObserver() {
    return null;
  }

  @override
  bool get isSupported => true;
}
