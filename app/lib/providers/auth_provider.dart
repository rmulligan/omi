import 'dart:async';
import 'package:flutter/material.dart';
import 'package:omi/services/auth_service.dart';

class AuthProvider extends ChangeNotifier {
  bool _isAuthenticated = false;

  bool get isAuthenticated => _isAuthenticated;

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

  Future<void> signOut() async {
    await AuthService.instance.signOut();
    _isAuthenticated = false;
    notifyListeners();
  }

  Future<void> restoreOnboardingState() async {
    await AuthService.instance.restoreOnboardingState();
  }
}
