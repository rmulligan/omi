// Re-export the main notification service for backward compatibility
// All notification functionality is now handled by the platform-aware service

export 'package:omi/services/notifications/notification_interface.dart';
export 'package:omi/services/notifications/notification_service.dart';

class NotificationUtil {
  static Future<void> initializeNotificationsEventListeners() async {}

  static Future<void> initializeIsolateReceivePort() async {}

  static Future<void> triggerFallNotification() async {}
}
