# BreakCheck

**Know what breaks before you break it.**

A local file safety assistant. Monitor project changes, detect previously known links that break after files move or disappear, find duplicate files, and check what may break before reorganizing a folder. BreakCheck never modifies scanned files.

[![Download for Windows](https://img.shields.io/badge/Download%20for%20Windows-0078D4?style=for-the-badge&logo=windows)](https://github.com/PCTestAdmin/BreakCheck/archive/refs/heads/main.zip)

[Windows installer releases](https://github.com/PCTestAdmin/BreakCheck/releases) · [Build status](https://github.com/PCTestAdmin/BreakCheck/actions/workflows/windows.yml)

## Installation

**Available now — Windows:** Download the ZIP above, extract it and double-click `Start-BreakCheck.cmd`. It detects Python or offers to install it.

**Standalone installer:** When a Windows release is published, download `BreakCheck-Setup.exe` from [Releases](https://github.com/PCTestAdmin/BreakCheck/releases). No separate Python installation is needed. The portable package is also published there. Windows binaries are unsigned.

## How to use

**Monitor a folder:** Select a project folder and click **Start monitoring** in the Safety Center. The first scan creates a baseline; subsequent checks run every 60 seconds after the previous check completes while the app is open. Previously known broken links and recent file changes appear in the dashboard. Stop at any time.

**Find duplicates:** Click **Find duplicates** to compare file contents and list matching copies by group. Nothing is deleted.

**Before moving or deleting:** Select a target, choose the operation and click **Analyze impact**. Review the results and coverage. Windows setup also offers an optional **Inspect with BreakCheck** Explorer context menu.

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

Monitoring is opt-in and only runs while the app is open. It does not intercept or prevent Windows file operations, back up files or repair links. It detects changes between snapshots, not every filesystem event; possible moves are inferred from matching metadata. Only previously observed references whose source metadata is unchanged are flagged as broken. The first scan cannot find historical breakage. Scans are capped at 100,000 files; duplicate hashing has a 4 GiB per-run budget. Reported duplicate sizes are logical file sizes, not guaranteed reclaimable disk space.

The local SQLite database stores paths, file metadata, observed dependencies and up to 1,000 recent events per monitored folder (no file contents). On Windows it lives at `%LOCALAPPDATA%/BreakCheck/safety.sqlite3`; close the app before removing it to clear history. Choose project folders outside the database directory; scanning a folder that contains this directory is not supported for monitoring. No automatic startup, cloud upload or system-wide monitoring.

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
