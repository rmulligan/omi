import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import 'package:app_links/app_links.dart';
import 'package:crypto/crypto.dart';
import 'package:http/http.dart' as http;
import 'package:sign_in_with_apple/sign_in_with_apple.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/logger.dart';

class UserCredential {
  final String? uid;
  final String? email;
  final String? displayName;
  final Map<String, dynamic>? additionalUserInfo;

  UserCredential({this.uid, this.email, this.displayName, this.additionalUserInfo});
}

class AuthService {
  static final AuthService _instance = AuthService._internal();
  static AuthService get instance => _instance;

  AuthService._internal();

  bool isSignedIn() => SharedPreferencesUtil().uid.isNotEmpty;

  getFirebaseUser() {
    return SharedPreferencesUtil().uid.isNotEmpty
        ? {'uid': SharedPreferencesUtil().uid, 'email': SharedPreferencesUtil().email}
        : null;
  }

  /// Google Sign In using the standard google_sign_in package (iOS, Android)
  Future<UserCredential?> signInWithGoogleMobile() async {
    print('DEBUG_AUTH: Using standard Google Sign In for mobile');

    // Trigger the authentication flow
    // NOTE: For local dev, this uses the web auth flow instead
    final credential = await authenticateWithProvider('google');
    print('DEBUG_AUTH: Google Sign In result: ${credential?.uid}');
    return credential;
  }

  /// Generates a cryptographically secure random nonce, to be included in a
  /// credential request.
  String generateNonce([int length = 32]) {
    const charset = '0123456789ABCDEFGHIJKLMNOPQRSTUVXYZabcdefghijklmnopqrstuvwxyz-._';
    final random = Random.secure();
    return List.generate(length, (_) => charset[random.nextInt(charset.length)]).join();
  }

  /// Returns the sha256 hash of [input] in hex notation.
  String sha256ofString(String input) {
    final bytes = utf8.encode(input);
    final digest = sha256.convert(bytes);
    return digest.toString();
  }

  Future<UserCredential?> signInWithAppleMobile() async {
    try {
      Logger.debug('Signing out current user...');
      await signOut();
      Logger.debug('User signed out successfully.');

      final rawNonce = generateNonce();
      final nonce = sha256ofString(rawNonce);

      Logger.debug('Requesting Apple credential...');
      final appleCredential = await SignInWithApple.getAppleIDCredential(
        scopes: [AppleIDAuthorizationScopes.email, AppleIDAuthorizationScopes.fullName],
        nonce: nonce,
      );

      if (appleCredential.identityToken == null) {
        throw Exception('Apple Sign In failed - no identity token received.');
      }

      // Use web auth flow for Apple
      final credential = await authenticateWithProvider('apple');
      Logger.debug('Apple sign-in successful.');

      // Extract name from Apple credential (only available on first sign-in)
      if (appleCredential.givenName != null && appleCredential.givenName!.isNotEmpty) {
        Logger.debug('Apple provided name: ${appleCredential.givenName} ${appleCredential.familyName ?? ""}');
        SharedPreferencesUtil().givenName = appleCredential.givenName!;
        if (appleCredential.familyName != null && appleCredential.familyName!.isNotEmpty) {
          SharedPreferencesUtil().familyName = appleCredential.familyName!;
        }
      }

      await _updateUserPreferences(credential, 'apple');
      return credential;
    } catch (e) {
      Logger.debug('Error during Apple Sign In: $e');
      Logger.handle(e, null, message: 'An error occurred while signing in. Please try again later.');
      return null;
    }
  }

  Future<void> signOut() async {
    _clearCachedAuth();
  }

  void _clearCachedAuth() {
    SharedPreferencesUtil().authToken = '';
    SharedPreferencesUtil().tokenExpirationTime = 0;
    SharedPreferencesUtil().uid = '';
  }

  Future<String?> getIdToken() async {
    try {
      final uid = SharedPreferencesUtil().uid;
      if (uid.isEmpty) {
        Logger.debug('getIdToken: uid is empty, clearing cached token');
        _clearCachedAuth();
        return null;
      }

      // Use admin key auth for local dev
      final authToken = SharedPreferencesUtil().authToken;
      if (authToken.isNotEmpty) {
        return authToken;
      }

      Logger.debug('getIdToken: no cached token');
      return null;
    } catch (e) {
      Logger.debug('getIdToken: token refresh failed (transient): $e');
      return null;
    }
  }

  // Method channel for direct deep link delivery (fallback for app_links)
  static const _deepLinkChannel = MethodChannel('com.omi/deep_links');

  Future<UserCredential?> authenticateWithProvider(String provider) async {
    try {
      final state = _generateState();
      const redirectUri = 'omi://auth/callback';

      Logger.debug('Starting OAuth flow for provider: $provider');

      final authUrl = '${Env.apiBaseUrl}v1/auth/authorize'
          '?provider=$provider'
          '&redirect_uri=${Uri.encodeComponent(redirectUri)}'
          '&state=$state';

      Logger.debug('Authorization URL: $authUrl');

      // Set up listeners before launching URL
      final appLinks = AppLinks();
      late StreamSubscription linkSubscription;
      final completer = Completer<String>();

      // Listen via app_links
      linkSubscription = appLinks.uriLinkStream.listen(
        (Uri uri) {
          Logger.debug('Received callback URI via app_links: $uri');
          if (uri.scheme == 'omi' && uri.host == 'auth' && uri.path == '/callback') {
            if (!completer.isCompleted) {
              linkSubscription.cancel();
              completer.complete(uri.toString());
            }
          }
        },
        onError: (error) {
          Logger.debug('App link error: $error');
          if (!completer.isCompleted) {
            linkSubscription.cancel();
            completer.completeError(error);
          }
        },
      );

      // Also listen via direct method channel (fallback)
      _deepLinkChannel.setMethodCallHandler((call) async {
        if (call.method == 'onDeepLink') {
          final urlString = call.arguments as String;
          Logger.debug('Received callback URI via method channel: $urlString');
          final uri = Uri.parse(urlString);
          if (uri.scheme == 'omi' && uri.host == 'auth' && uri.path == '/callback') {
            if (!completer.isCompleted) {
              linkSubscription.cancel();
              _deepLinkChannel.setMethodCallHandler(null);
              completer.complete(urlString);
            }
          }
        }
      });

      // Now launch the URL
      final launched = await launchUrl(Uri.parse(authUrl), mode: LaunchMode.inAppBrowserView);

      if (!launched) {
        linkSubscription.cancel();
        _deepLinkChannel.setMethodCallHandler(null);
        throw Exception('Failed to launch authentication URL');
      }

      final result = await completer.future.timeout(
        const Duration(minutes: 5),
        onTimeout: () {
          linkSubscription.cancel();
          _deepLinkChannel.setMethodCallHandler(null);
          throw Exception('Authentication timeout');
        },
      );

      final uri = Uri.parse(result);
      final code = uri.queryParameters['code'];
      final returnedState = uri.queryParameters['state'];

      if (code == null) {
        throw Exception('No authorization code received');
      }

      if (returnedState != state) {
        throw Exception('Invalid state parameter');
      }

      // Exchange the code for OAuth credentials
      final oauthCredentials = await _exchangeCodeForOAuthCredentials(code, redirectUri);

      if (oauthCredentials == null) {
        throw Exception('Failed to exchange code for OAuth credentials');
      }

      // Sign in with the OAuth credentials (admin key auth for local dev)
      final credential = await _signInWithOAuthCredentials(oauthCredentials);

      // Update user profile and local storage after successful sign-in
      await _updateUserPreferences(credential, provider);

      Logger.debug('Authentication successful');
      return credential;
    } catch (e) {
      Logger.debug('OAuth authentication error: $e');
      Logger.handle(e, StackTrace.current, message: 'Authentication failed');
      return null;
    }
  }

  Future<Map<String, dynamic>?> _exchangeCodeForOAuthCredentials(String code, String redirectUri) async {
    try {
      final useCustomToken = Env.useAuthCustomToken;

      final response = await http.post(
        Uri.parse('${Env.apiBaseUrl}v1/auth/token'),
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: {
          'grant_type': 'authorization_code',
          'code': code,
          'redirect_uri': redirectUri,
          'use_custom_token': useCustomToken.toString(),
        },
      );

      Logger.debug('Token exchange response status: ${response.statusCode}');
      Logger.debug('Token exchange response body: ${response.body}');

      if (response.statusCode == 200) {
        return json.decode(response.body);
      } else {
        Logger.debug('Token exchange failed: ${response.body}');
        return null;
      }
    } catch (e) {
      Logger.debug('Token exchange error: $e');
      return null;
    }
  }

  Future<UserCredential> _signInWithOAuthCredentials(Map<String, dynamic> oauthCredentials) async {
    final provider = oauthCredentials['provider'];
    final useCustomToken = Env.useAuthCustomToken;
    final customToken = oauthCredentials['custom_token'];

    // Use custom token if enabled and available
    if (useCustomToken && customToken != null) {
      Logger.debug('Signing in with custom token from $provider');
      // For local dev, store the UID from the custom token
      final uid = oauthCredentials['uid'] ?? '';
      final email = oauthCredentials['email'] ?? '';
      final givenName = oauthCredentials['given_name'] ?? '';
      final familyName = oauthCredentials['family_name'] ?? '';

      SharedPreferencesUtil().uid = uid;
      SharedPreferencesUtil().email = email;
      SharedPreferencesUtil().givenName = givenName;
      SharedPreferencesUtil().familyName = familyName;
      SharedPreferencesUtil().authToken = customToken;
      SharedPreferencesUtil().tokenExpirationTime = DateTime.now().add(Duration(hours: 1)).millisecondsSinceEpoch;

      return UserCredential(uid: uid, email: email, displayName: '$givenName $familyName'.trim());
    }

    // Fallback to UID from OAuth credentials
    final uid = oauthCredentials['uid'] ?? '';
    final email = oauthCredentials['email'] ?? '';
    final givenName = oauthCredentials['given_name'] ?? '';
    final familyName = oauthCredentials['family_name'] ?? '';

    SharedPreferencesUtil().uid = uid;
    SharedPreferencesUtil().email = email;
    SharedPreferencesUtil().givenName = givenName;
    SharedPreferencesUtil().familyName = familyName;
    SharedPreferencesUtil().authToken = customToken ?? '';

    return UserCredential(uid: uid, email: email, displayName: '$givenName $familyName'.trim());
  }

  Future<void> _updateUserPreferences(UserCredential result, String provider) async {
    try {
      final uid = result.uid;
      if (uid == null || uid.isEmpty) return;

      // Update UID and basic user info
      SharedPreferencesUtil().uid = uid;

      // Get user info from result
      var email = result.email ?? '';
      var displayName = result.displayName ?? '';
      var givenName = '';
      var familyName = '';

      if (result.additionalUserInfo?.profile != null) {
        final profile = result.additionalUserInfo!['profile'] as Map<String, dynamic>? ?? {};

        if (provider == 'google') {
          givenName = profile['given_name'] ?? '';
          familyName = profile['family_name'] ?? '';
          email = profile['email'] ?? email;
        } else if (provider == 'apple') {
          if (profile.containsKey('name')) {
            final name = profile['name'];
            if (name is Map) {
              givenName = name['firstName'] ?? '';
              familyName = name['lastName'] ?? '';
            }
          }
          email = profile['email'] ?? email;
        }
      }

      if (givenName.isEmpty && displayName.isNotEmpty) {
        var nameParts = displayName.split(' ');
        givenName = nameParts.isNotEmpty ? nameParts[0] : '';
        familyName = nameParts.length > 1 ? nameParts.sublist(1).join(' ') : '';
      }

      // Update SharedPreferences
      if (email.isNotEmpty) {
        SharedPreferencesUtil().email = email;
      }
      if (givenName.isNotEmpty) {
        SharedPreferencesUtil().givenName = givenName;
        SharedPreferencesUtil().familyName = familyName;
      }

      Logger.debug('Updated user preferences:');
      Logger.debug('Email: ${SharedPreferencesUtil().email}');
      Logger.debug('Given Name: ${SharedPreferencesUtil().givenName}');
      Logger.debug('Family Name: ${SharedPreferencesUtil().familyName}');
      Logger.debug('UID: ${SharedPreferencesUtil().uid}');

      // Restore onboarding state from server
      await _restoreOnboardingState();
    } catch (e) {
      Logger.debug('Error updating user preferences: $e');
    }
  }

  /// Restore onboarding state from server. Call this on app startup when using cached credentials.
  Future<void> restoreOnboardingState() async {
    return _restoreOnboardingState();
  }

  Future<void> _restoreOnboardingState() async {
    try {
      print('DEBUG _restoreOnboardingState: fetching from server...');
      final state = await getUserOnboardingState();
      print('DEBUG _restoreOnboardingState: got state=$state');
      if (state != null) {
        if (state['completed'] == true) {
          print('DEBUG _restoreOnboardingState: setting onboardingCompleted=true');
          SharedPreferencesUtil().onboardingCompleted = true;
        }
        final acquisitionSource = state['acquisition_source'] as String? ?? '';
        if (acquisitionSource.isNotEmpty) {
          SharedPreferencesUtil().foundOmiSource = acquisitionSource;
        }
        // Restore language from server if not already set locally
        final serverLanguage = await getUserPrimaryLanguage();
        if (serverLanguage != null && serverLanguage.isNotEmpty) {
          SharedPreferencesUtil().userPrimaryLanguage = serverLanguage;
          SharedPreferencesUtil().hasSetPrimaryLanguage = true;
        }
        print(
          'DEBUG _restoreOnboardingState: done, onboardingCompleted=${SharedPreferencesUtil().onboardingCompleted}',
        );
      }
    } catch (e) {
      print('DEBUG _restoreOnboardingState: error=$e');
    }
  }

  Future<void> updateGivenName(String fullName) async {
    try {
      SharedPreferencesUtil().givenName = fullName.split(' ')[0];
      if (fullName.split(' ').length > 1) {
        SharedPreferencesUtil().familyName = fullName.split(' ').sublist(1).join(' ');
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
    try {
      final state = _generateState();
      const redirectUri = 'omi://auth/callback';

      Logger.debug('Starting OAuth linking flow for provider: $provider');

      final authUrl = '${Env.apiBaseUrl}v1/auth/authorize'
          '?provider=$provider'
          '&redirect_uri=${Uri.encodeComponent(redirectUri)}'
          '&state=$state';

      Logger.debug('Authorization URL: $authUrl');

      final launched = await launchUrl(Uri.parse(authUrl), mode: LaunchMode.inAppBrowserView);

      if (!launched) {
        throw Exception('Failed to launch authentication URL');
      }

      // Listen for the callback URL using app_links
      final appLinks = AppLinks();
      late StreamSubscription linkSubscription;
      final completer = Completer<String>();

      linkSubscription = appLinks.uriLinkStream.listen(
        (Uri uri) {
          Logger.debug('Received callback URI: $uri');
          if (uri.scheme == 'omi' && uri.host == 'auth' && uri.path == '/callback') {
            linkSubscription.cancel();
            completer.complete(uri.toString());
          }
        },
        onError: (error) {
          Logger.debug('App link error: $error');
          linkSubscription.cancel();
          completer.completeError(error);
        },
      );

      final result = await completer.future.timeout(
        const Duration(minutes: 5),
        onTimeout: () {
          linkSubscription.cancel();
          throw Exception('Authentication timeout');
        },
      );

      final uri = Uri.parse(result);
      final code = uri.queryParameters['code'];
      final returnedState = uri.queryParameters['state'];

      if (code == null) {
        throw Exception('No authorization code received');
      }

      if (returnedState != state) {
        throw Exception('Invalid state parameter');
      }

      // Exchange the code for OAuth credentials
      final oauthCredentials = await _exchangeCodeForOAuthCredentials(code, redirectUri);

      if (oauthCredentials == null) {
        throw Exception('Failed to exchange code for OAuth credentials');
      }

      // Sign in with the OAuth credentials
      final credential = await _signInWithOAuthCredentials(oauthCredentials);

      // Update user preferences after successful linking
      await _updateUserPreferences(credential, provider);

      Logger.debug('Account linking successful');
      return credential;
    } catch (e) {
      Logger.debug('OAuth linking error: $e');
      Logger.handle(e, StackTrace.current, message: 'Account linking failed');
      rethrow;
    }
  }

  Future<UserCredential?> linkWithGoogle() async {
    return await linkWithProvider('google');
  }

  Future<UserCredential?> linkWithApple() async {
    return await linkWithProvider('apple');
  }
}
