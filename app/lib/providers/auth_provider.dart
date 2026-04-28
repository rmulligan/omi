import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/backend/http/api/apps.dart' as apps_api;
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/providers/base_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/platform/platform_service.dart';

class AuthenticationProvider extends BaseProvider {
  String? _uid;
  String? _email;
  String? _givenName;
  String? _authToken;
  bool _loading = false;
  final List<VoidCallback> _stateListeners = [];

  @override
  bool get loading => _loading;

  String? get uid => _uid;
  String? get email => _email;
  String? get givenName => _givenName;
  String? get authToken => _authToken;

  AuthenticationProvider() {
    _initAuth();
  }

  void _initAuth() {
    // Restore cached credentials
    _uid = SharedPreferencesUtil().uid;
    _email = SharedPreferencesUtil().email;
    _givenName = SharedPreferencesUtil().givenName;
    _authToken = SharedPreferencesUtil().authToken;
    Logger.debug(
      'DEBUG AuthProvider: Initial uid=$_uid, isSignedIn=${isSignedIn()}',
    );
  }

  void _onAuthStateChanged() {
    Logger.debug(
      'DEBUG AuthProvider: authStateChanges fired - uid=$_uid, isSignedIn=${isSignedIn()}',
    );
    notifyListeners();
  }

  bool isSignedIn() {
    return _uid != null && _uid!.isNotEmpty;
  }

  void setLoading(bool value) {
    _loading = value;
    notifyListeners();
  }

  Future<void> onGoogleSignIn(Function() onSignIn) async {
    final useWebAuth = Env.useWebAuth;
    if (!loading) {
      setLoadingState(true);
      try {
        UserCredential? credential;
        if (PlatformService.isMobile && !useWebAuth) {
          credential = await AuthService.instance.signInWithGoogleMobile();
        } else {
          credential = await AuthService.instance.authenticateWithProvider('google');
        }
        if (credential != null && isSignedIn()) {
          _signIn(onSignIn);
        } else {
          AppSnackbar.showSnackbarError(
            globalNavigatorKey.currentContext?.l10n.authFailedToSignInWithGoogle ??
                'Failed to sign in with Google, please try again.',
          );
        }
      } catch (e, stackTrace) {
        print('DEBUG_AUTH: OAuth Google sign in error: $e');
        print('DEBUG_AUTH: Stack trace: $stackTrace');
        Logger.debug('OAuth Google sign in error: $e');
        AppSnackbar.showSnackbarError(
          globalNavigatorKey.currentContext?.l10n.authenticationFailed ?? 'Authentication failed. Please try again.',
        );
      }
      setLoadingState(false);
    }
  }

  Future<void> onAppleSignIn(Function() onSignIn) async {
    final useWebAuth = Env.useWebAuth;
    if (!loading) {
      setLoadingState(true);
      try {
        UserCredential? credential;
        if (PlatformService.isMobile && !useWebAuth && !Platform.isAndroid) {
          credential = await AuthService.instance.signInWithAppleMobile();
        } else {
          credential = await AuthService.instance.authenticateWithProvider('apple');
        }
        if (credential != null && isSignedIn()) {
          _signIn(onSignIn);
        } else {
          AppSnackbar.showSnackbarError(
            globalNavigatorKey.currentContext?.l10n.authFailedToSignInWithApple ??
                'Failed to sign in with Apple, please try again.',
          );
        }
      } catch (e) {
        Logger.debug('OAuth Apple sign in error: $e');
        AppSnackbar.showSnackbarError(
          globalNavigatorKey.currentContext?.l10n.authenticationFailed ?? 'Authentication failed. Please try again.',
        );
      }
      setLoadingState(false);
    }
  }

  Future<String?> _getIdToken() async {
    try {
      final token = await AuthService.instance.getIdToken();
      NotificationService.instance.saveNotificationToken();

      Logger.debug('Token: $token');
      return token;
    } catch (e, stackTrace) {
      AppSnackbar.showSnackbarError(
        globalNavigatorKey.currentContext?.l10n.authFailedToRetrieveToken ??
            'Failed to retrieve token, please try again.',
      );
      PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);

      return null;
    }
  }

  void _signIn(Function() onSignIn) async {
    String? token = await _getIdToken();

    if (token != null) {
      String newUid = _uid ?? '';
      SharedPreferencesUtil().uid = newUid;
      MixpanelManager().identify();
      onSignIn();
    } else {
      AppSnackbar.showSnackbarError(
        globalNavigatorKey.currentContext?.l10n.authUnexpectedError ?? 'Unexpected error signing in, please try again',
      );
    }
  }

  void openTermsOfService() {
    _launchUrl('https://www.omi.me/pages/terms-of-service');
  }

  void openPrivacyPolicy() {
    _launchUrl('https://www.omi.me/pages/privacy');
  }

  void _launchUrl(String url) async {
    final uri = Uri.tryParse(url);
    if (uri == null) {
      Logger.debug('Invalid URL');
      return;
    }

    await launchUrl(uri, mode: LaunchMode.inAppBrowserView);
  }

  Future<void> linkWithGoogle() async {
    setLoading(true);
    try {
      final result = await AuthService.instance.linkWithGoogle();
      if (result == null) {
        setLoading(false);
        return;
      }
    } catch (e) {
      AppSnackbar.showSnackbarError(
        globalNavigatorKey.currentContext?.l10n.authFailedToLinkGoogle ??
            'Failed to link with Google, please try again.',
      );
      rethrow;
    } finally {
      setLoading(false);
    }
  }

  Future<void> linkWithApple() async {
    setLoading(true);
    try {
      await AuthService.instance.linkWithApple();
    } catch (e) {
      print('Error linking with Apple: $e');
      AppSnackbar.showSnackbarError(
        globalNavigatorKey.currentContext?.l10n.authFailedToLinkApple ?? 'Failed to link with Apple, please try again.',
      );
      rethrow;
    } finally {
      setLoading(false);
    }
  }

  Future<bool> migrateAppOwnerId(String oldId) async {
    return await apps_api.migrateAppOwnerId(oldId);
  }
}

class UserCredential {
  final String? uid;
  final String? email;
  final String? displayName;

  UserCredential({this.uid, this.email, this.displayName});
}
