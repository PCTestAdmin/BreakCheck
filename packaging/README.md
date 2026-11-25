# Windows packaging

Requirements: Windows x64, 64-bit Python 3.12, PowerShell, and Inno Setup 6. From the project root run `./packaging/build-windows.ps1`. Use `-Iscc 'C:\path\to\ISCC.exe'` if the compiler is installed in a custom location. PyInstaller is installed from the pinned build requirements. The script runs unit tests, builds separate desktop and CLI binaries, creates the setup EXE, packages the portable ZIP and writes SHA-256 checksums.

The installer is per-user and offers optional shortcuts and Explorer integration. The registry changes are scoped to BreakCheck's own verbs under HKCU. No service, scheduled task, PATH modification or automatic update agent is installed. Uninstall removes the app and its registered Explorer verbs. On Windows 11, the verb appears under Show more options.

Run `./packaging/smoke-windows.ps1` only on a disposable Windows test machine: it installs to a temporary path, tests both binaries and Explorer registration, then uninstalls. It is not intended for a machine with an existing BreakCheck installation.

The GitHub Actions workflow publishes the installer, portable archive and checksums for a new version only after successful smoke tests on main. Releases are immutable by convention: bump the package version and `breakcheck/__init__.py` before publishing a new build. No signing certificate is configured; the artifacts are unsigned.
