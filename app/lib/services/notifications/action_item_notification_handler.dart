import 'package:omi/utils/logger.dart';

/// Shared handler for action item notifications
class ActionItemNotificationHandler {
  static Future<void> scheduleNotification({
    required String actionItemId,
    required String description,
    required String dueAtIso,
    required String channelKey,
  }) async {
    Logger.debug('[ActionItem] notification scheduling disabled: $actionItemId');
  }

  static Future<void> cancelNotification(String actionItemId) async {
    Logger.debug('[ActionItem] notification cancellation disabled: $actionItemId');
  }

  /// Handle action item reminder data message
  static Future<void> handleReminderMessage(Map<String, dynamic> data, String channelKey) async {
    final actionItemId = data['action_item_id'];
    final description = data['description'];
    final dueAt = data['due_at'];

    if (actionItemId == null || description == null || dueAt == null) {
      Logger.debug('[ActionItem] Invalid reminder data');
      return;
    }

    await scheduleNotification(
      actionItemId: actionItemId,
      description: description,
      dueAtIso: dueAt,
      channelKey: channelKey,
    );
  }

  /// Handle action item update data message
  static Future<void> handleUpdateMessage(Map<String, dynamic> data, String channelKey) async {
    final actionItemId = data['action_item_id'];
    final description = data['description'];
    final dueAt = data['due_at'];

    if (actionItemId == null || description == null || dueAt == null) {
      Logger.debug('[ActionItem] Invalid update data');
      return;
    }

    // Cancel existing notification and reschedule with new data
    await cancelNotification(actionItemId);
    await scheduleNotification(
      actionItemId: actionItemId,
      description: description,
      dueAtIso: dueAt,
      channelKey: channelKey,
    );
  }

  /// Handle action item deletion data message
  static Future<void> handleDeletionMessage(Map<String, dynamic> data) async {
    final actionItemId = data['action_item_id'];

    if (actionItemId == null) {
      Logger.debug('[ActionItem] Invalid deletion data');
      return;
    }

    await cancelNotification(actionItemId);
  }
}
