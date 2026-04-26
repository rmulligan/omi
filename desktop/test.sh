#!/bin/bash
# Desktop test runner — runs both Rust backend and Swift app tests.
# Usage: cd desktop && bash test.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Rust Backend Tests ==="
cd "$SCRIPT_DIR/Backend-Rust"
cargo test
echo ""

echo "=== Swift App Tests ==="
cd "$SCRIPT_DIR"
# Skip test suites that trigger FirebaseApp.configure() — unavailable in the
# headless test environment (pre-existing, not PR-related). These suites
# reference singletons (TasksStore.shared, CrispManager, MemoriesViewModel)
# that pull in Firebase Auth at init time.
xcrun swift test --package-path Desktop \
  --skip CrispManagerLifecycleTests \
  --skip MemoriesViewModelObserverTests \
  --skip TasksStoreObserverTests
echo ""

echo "All desktop tests passed."
