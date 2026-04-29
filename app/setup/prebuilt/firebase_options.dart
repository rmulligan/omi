// Stubbed Firebase options - Firebase was stripped from the fork.
// ignore_for_file: type=lint
import 'package:flutter/foundation.dart' show defaultTargetPlatform, kIsWeb, TargetPlatform;

// Lightweight placeholder so the app can compile without firebase_core.
class _FakeFirebaseOptions {
  final String apiKey;
  final String appId;
  final String? messagingSenderId;
  final String? projectId;
  final String? storageBucket;
  final String? authDomain;
  final String? androidClientId;
  final String? iosClientId;
  final String? iosBundleId;

  const _FakeFirebaseOptions({
    this.apiKey = 'fake',
    this.appId = '1:1031333818730:android:de181b5b4681b7a1afb513',
    this.messagingSenderId = '1031333818730',
    this.projectId = 'based-hardware-dev',
    this.storageBucket = 'based-hardware-dev.firebasestorage.app',
    this.authDomain,
    this.androidClientId,
    this.iosClientId,
    this.iosBundleId,
  });
}

class DefaultFirebaseOptions {
  static _FakeFirebaseOptions get currentPlatform {
    if (kIsWeb) {
      return web;
    }
    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return android;
      case TargetPlatform.iOS:
        return ios;
      case TargetPlatform.macOS:
        return macos;
      default:
        throw UnsupportedError('DefaultFirebaseOptions are not supported for this platform.');
    }
  }

  static const _FakeFirebaseOptions android = _FakeFirebaseOptions(
    apiKey: 'AIzaSy...3Dq0',
    appId: '1:1031333818730:android:de181b5b4681b7a1afb513',
    messagingSenderId: '1031333818730',
    projectId: 'based-hardware-dev',
    storageBucket: 'based-hardware-dev.firebasestorage.app',
  );

  static const _FakeFirebaseOptions ios = _FakeFirebaseOptions(
    apiKey: 'AIzaSy...vcqM',
    appId: '1:1031333818730:ios:3bea63d8e4f41dbfafb513',
    messagingSenderId: '1031333818730',
    projectId: 'based-hardware-dev',
    storageBucket: 'based-hardware-dev.firebasestorage.app',
    androidClientId: '1031333818730-1cgqp3jc5p8n2rk467pl4t56qc4lnnbr.apps.googleusercontent.com',
    iosClientId: '1031333818730-dusn243nct6i5rgfpfkj5mchuj1qnmde.apps.googleusercontent.com',
    iosBundleId: 'com.friend-app-with-wearable.ios12.development',
  );

  static const _FakeFirebaseOptions web = _FakeFirebaseOptions(
    apiKey: 'AIzaSy...ZI1w',
    appId: '1:1031333818730:web:e1b83d713c04245cafb513',
    messagingSenderId: '1031333818730',
    projectId: 'based-hardware-dev',
    storageBucket: 'based-hardware-dev.firebasestorage.app',
    authDomain: 'based-hardware-dev.firebaseapp.com',
  );

  static const _FakeFirebaseOptions macos = _FakeFirebaseOptions(
    apiKey: 'AIzaSy...vcqM',
    appId: '1:1031333818730:ios:3bea63d8e4f41dbfafb513',
    messagingSenderId: '1031333818730',
    projectId: 'based-hardware-dev',
    storageBucket: 'based-hardware-dev.firebasestorage.app',
    androidClientId: '1031333818730-1cgqp3jc5p8n2rk467pl4t56qc4lnnbr.apps.googleusercontent.com',
    iosClientId: '1031333818730-dusn243nct6i5rgfpfkj5mchuj1qnmde.apps.googleusercontent.com',
    iosBundleId: 'com.friend-app-with-wearable.ios12.development',
  );
}
