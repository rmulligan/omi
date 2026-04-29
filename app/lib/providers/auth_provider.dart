import 'dart:async';
import 'package:flutter/material.dart';
import 'package:omi/services/auth_service.dart';

class AuthProvider extends ChangeNotifier {
  bool _isAuthenticated = false;
  bool _loading = false;

  bool get isAuthenticated => _isAuthenticated;
  bool get loading => _loading;

  bool get isSignedIn => _isAuthenticated;

  AuthProvider() {
    _isAuthenticated = AuthService.instance.isSignedIn();
  }

  Future<void> signInWithGoogle(VoidCallback onSuccess) async {
    await AuthService.instance.signInWithGoogleMobile();
    _isAuthenticated = true;
    notifyListeners();
    onSuccess();
  }

  Future<void> signInWithApple(VoidCallback onSuccess) async {
    await AuthService.instance.signInWithAppleMobile();
    _isAuthenticated = true;
    notifyListeners();
    onSuccess();
  }

  Future<void> onAppleSignIn(VoidCallback onSuccess) async {
    _loading = true;
    notifyListeners();
    await AuthService.instance.signInWithAppleMobile();
    _isAuthenticated = true;
    _loading = false;
    notifyListeners();
    onSuccess();
  }

  Future<void> onGoogleSignIn(VoidCallback onSuccess) async {
    _loading = true;
    notifyListeners();
    await AuthService.instance.signInWithGoogleMobile();
    _isAuthenticated = true;
    _loading = false;
    notifyListeners();
    onSuccess();
  }

  void openPrivacyPolicy() {
    // Stub: in production this opens the privacy policy URL
  }

  void openTermsOfService() {
    // Stub: in production this opens the terms of service URL
  }

  Future<void> signOut() async {
    await AuthService.instance.signOut();
    _isAuthenticated = false;
    notifyListeners();
  }

  Future<void> restoreOnboardingState() async {
    await AuthService.instance.restoreOnboardingState();
  }
}
