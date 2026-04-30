param(
    [ValidateSet("ios", "android")]
    [string]$Platform = "android"
)

flutter clean
flutter pub get
dart run build_runner build

if ($Platform -eq "ios") {
    flutter build ios --release --flavor prod
} else {
    flutter build appbundle --release --flavor prod
    flutter build apk --release --flavor prod
}
