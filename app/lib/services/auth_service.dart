import 'dart:async';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

class UserCredential {
  final String? uid;
  final String? email;
  final String? displayName;
  final Map<String, dynamic>? additionalUserInfo;

  UserCredential({this.uid, this.email, this.displayName, this.additionalUserInfo});

  String get token => 'LOCAL_DEV_TOKEN';
}

class AuthService {
  static final AuthService _instance = AuthService._internal();
  static AuthService get instance => _instance;

  AuthService._internal();

  bool isSignedIn() => true;

  Map<String, dynamic>? getFirebaseUser() {
    return {
      'uid': _defaultUid,
      'email': 'user@local.dev',
    };
  }

  Future<UserCredential?> signInWithGoogleMobile() async {
    _autoSignIn();
    return _makeCredential();
  }

  String generateNonce([int length = 32]) {
    const charset =
        '0123456789ABCDEFGHIJKLMNOPQRSTUVXYZabcdefghijklmnopqrstuvwxyz-._';
    final random = Random.secure();
    return List.generate(length, (_) => charset[random.nextInt(charset.length)]).join();
  }

  String sha256ofString(String input) {
    // Stub — not used in local dev.
    return 'stub';
  }

  Future<UserCredential?> signInWithAppleMobile() async {
    _autoSignIn();
    return _makeCredential();
  }

  Future<void> signOut() async {
    SharedPreferencesUtil().authToken = '';
    SharedPreferencesUtil().tokenExpirationTime = 0;
    SharedPreferencesUtil().uid = '';
  }

  Future<String?> getIdToken() async {
    return 'LOCAL_DEV_TOKEN';
  }

  /// Stub — no auth flows in local dev. Always returns a default credential.
  Future<UserCredential?> authenticateWithProvider(String provider) async {
    _autoSignIn();
    return _makeCredential();
  }

  Future<Map<String, dynamic>?> _exchangeCodeForOAuthCredentials(
    String code,
    String redirectUri,
  ) async {
    return {'uid': _defaultUid, 'email': 'user@local.dev', 'custom_token': 'LOCAL_DEV_TOKEN'};
  }

  Future<UserCredential> _signInWithOAuthCredentials(
    Map<String, dynamic> oauthCredentials,
  ) async {
    final uid = oauthCredentials['uid'] ?? _defaultUid;
    final email = oauthCredentials['email'] ?? 'user@local.dev';
    SharedPreferencesUtil().uid = uid;
    SharedPreferencesUtil().email = email;
    SharedPreferencesUtil().authToken =
        oauthCredentials['custom_token'] ?? 'LOCAL_DEV_TOKEN';
    SharedPreferencesUtil().tokenExpirationTime =
        DateTime.now().add(const Duration(hours: 1)).millisecondsSinceEpoch;
    return UserCredential(uid: uid, email: email);
  }

  Future<void> _updateUserPreferences(
    UserCredential result,
    String provider,
  ) async {
    final uid = result.uid ?? _defaultUid;
    SharedPreferencesUtil().uid = uid;
    SharedPreferencesUtil().email = result.email ?? 'user@local.dev';
    final displayName = result.displayName ?? 'User';
    final parts = displayName.split(' ');
    SharedPreferencesUtil().givenName = parts.isNotEmpty ? parts[0] : 'User';
    SharedPreferencesUtil().familyName =
        parts.length > 1 ? parts.sublist(1).join(' ') : '';
    await _restoreOnboardingState();
  }

  Future<void> restoreOnboardingState() async {
    return _restoreOnboardingState();
  }

  Future<void> _restoreOnboardingState() async {
    try {
      print('DEBUG _restoreOnboardingState: stub — no server call in local dev');
      SharedPreferencesUtil().onboardingCompleted = true;
    } catch (e) {
      print('DEBUG _restoreOnboardingState: error=$e');
    }
  }

  Future<void> updateGivenName(String fullName) async {
    try {
      SharedPreferencesUtil().givenName = fullName.split(' ')[0];
      if (fullName.split(' ').length > 1) {
        SharedPreferencesUtil().familyName =
            fullName.split(' ').sublist(1).join(' ');
      }
    } catch (e) {
      Logger.debug('Error in updateGivenName: $e');
    }
  }

  String _generateState() {
    final random = Random.secure();
    final bytes = Uint8List(32);
    for (int i = 0; i < 32; i++) {
      bytes[i] = random.nextInt(256);
    }
    return base64Url.encode(bytes);
  }

  Future<UserCredential?> linkWithProvider(String provider) async {
    _autoSignIn();
    return _makeCredential();
  }

  // --- internals ---

  static String get _defaultUid =>
      Env.env['OMI_USER_UID'] ?? 'local-dev-user';

  void _autoSignIn() {
    if (isSignedIn()) return;
    SharedPreferencesUtil().uid = _defaultUid;
    SharedPreferencesUtil().email = 'user@local.dev';
    SharedPreferencesUtil().authToken = 'LOCAL_DEV_TOKEN';
    SharedPreferencesUtil().tokenExpirationTime =
        DateTime.now().add(const Duration(hours: 1)).millisecondsSinceEpoch;
  }

  UserCredential _makeCredential() {
    return UserCredential(
      uid: _defaultUid,
      email: 'user@local.dev',
      displayName: 'User',
    );
  }
}
