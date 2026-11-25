# BreakCheck

**Know what breaks before you break it.**

A local file safety assistant. Monitor project changes, detect previously known links that break after files move or disappear, find duplicate files, and check what may break before reorganizing a folder. Scans never modify source files. Recovery and link repair require explicit user actions.

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

**Repair a link:** Double-click a broken link in Overview or open Link repair. Check the suggested replacement or choose one manually, review the diff, then confirm. Repair history allows undo if the repaired file has not changed.

**Explore storage:** Open Storage, select a folder or drive, and scan. Switch between folder, file-type and modification-age distributions; click folder bars to drill down. Review the largest files and filter candidates by size and time since modification. Double-click a file to open Impact analysis. Export JSON or cancel a scan at any time.

**Guard a file operation:** Open Protection or right-click a file in Explorer and choose **Guarded move with BreakCheck** (optional installer integration). Set the project and destination, check risks, then explicitly confirm. Local block/warn rules apply only to this guided workflow. Delete review is advisory; BreakCheck does not delete files. Optional startup update checks query GitHub for release metadata only.

**Monitor multiple devices:** Deploy the optional self-hosted Fleet collector, enroll each endpoint with its own token, and run the headless fleet agent. The authenticated dashboard shows latest aggregate counts, scan coverage and last report times. No file paths or content are submitted. See [Fleet deployment](docs/fleet.md).

## Features

- Safety Center with a persistent local index, change history and after-the-fact broken-link alerts.
- Reference-aware SHA-256 duplicate finder; excludes hard links.
- Metadata-only storage intelligence with folder drill-down, file type and age distributions, review filters and JSON export.
- Opt-in local version history and integrity-checked copy-out recovery.
- Previewed link repair and persistent undo for supported UTF-8 HTML and JSON relative paths.
- Read-only delete, move and rename simulations.
- Guarded same-volume single-file moves and renames with block/warn rules, no destination overwrite and explicit confirmation.
- Optional startup release checks; no automatic installation.
- Optional self-hosted fleet monitoring for Windows and Linux, authenticated web dashboard and JSON status API.
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

Monitoring is opt-in and runs while the desktop process or terminal watcher is alive. It uses optional filesystem events with periodic full reconciliation; if events are unavailable it checks every 60 seconds. It does not intercept or prevent external file operations. Protection rules only govern the guarded move/rename workflow, not repair, recovery, Explorer, shell commands or other applications. Guarded moves require a trusted project and a regular single-link file with an existing same-volume destination directory inside the project. Linux requires filesystem support for atomic no-replace rename; unsupported systems refuse the move. Close external writers first; preflight checks are not a filesystem transaction. Delete checks never delete. Update checks are disabled by default, contact GitHub (IP address and ordinary HTTP metadata), and never download or execute an update. It detects changes between snapshots, not every filesystem event; possible moves are inferred from matching metadata. Only previously observed references whose source metadata is unchanged are flagged as broken. The first scan cannot find historical breakage. Incomplete inventory scans preserve the previous baseline and do not generate deletion alerts. Scans are capped at 100,000 files; duplicate hashing has a 4 GiB per-run budget. Reported duplicate sizes are logical file sizes, not guaranteed reclaimable disk space.

The local SQLite database stores paths, file metadata, observed dependencies and up to 1,000 recent events per monitored folder (no file contents). On Windows it lives at `%LOCALAPPDATA%/BreakCheck/safety.sqlite3`; close the app before removing it to clear history. Choose project folders outside the database directory; scanning a folder that contains this directory is not supported for monitoring. No automatic startup unless explicitly enabled, cloud upload or system-wide monitoring.

### Recovery limits

Recovery is disabled by default. The separate `recovery.sqlite3` stores file contents locally, unencrypted by BreakCheck. The default total content budget is 256 MiB (configurable from 1–4096 MiB); SQLite overhead is extra. Individual files are limited to 16 MiB, with a 128 MiB read budget per capture and 20,000 versions in total. A full vault stops accepting new versions; old versions are never automatically pruned. Close all BreakCheck processes before manually removing the recovery database. Keep independent backups: files lost before a successful capture or between checks cannot be recovered. Restore verifies SHA-256 and atomically creates a new file using a hard link to a staged copy; the destination filesystem must support hard links. No existing file is replaced.

### Link repair limits

Only literal quoted relative HTML link attributes and relative JSON string values in UTF-8 files up to 4 MiB are supported. HTML base URLs, complex URLs, absolute paths, symlinks, hard-linked sources and other formats are not automatically repaired. Move hints are inferred from history and must be verified. JSON strings may have other meanings, so review the diff. Close external editors and other processes that write the source before applying or undoing: atomic replacement is not a filesystem compare-and-swap and may change metadata, ownership, ACLs or extended attributes. The separate private `repairs.sqlite3` journal saves original and repaired contents (unencrypted, 128 MiB content budget, 1,000 entries); no automatic pruning. Undo refuses changed files. The journal is not a substitute for independent backups.

### Storage limits

Storage uses a single metadata traversal (no file-content hashing or dependency parsing) and defaults to 500,000 directory entries; CLI limits can be set from 1 to 2,000,000. Protected, excluded, linked and other-volume entries are skipped and coverage is reported as partial. Logical sizes count each observed hard link and may differ from actual allocated space; volume free space is a separate OS measurement. Modification age is not last-access age. Size and age are review hints, not proof that a file is unused. Results are not an atomic snapshot. No cleanup is automatic.

### Fleet limitations

Fleet is disabled unless explicitly launched. Agent IDs, version, folder/file/byte counts, known broken-link counts, coverage/error counts and report timing are sent to a server selected by the operator; the server and proxy can also see network metadata. Only the latest report per enrolled agent is retained. No file paths, names or contents are sent. Use dedicated agent state and HTTPS for network deployment. The small collector is intended for trusted, private environments behind a reverse proxy; it is not a hardened public SaaS or remote management platform. No remote commands, central policy enforcement, SSO or webhooks are implemented yet.

## Linux / terminal sessions

Python 3.10+ is required; Tk is not needed for terminal use. Starting with v0.5.0, published releases also include a single-file `BreakCheck.pyz` archive (run `python3 BreakCheck.pyz watch /path/to/project`). From the extracted source folder:

```sh
python3 -m breakcheck watch /path/to/project
python3 -m breakcheck duplicates /path/to/project
python3 -m breakcheck storage /path/to/project --json
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
