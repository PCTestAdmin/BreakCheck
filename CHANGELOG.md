# Changelog

## 0.7.0

- Smart Recovery workspace with manual or opt-in automatic bounded local content versions and no-overwrite integrity-checked restoration.
- Reference-aware duplicate review, including incoming-reference counts, coverage and keep/review hints.
- Headless recovery capture/list/restore commands and optional `watch --backup`.
- Seven additional unit tests and expanded Windows GUI/CLI and Linux zipapp smoke tests, including no-overwrite recovery.

## 0.6.0

- Redesigned desktop workspace with sidebar navigation, overview metrics, separated impact analysis, and a refined light/dark appearance.
- Bounded whole-drive storage overview and largest-file list without traversing protected system directories.
- Report inaccessible folders and scan limits as partial coverage instead of aborting; preserve the previous monitoring baseline and suppress unsupported alerts.
- Add regression tests for permission-denied traversal, file limits, largest-file previews and inaccessible link targets; expand GUI smoke tests for the new navigation.

## 0.5.0

- Windows notification-area integration, optional per-user startup and new broken-link notifications.
- Remember the opted-in desktop monitor folder and notification preference across launches.
- Optional native filesystem event wakeups with periodic reconciliation and dependency-free fallback.
- Headless multi-folder monitor, JSON lines, CLI duplicate search, portable Python zipapp and Linux user-service documentation.
- Single-instance Windows desktop behavior with Explorer launch forwarding.
- Five additional headless unit tests and expanded Windows and Linux package smoke tests.

## 0.4.1

- Close regression-test SQLite connections explicitly before temporary directory cleanup on Windows.

- Fix SQLite integer overflow on Windows by storing filesystem device identifiers as lossless prefixed text, compatible with existing snapshots.
- Add a regression test for unsigned 64-bit device IDs and legacy SQLite column affinity.

## 0.4.0

- Safety Center: opt-in periodic folder monitoring while the app is open.
- Persistent SQLite snapshots and file activity history, including possible moves.
- Alerts when previously observed dependencies disappear, with possible new location hints.
- SHA-256 duplicate finder with a bounded read budget and hard-link exclusion.
- Skip Windows reparse points in the dependency scanner.
- Seven additional unit tests and an expanded desktop self-test.

## 0.3.2

- Bound every Windows smoke-test process with a timeout and log each step.
- Catch windowed desktop self-test errors without modal dialogs and save diagnostic files.
- Preserve installer and uninstaller diagnostics as CI artifacts; cancel obsolete Windows builds.
- Keep release publication gated on successful package tests.

## 0.3.1

- Stable direct download links for the latest Windows installer and portable archive.
- Shorter installation wizard, desktop shortcut selected by default, and launch on completion.
- Double-click source launcher with Python detection and optional user-approved Python installation via WinGet.
- Windows CI checks the source launcher and publishes stable asset names only after package smoke tests pass.
- English installation instructions, update and uninstall guidance at the top of the README.

## 0.3.0

- Interactive, bounded dependency graph using observed references, with clickable nodes.
- Light and dark desktop themes.
- Read-only candidate media inventory in the desktop interface and CLI.
- SVG, Wavefront OBJ/MTL and experimental Premiere XML media path adapters with bounded reads.
- Expanded GUI smoke test and adapter/inventory/graph unit tests.

## 0.2.0

- Windows x64 standalone GUI and CLI build recipes using PyInstaller.
- Per-user Inno Setup installer with optional desktop shortcut and File Explorer integration.
- Portable ZIP and SHA-256 checksum manifest.
- Desktop `--inspect` and `--root` launch options, plus a GUI smoke test.
- Preserve a preselected target when widening the scan scope.
- Automated package builds, installation and uninstall smoke tests, and versioned GitHub release publication after a successful build.
- Six additional unit tests for launch path handling.

## 0.1.0

- Initial read-only static dependency scanner, Tk desktop application, CLI, JSON export, and delete/move/rename simulation.
