import 'dart:async';
import 'dart:io';
import 'dart:math';
import 'dart:ui';

import 'package:flutter/material.dart';

import 'package:awesome_notifications/awesome_notifications.dart';
import 'package:flutter_timezone/flutter_timezone.dart';

import 'package:omi/backend/http/api/notifications.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/services/notifications/action_item_notification_handler.dart';
import 'package:omi/services/notifications/important_conversation_notification_handler.dart';
import 'package:omi/services/notifications/merge_notification_handler.dart';
import 'package:omi/services/notifications/notification_interface.dart';
import 'package:omi/utils/logger.dart';

/// Stubbed FCM notification service (local dev)
class _FCMNotificationService implements NotificationInterface {
  _FCMNotificationService._();

  final channel = NotificationChannel(
    channelGroupKey: 'channel_group_key',
    channelKey: 'channel',
    channelName: 'Omi Notifications',
    channelDescription: 'Notification channel for Omi',
    defaultColor: const Color(0xFF9D50DD),
    ledColor: Colors.white,
  );

  final AwesomeNotifications _awesomeNotifications = AwesomeNotifications();

  @override
  Future<void> initialize() async {
    bool initialized = await _awesomeNotifications.initialize(
      'resource://drawable/icon',
      [
        NotificationChannel(
          channelGroupKey: 'channel_group_key',
          channelKey: channel.channelKey,
          channelName: channel.channelName,
          channelDescription: channel.channelDescription,
          defaultColor: const Color(0xFF9D50DD),
          ledColor: Colors.white,
        ),
      ],
      channelGroups: [
        NotificationChannelGroup(channelGroupKey: channel.channelKey!, channelGroupName: channel.channelName!),
      ],
      debug: false,
    );
    Logger.debug('initializeNotifications: $initialized');
    int badgeCount = await _awesomeNotifications.getGlobalBadgeCounter();
    if (badgeCount > 0) await _awesomeNotifications.resetGlobalBadge();
  }

  @override
  Future<void> showNotification({
    required int id,
    required String title,
    required String body,
    Map<String, String?>? payload,
    bool wakeUpScreen = false,
    NotificationSchedule? schedule,
    NotificationLayout layout = NotificationLayout.Default,
  }) async {
    final allowed = await _awesomeNotifications.isNotificationAllowed();
    if (!allowed) return;
    try {
      await _awesomeNotifications.createNotification(
        content: NotificationContent(
          id: id,
          channelKey: channel.channelKey!,
          actionType: ActionType.Default,
          title: title,
          body: body,
          payload: payload,
          notificationLayout: layout,
        ),
      );
    } catch (e) {
      Logger.debug('Failed to create notification: $e');
    }
  }

  @override
  Future<bool> requestNotificationPermissions() async {
    bool isAllowed = await _awesomeNotifications.isNotificationAllowed();
    if (!isAllowed) {
      isAllowed = await _awesomeNotifications.requestPermissionToSendNotifications();
    }
    return isAllowed;
  }

  @override
  Future<void> register() async {}

  @override
  Future<String> getTimeZone() async {
    return await FlutterTimezone.getLocalTimezone();
  }

  @override
  Future<void> saveFcmToken(String? token) async {
    // NOTE: Firebase auth removed for local dev
    // Only save if we have a uid
    if (token == null) return;
    final uid = await _getUid();
    if (uid != null && token.isNotEmpty) {
      String timeZone = await getTimeZone();
      await saveFcmTokenServer(token: token, timeZone: timeZone);
      Logger.debug('FCM token saved: $token');
    }
  }

  Future<String?> _getUid() async {
    try {
      final prefs = await _getPrefs();
      return prefs.getString('uid');
    } catch (e) {
      return null;
    }
  }

  Future<dynamic> _getPrefs() async {
    // Stub: in real app this would be SharedPreferencesUtil
    return null;
  }

  @override
  Future<void> saveNotificationToken() async {
    try {
      String? token;
      // Stubbed: no Firebase messaging token in local dev
      Logger.debug('saveNotificationToken: stubbed (no FCM)');
      await saveFcmToken(token);
    } catch (e) {
      Logger.debug('Failed to save notification token: $e');
    }
  }

  @override
  Future<bool> hasNotificationPermissions() async {
    return await _awesomeNotifications.isNotificationAllowed();
  }

  @override
  Future<void> createNotification({
    String title = '',
    String body = '',
    int notificationId = 1,
    Map<String, String?>? payload,
  }) async {
    var allowed = await _awesomeNotifications.isNotificationAllowed();
    if (!allowed) return;
    Logger.debug('createNotification: Creating notification: $title');
    showNotification(id: notificationId, title: title, body: body, wakeUpScreen: true, payload: payload);
  }

  @override
  void clearNotification(int id) => _awesomeNotifications.cancel(id);

  @override
  Future<void> listenForMessages() async {
    // Stubbed: no FCM in local dev
    Logger.debug('listenForMessages: stubbed (no FCM)');
  }

  final _serverMessageStreamController = StreamController<ServerMessage>.broadcast();

  @override
  Stream<ServerMessage> get listenForServerMessages => _serverMessageStreamController.stream;

  @override
  Future<void> _showForegroundNotification({
    required dynamic noti,
    NotificationLayout layout = NotificationLayout.Default,
    Map<String, String?>? payload,
  }) async {
    if (noti.title == null || noti.body == null) return;
    final id = Random().nextInt(10000);
    showNotification(id: id, title: noti.title!, body: noti.body!, layout: layout, payload: payload);
  }
}

/// Factory function to create the FCM notification service (stubbed for local dev)
NotificationInterface createNotificationService() => _FCMNotificationService._();
