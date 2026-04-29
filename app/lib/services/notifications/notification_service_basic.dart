import 'package:omi/services/notifications/notification_interface.dart';
import 'package:omi/services/notifications/notification_service_fcm.dart' as noop;

NotificationInterface createNotificationService() => noop.createNotificationService();
