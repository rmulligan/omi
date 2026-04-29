import 'dart:async';

import 'package:flutter_timezone/flutter_timezone.dart';

import 'package:omi/backend/schema/message.dart';
import 'package:omi/services/notifications/notification_interface.dart';
import 'package:omi/utils/logger.dart';

/// Notifications are intentionally disabled for the Lilly fork.
class _NoopNotificationService implements NotificationInterface {
  _NoopNotificationService._();

  @override
  Future<void> initialize() async {
    Logger.debug('Notifications disabled for Lilly fork');
  }

  @override
  Future<void> showNotification({
    required int id,
    required String title,
    required String body,
    Map<String, String?>? payload,
    bool wakeUpScreen = false,
  }) async {}

  @override
  Future<bool> requestNotificationPermissions() async => false;

  @override
  Future<void> register() async {}

  @override
  Future<String> getTimeZone() async {
    try {
      return await FlutterTimezone.getLocalTimezone();
    } catch (_) {
      return 'UTC';
    }
  }

  @override
  Future<void> saveFcmToken(String? token) async {}

  @override
  Future<void> saveNotificationToken() async {}

  @override
  Future<bool> hasNotificationPermissions() async => false;

  @override
  Future<void> createNotification({
    String title = '',
    String body = '',
    int notificationId = 1,
    Map<String, String?>? payload,
  }) async {}

  @override
  void clearNotification(int id) {}

  @override
  Future<void> listenForMessages() async {
    Logger.debug('listenForMessages skipped; notifications disabled');
  }

  final _serverMessageStreamController = StreamController<ServerMessage>.broadcast();

  @override
  Stream<ServerMessage> get listenForServerMessages => _serverMessageStreamController.stream;
}

NotificationInterface createNotificationService() => _NoopNotificationService._();
