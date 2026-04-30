#!/usr/bin/env bash
set -euo pipefail

platform="${1:-android}"
flavor="${2:-}"

if [[ -z "$flavor" ]]; then
  if [[ "$platform" == "ios" ]]; then
    flavor="dev"
  else
    flavor="prod"
  fi
fi

create_sideload_ipa() {
  local ipa_name="Runner-${flavor}-sideload.ipa"
  local staging_dir="build/ios/sideload"
  local ipa_dir="build/ios/ipa"

  rm -rf "$staging_dir"
  mkdir -p "$staging_dir/Payload" "$ipa_dir"
  cp -R "build/ios/iphoneos/Runner.app" "$staging_dir/Payload/Runner.app"
  rm -f "$ipa_dir/$ipa_name"

  (
    cd "$staging_dir"
    zip -qry "../ipa/$ipa_name" Payload
  )

  echo "Sideloadly IPA: $ipa_dir/$ipa_name"
}

flutter clean
flutter pub get
dart run build_runner build

case "$platform" in
  ios)
    flutter build ios --release --flavor "$flavor" --no-codesign
    create_sideload_ipa
    ;;
  android)
    flutter build appbundle --release --flavor "$flavor"
    flutter build apk --release --flavor "$flavor"
    ;;
  *)
    echo "Usage: bash release.sh [ios|android] [dev|prod]" >&2
    exit 1
    ;;
esac
