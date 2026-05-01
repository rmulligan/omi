import 'dart:ffi';
import 'dart:io';

import 'package:opus_flutter/opus_flutter.dart' as opus_flutter;

Future<DynamicLibrary> loadOpusLibrary() async {
  if (Platform.isLinux) {
    return _loadLinuxOpusLibrary();
  }

  return await opus_flutter.load() as DynamicLibrary;
}

DynamicLibrary _loadLinuxOpusLibrary() {
  final candidates = [
    'libopus.so.0',
    'libopus.so',
    '/lib/x86_64-linux-gnu/libopus.so.0',
    '/usr/lib/x86_64-linux-gnu/libopus.so.0',
  ];

  Object? lastError;
  for (final candidate in candidates) {
    try {
      return DynamicLibrary.open(candidate);
    } catch (error) {
      lastError = error;
    }
  }

  throw UnsupportedError('Unable to load libopus on Linux: $lastError');
}
