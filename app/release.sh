#!/usr/bin/env bash
set -euo pipefail

platform="${1:-android}"

flutter clean
flutter pub get
dart run build_runner build

case "$platform" in
  ios)
    flutter build ios --release --flavor prod
    ;;
  android)
    flutter build appbundle --release --flavor prod
    flutter build apk --release --flavor prod
    ;;
  *)
    echo "Usage: bash release.sh [ios|android]" >&2
    exit 1
    ;;
esac
