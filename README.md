# BreakCheck

**Know what breaks before you break it.**

A local file safety assistant. Monitor project changes, detect previously known links that break after files move or disappear, find duplicate files, and check what may break before reorganizing a folder. Scans never modify source files; recovery writes a new file only on explicit request.

[![Download for Windows](https://img.shields.io/badge/Download%20for%20Windows-0078D4?style=for-the-badge&logo=windows)](https://github.com/PCTestAdmin/BreakCheck/releases/latest/download/BreakCheck-Setup.exe)

[Windows installer releases](https://github.com/PCTestAdmin/BreakCheck/releases) · [Build status](https://github.com/PCTestAdmin/BreakCheck/actions/workflows/windows.yml)

## Installation

**Windows:** Download and run the [installer](https://github.com/PCTestAdmin/BreakCheck/releases/latest/download/BreakCheck-Setup.exe), or extract the [portable ZIP](https://github.com/PCTestAdmin/BreakCheck/releases/latest/download/BreakCheck-Portable.zip). Windows binaries are unsigned. The [latest release](https://github.com/PCTestAdmin/BreakCheck/releases) may lag behind the source.

**From source:** [Download the ZIP](https://github.com/PCTestAdmin/BreakCheck/archive/refs/heads/main.zip), extract it, then open `Start-BreakCheck.cmd`. Python is required for the source version; optional tray and event features require `pip install '.[windows]'` on Windows.

## How to use

**Monitor a folder:** In Overview, select a project folder and click **Start monitoring**. BreakCheck remembers the folder across launches. On Windows, closing the window hides it in the notification area; use the tray menu to quit. Enable **Start with Windows** in the packaged app if desired. New broken links trigger Windows notifications when enabled.

**Check a drive:** Select a drive root and click **Check now** for a bounded storage overview and the largest observed files. System folders and inaccessible entries are skipped and listed under Scan coverage. Continuous monitoring requires a project folder. No dependency alerts are calculated for a drive overview.

**Find duplicates:** Compare file contents by SHA-256, see detected incoming references per copy and review cleanup candidates. No detected links do not prove safety. Nothing is deleted.

**Recover a file:** Open Recovery, capture a project manually or opt in to automatic versions while monitoring. Select an earlier version and restore it to a new path. Existing files are never overwritten.

**Before moving or deleting:** Open Impact analysis, select a target, choose the operation and click **Analyze impact**. Review the results and coverage. Windows setup also offers an optional **Inspect with BreakCheck** Explorer context menu.

## Features

- Safety Center with a persistent local index, change history and after-the-fact broken-link alerts.
- Reference-aware SHA-256 duplicate finder; excludes hard links.
- Opt-in local version history and integrity-checked copy-out recovery.
- Read-only delete, move and rename simulations.
- Direct and indirect dependency detection with an interactive graph.
- Media files with no detected incoming references.
- Dark mode, JSON reports and a command-line interface.
- Local processing, no account or cloud required.

## Supported formats

| Format | References detected |
| --- | --- |
| HTML, CSS, Markdown, JSON | Local file links and paths |
| Word, Excel, PowerPoint (Open XML) | External file relationships |
| SVG | Linked files |
| OBJ / MTL | Material libraries and basic texture paths |
| Premiere Pro | Experimental media-path detection |

## Limitations

BreakCheck is a static analyzer, not a guarantee that deleting a file is safe. It detects supported, existing references within the selected scan folder. Dynamic links, unsupported formats and references outside that folder may be missed. Files listed as unreferenced may still be in use. Review warnings, scan trusted folders and keep backups.

Monitoring is opt-in and runs while the desktop process or terminal watcher is alive. It uses optional filesystem events with periodic full reconciliation; if events are unavailable it checks every 60 seconds. It does not intercept or prevent Windows file operations or repair links. It detects changes between snapshots, not every filesystem event; possible moves are inferred from matching metadata. Only previously observed references whose source metadata is unchanged are flagged as broken. The first scan cannot find historical breakage. Incomplete inventory scans preserve the previous baseline and do not generate deletion alerts. Scans are capped at 100,000 files; duplicate hashing has a 4 GiB per-run budget. Reported duplicate sizes are logical file sizes, not guaranteed reclaimable disk space.

The local SQLite database stores paths, file metadata, observed dependencies and up to 1,000 recent events per monitored folder (no file contents). On Windows it lives at `%LOCALAPPDATA%/BreakCheck/safety.sqlite3`; close the app before removing it to clear history. Choose project folders outside the database directory; scanning a folder that contains this directory is not supported for monitoring. No automatic startup unless explicitly enabled, cloud upload or system-wide monitoring.

### Recovery limits

Recovery is disabled by default. The separate `recovery.sqlite3` stores file contents locally, unencrypted by BreakCheck. The default total content budget is 256 MiB (configurable from 1–4096 MiB); SQLite overhead is extra. Individual files are limited to 16 MiB, with a 128 MiB read budget per capture and 20,000 versions in total. A full vault stops accepting new versions; old versions are never automatically pruned. Close all BreakCheck processes before manually removing the recovery database. Keep independent backups: files lost before a successful capture or between checks cannot be recovered. Restore verifies SHA-256 and atomically creates a new file using a hard link to a staged copy; the destination filesystem must support hard links. No existing file is replaced.

## Linux / terminal sessions

Python 3.10+ is required; Tk is not needed for terminal use. Starting with v0.5.0, published releases also include a single-file `BreakCheck.pyz` archive (run `python3 BreakCheck.pyz watch /path/to/project`). From the extracted source folder:

```sh
python3 -m breakcheck watch /path/to/project
python3 -m breakcheck duplicates /path/to/project
python3 -m breakcheck recovery capture /path/to/project
python3 -m breakcheck recovery list
python3 -m breakcheck recovery restore 1 /path/to/new-file
```

Use `--once --json` for a single machine-readable snapshot. Multiple paths are supported by `watch`. Install the optional event backend with `python3 -m pip install '.[watch]'` in a virtual environment, or use the dependency-free polling mode. For persistent user services and IGEL/SSH deployment, see [Headless monitoring](docs/headless.md).

## Run from source

Requires Python 3.10+ with Tk (Windows, macOS or Linux). From the project directory:

```sh
python -m breakcheck gui
```

Try the CLI with the bundled demo:

```sh
python -m breakcheck check examples/demo assets/logo.svg
```

The demo reports three direct references. Use `python -m breakcheck --help` for more commands.

[Build instructions](packaging/README.md) · [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md) · [MIT License](LICENSE)
