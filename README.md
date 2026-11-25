# BreakCheck

**Know what breaks before you break it.**

Find out which files depend on a file or folder before you delete, move, or rename it. BreakCheck runs locally and never modifies your scanned files.

[![Download for Windows](https://img.shields.io/badge/Download%20for%20Windows-Setup.exe-0078D4?style=for-the-badge&logo=windows)](https://github.com/PCTestAdmin/BreakCheck/releases/latest/download/BreakCheck-Setup.exe)

[Portable ZIP](https://github.com/PCTestAdmin/BreakCheck/releases/latest/download/BreakCheck-Portable.zip) · [All releases](https://github.com/PCTestAdmin/BreakCheck/releases)

## Installation

**Windows 10/11 (64-bit):** Download and run the installer. No Python or administrator rights required. For the portable version, extract the ZIP and open `BreakCheck.exe`.

If the installer is not available yet, [download the source ZIP](https://github.com/PCTestAdmin/BreakCheck/archive/refs/heads/main.zip), extract it and double-click `Start-BreakCheck.cmd`. The launcher detects Python or offers to install it.

Windows binaries are unsigned. [Checksums](https://github.com/PCTestAdmin/BreakCheck/releases/latest/download/SHA256SUMS.txt) are included with published packages.

## How to use

1. Select a folder to scan.
2. Select the file or folder you want to delete, move or rename.
3. Choose the operation and click **Analyze impact**.

Review the affected files, dependency graph and scan coverage before making changes. You can also enable the optional **Inspect with BreakCheck** File Explorer context menu during installation.

## Features

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
