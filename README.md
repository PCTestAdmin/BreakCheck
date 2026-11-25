# BreakCheck

**Know what breaks before you break it.**

A local file safety assistant. Monitor project changes, detect previously known links that break after files move or disappear, find duplicate files, and check what may break before reorganizing a folder. BreakCheck never modifies scanned files.

[![Download for Windows](https://img.shields.io/badge/Download%20for%20Windows-0078D4?style=for-the-badge&logo=windows)](https://github.com/PCTestAdmin/BreakCheck/releases/latest/download/BreakCheck-Setup.exe)

[Windows installer releases](https://github.com/PCTestAdmin/BreakCheck/releases) · [Build status](https://github.com/PCTestAdmin/BreakCheck/actions/workflows/windows.yml)

## Installation

**Windows:** Download and run the [installer](https://github.com/PCTestAdmin/BreakCheck/releases/latest/download/BreakCheck-Setup.exe), or extract the [portable ZIP](https://github.com/PCTestAdmin/BreakCheck/releases/latest/download/BreakCheck-Portable.zip). Windows binaries are unsigned. The [latest release](https://github.com/PCTestAdmin/BreakCheck/releases) may lag behind the source.

**From source:** [Download the ZIP](https://github.com/PCTestAdmin/BreakCheck/archive/refs/heads/main.zip), extract it, then open `Start-BreakCheck.cmd`. Python is required for the source version; optional tray and event features require `pip install '.[windows]'` on Windows.

## How to use

**Monitor a folder:** In Overview, select a project folder and click **Start monitoring**. BreakCheck remembers the folder across launches. On Windows, closing the window hides it in the notification area; use the tray menu to quit. Enable **Start with Windows** in the packaged app if desired. New broken links trigger Windows notifications when enabled.

**Check a drive:** Select a drive root and click **Check now** for a bounded storage overview and the largest observed files. System folders and inaccessible entries are skipped and listed under Scan coverage. Continuous monitoring requires a project folder. No dependency alerts are calculated for a drive overview.

**Find duplicates:** Click **Find duplicates** to compare file contents and list matching copies by group. Nothing is deleted.

**Before moving or deleting:** Open Impact analysis, select a target, choose the operation and click **Analyze impact**. Review the results and coverage. Windows setup also offers an optional **Inspect with BreakCheck** Explorer context menu.

## Features

- Safety Center with a persistent local index, change history and after-the-fact broken-link alerts.
- Duplicate finder using SHA-256 content hashes; excludes hard links.
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

Monitoring is opt-in and runs while the desktop process or terminal watcher is alive. It uses optional filesystem events with periodic full reconciliation; if events are unavailable it checks every 60 seconds. It does not intercept or prevent Windows file operations, back up files or repair links. It detects changes between snapshots, not every filesystem event; possible moves are inferred from matching metadata. Only previously observed references whose source metadata is unchanged are flagged as broken. The first scan cannot find historical breakage. Incomplete inventory scans preserve the previous baseline and do not generate deletion alerts. Scans are capped at 100,000 files; duplicate hashing has a 4 GiB per-run budget. Reported duplicate sizes are logical file sizes, not guaranteed reclaimable disk space.

The local SQLite database stores paths, file metadata, observed dependencies and up to 1,000 recent events per monitored folder (no file contents). On Windows it lives at `%LOCALAPPDATA%/BreakCheck/safety.sqlite3`; close the app before removing it to clear history. Choose project folders outside the database directory; scanning a folder that contains this directory is not supported for monitoring. No automatic startup unless explicitly enabled, cloud upload or system-wide monitoring.

## Linux / terminal sessions

Python 3.10+ is required; Tk is not needed for terminal use. Starting with v0.5.0, published releases also include a single-file `BreakCheck.pyz` archive (run `python3 BreakCheck.pyz watch /path/to/project`). From the extracted source folder:

```sh
python3 -m breakcheck watch /path/to/project
python3 -m breakcheck duplicates /path/to/project
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
