import 'dart:async';

import 'package:omi/utils/logger.dart';

/// Event data for merge completion
class MergeCompletedEvent {
  final String mergedConversationId;
  final List<String> removedConversationIds;

  MergeCompletedEvent({required this.mergedConversationId, required this.removedConversationIds});
}

/// Handler for conversation merge FCM notifications
class MergeNotificationHandler {
  /// Stream controller for merge completed events
  static final StreamController<MergeCompletedEvent> _mergeCompletedController =
      StreamController<MergeCompletedEvent>.broadcast();

  /// Stream to listen for merge completed events
  static Stream<MergeCompletedEvent> get onMergeCompleted => _mergeCompletedController.stream;

  /// Handle merge_completed FCM data message
  ///
  /// The app receives this when a background merge task completes.
  /// - Foreground: Provider will refresh and show toast
  /// - Background: Shows a local notification
  static Future<void> handleMergeCompleted(
    Map<String, dynamic> data,
    String channelKey, {
    bool isAppInForeground = true,
  }) async {
    final mergedConversationId = data['merged_conversation_id'];
    final removedIdsStr = data['removed_conversation_ids'] as String?;

    if (mergedConversationId == null) {
      Logger.debug('[MergeNotification] Invalid merge completed data');
      return;
    }

    final removedIds = removedIdsStr?.isNotEmpty == true ? removedIdsStr!.split(',') : <String>[];

    Logger.debug('[MergeNotification] Merge completed: $mergedConversationId, removed: $removedIds');
    Logger.debug(
      '[MergeNotification] Broadcasting event to stream (hasListener: ${_mergeCompletedController.hasListener})',
    );

    // Broadcast the event so providers can update their state
    _mergeCompletedController.add(
      MergeCompletedEvent(mergedConversationId: mergedConversationId, removedConversationIds: removedIds),
    );
    Logger.debug('[MergeNotification] Event broadcasted');

    // Show notification if app was in background
    if (!isAppInForeground) {
      Logger.debug('[MergeNotification] local notification disabled for Lilly fork');
    }
  }
}
