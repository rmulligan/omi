class IntercomManager {
  static final IntercomManager _instance = IntercomManager._internal();
  static IntercomManager get instance => _instance;

  final IntercomClient intercom = const IntercomClient();

  IntercomManager._internal();

  factory IntercomManager() {
    return _instance;
  }

  Future<void> initIntercom() async {}

  Future<void> displayMessenger() => intercom.displayMessenger();

  Future<void> displayChargingArticle(String device) async {}

  Future<void> loginIdentifiedUser(String uid) async {}

  Future<void> loginUnidentifiedUser() async {}

  Future<void> displayEarnMoneyArticle() async {}

  Future<void> displayFirmwareUpdateArticle() async {}

  Future<void> logEvent(String eventName, {Map<String, dynamic>? metaData}) async {}

  Future<void> updateCustomAttributes(Map<String, dynamic> attributes) async {}

  Future<void> updateUser(String? email, String? name, String? uid) async {}

  Future<void> setUserAttributes() async {}

  Future<void> sendTokenToIntercom(String token) async {}
}

class IntercomClient {
  const IntercomClient();

  Future<void> displayMessenger() async {}

  Future<void> displayArticle(String articleId) async {}
}
