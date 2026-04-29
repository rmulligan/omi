import 'dart:async';

import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/logger.dart';

/// Event data for important conversation completion
class ImportantConversationEvent {
  final String conversationId;
  final String navigateTo;

  ImportantConversationEvent({required this.conversationId, required this.navigateTo});
}

/// Handler for important conversation FCM notifications
/// Triggered when a conversation >30 minutes completes processing
class ImportantConversationNotificationHandler {
  /// Stream controller for important conversation events
  static final StreamController<ImportantConversationEvent> _importantConversationController =
      StreamController<ImportantConversationEvent>.broadcast();

  /// Stream to listen for important conversation events
  static Stream<ImportantConversationEvent> get onImportantConversation => _importantConversationController.stream;

  /// Handle important_conversation FCM data message
  ///
  /// The app receives this when a long conversation (>30 min) completes processing.
  /// - Foreground: Provider can show toast, then user can tap notification
  /// - Background: Shows a local notification that navigates to conversation detail with share sheet
  static Future<void> handleImportantConversation(
    Map<String, dynamic> data,
    String channelKey, {
    bool isAppInForeground = true,
  }) async {
    final conversationId = data['conversation_id'];
    final navigateTo = data['navigate_to'] as String?;

    if (conversationId == null) {
      Logger.debug('[ImportantConversationNotification] Invalid data: missing conversation_id');
      return;
    }

    Logger.debug('[ImportantConversationNotification] Important conversation completed: $conversationId');
    Logger.debug('[ImportantConversationNotification] Navigate to: $navigateTo');

    // Track notification received
    MixpanelManager().importantConversationNotificationReceived(conversationId);

    // Broadcast the event so providers can update their state
    _importantConversationController.add(
      ImportantConversationEvent(
        conversationId: conversationId,
        navigateTo: navigateTo ?? '/conversation/$conversationId?share=1',
      ),
    );

    Logger.debug('[ImportantConversationNotification] local notification disabled for Lilly fork');
  }
}
