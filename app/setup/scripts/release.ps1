param(
    [ValidateSet("ios", "android")]
    [string]$Platform = "android",

    [ValidateSet("", "dev", "prod")]
    [string]$Flavor = ""
)

if ([string]::IsNullOrEmpty($Flavor)) {
    if ($Platform -eq "ios") {
        $Flavor = "dev"
    } else {
        $Flavor = "prod"
    }
}

flutter clean
flutter pub get
dart run build_runner build

if ($Platform -eq "ios") {
    flutter build ios --release --flavor $Flavor --no-codesign

    $ipaName = "Runner-$Flavor-sideload.ipa"
    $stagingDir = "build/ios/sideload"
    $ipaDir = "build/ios/ipa"

    Remove-Item -Recurse -Force $stagingDir -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force "$stagingDir/Payload", $ipaDir | Out-Null
    Copy-Item -Recurse "build/ios/iphoneos/Runner.app" "$stagingDir/Payload/Runner.app"
    Remove-Item -Force "$ipaDir/$ipaName" -ErrorAction SilentlyContinue

    Push-Location $stagingDir
    zip -qry "../ipa/$ipaName" Payload
    Pop-Location

    Write-Host "Sideloadly IPA: $ipaDir/$ipaName"
} else {
    flutter build appbundle --release --flavor $Flavor
    flutter build apk --release --flavor $Flavor
}
