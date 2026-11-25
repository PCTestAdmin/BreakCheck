<div align="center">

# BreakCheck

**Know what breaks before you break it.**

A local, read-only file dependency inspector for Windows, macOS and Linux.

[![Download for Windows](https://img.shields.io/badge/Download%20for%20Windows-Setup.exe-0078D4?style=for-the-badge&logo=windows)](https://github.com/PCTestAdmin/BreakCheck/releases/latest/download/BreakCheck-Setup.exe)

[Portable ZIP](https://github.com/PCTestAdmin/BreakCheck/releases/latest/download/BreakCheck-Portable.zip) · [All releases](https://github.com/PCTestAdmin/BreakCheck/releases) · [Installation help](#windows-downloads)

![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg) ![Status: MVP](https://img.shields.io/badge/status-MVP-orange)

</div>

## Why BreakCheck?

Before deleting a shared asset, renaming a file, or reorganizing a project folder, find out which other files may stop working. BreakCheck indexes supported file references, simulates changes without performing them, and reports direct and potential indirect impact.

**No account, cloud service, AI API, or third-party runtime dependency.** Scans run locally. Reports may contain sensitive local paths, so review them before sharing.

## Features

- Desktop interface with folder and file pickers, impact table, and scan coverage.
- Read-only delete, move, and rename simulations for files and directories.
- Direct references with source, target, evidence type, and line number where available.
- Potential indirect dependencies, including dependency cycles.
- JSON export and command-line interface for scripting.
- Bounded text and Office relationship reads; no macros or document code executed.

## New in v0.3.0

- Interactive impact graph: observed file-to-file links, red predicted breaks, clickable nodes and bounded display size.
- Light/dark desktop theme.
- Unreferenced media inventory, sorted by file size. Candidates are not verified unused or safe to delete; entry-point files and dynamically loaded assets can appear here.
- New adapters for SVG links, Wavefront OBJ material libraries and basic MTL texture maps, plus experimental plain/gzip Premiere Pro project media paths. Native Blender `.blend` parsing is not supported.
- CLI inventory: `python -m breakcheck inventory examples/demo --json` (or `BreakCheckCLI.exe inventory examples/demo`).

## Windows downloads

### Recommended: install in two steps

1. [**Download BreakCheck-Setup.exe**](https://github.com/PCTestAdmin/BreakCheck/releases/latest/download/BreakCheck-Setup.exe).
2. Double-click it, choose your optional shortcuts, then click **Install** and **Finish**.

BreakCheck opens when setup completes. Find it again in the Start menu or via the desktop shortcut. No Python, terminal, or administrator privileges required. Windows 10 (1809+) and Windows 11 x64 are the target platforms.

### Prefer no installation?

[Download BreakCheck-Portable.zip](https://github.com/PCTestAdmin/BreakCheck/releases/latest/download/BreakCheck-Portable.zip), extract the entire ZIP and double-click `BreakCheck.exe`. Both the desktop app and console CLI are included.

### Download not available yet?

The direct links work once a release with the named assets has successfully been published. Check [all releases](https://github.com/PCTestAdmin/BreakCheck/releases) or [Windows package builds](https://github.com/PCTestAdmin/BreakCheck/actions/workflows/windows.yml) if a download returns 404.

To run from source without typing commands, [download the source ZIP](https://github.com/PCTestAdmin/BreakCheck/archive/refs/heads/main.zip), extract it, then double-click `Start-BreakCheck.cmd`. It detects Python 3.10+ with Tk. If Python is missing, it offers to open the downloads page or install Python through Windows Package Manager with your consent. Python is only required for this fallback, not for the EXE installer.

### Updates, uninstall and security

- To update, download and run the newest setup EXE. The installer uses the same application ID and per-user installation directory.
- To uninstall, open Windows Settings > Apps > Installed apps and select BreakCheck.
- Enable optional Explorer integration during setup to inspect files and folders by right-clicking **Inspect with BreakCheck** (Windows 11: **Show more options**). The selected target is prefilled; choose a wider scan folder if necessary and click **Analyze impact**.
- Binaries are unsigned and may display a Windows SmartScreen warning. Verify downloads against the [SHA-256 checksums](https://github.com/PCTestAdmin/BreakCheck/releases/latest/download/SHA256SUMS.txt) and follow your organization's security policy.

## Quick start from source (developers)

Install Python 3.10 or newer. The desktop app also requires Tk, included in typical Windows and macOS Python installations; on Debian/Ubuntu install `python3-tk` if needed.

From the project directory:

```sh
python -m breakcheck gui
```

No package installation is needed to run from source. Optional installation:

```sh
python -m pip install .
breakcheck gui
```

Choose the folder to scan, then the file or folder to inspect. Select **Delete**, **Move**, or **Rename** and click **Analyze impact**. For move or rename, enter a new destination. Review the **Coverage & warnings** tab even when no dependencies are found.

### Try the bundled demo

```sh
python -m breakcheck check examples/demo assets/logo.svg
```

Expected: three direct references (HTML, CSS and JSON) and one potential indirect dependent (Markdown). The command exits with code 2 because potential impact was found. The SVG remains unchanged.

```sh
python -m breakcheck check examples/demo assets --operation rename --destination media
python -m breakcheck check examples/demo pages/index.html --operation move --destination archive/index.html
python -m breakcheck check examples/demo assets/logo.svg --json
```

Paths passed to `check` are relative to the scan root unless absolute. `--max-files` controls the traversal limit (default 100,000). CLI exit codes: 0 = no direct impacts detected; 1 = invalid input or fatal error; 2 = direct impacts detected. An exit code of 0 is **not** a guarantee that a change is safe, especially with incomplete coverage.

## Supported references

| Format | Detection |
| --- | --- |
| HTML (`.html`, `.htm`) | Local `href`, `src`, `poster`, `data` attributes |
| CSS (`.css`) | Local `url()` and quoted `@import` |
| Markdown (`.md`, `.markdown`) | Common inline links/images and reference definitions |
| JSON (`.json`) | Heuristic path-like string values resolving to existing files |
| Office Open XML (`.xlsx`, `.docx`, `.pptx`, macro-enabled variants) | Local external relationship targets in `.rels` entries, resolved relative to the document directory |
| SVG (`.svg`) | XML `href` and `xlink:href` links |
| Wavefront (`.obj`, `.mtl`) | Simple material-library and texture-map paths; texture options and multiple libraries per line are not parsed |
| Adobe Premiere Pro (`.prproj`) | Experimental UTF-8 plain/gzip XML media path fields; stored paths may be stale; no timeline/object graph interpretation |

## Important limitations

BreakCheck is an early-stage static analyzer, not a deletion-safety guarantee. It only indexes existing references inside the chosen scan directory. Dependencies outside the scan root, dynamic references, unsupported files, symbolic-link aliases, junctions, server-root-relative web paths, HTML base URLs, CSS embedded in HTML, `srcset`, complex Markdown syntax, and some Office-specific links may be missed. Relative paths in JSON or Office files may use application-specific semantics; findings can be false positives. Only UTF-8 text is supported. No file watcher is active; rescan after changes.

The tool skips `.git`, `.venv`, `node_modules`, `__pycache__`, symlink/junction directories, and non-regular files. Text files are capped at 4 MiB; Office relationship parts have per-entry and aggregate limits. Unsupported formats and skipped files are reported as coverage limitations. This is not a sandbox for hostile or concurrently modified directory trees; scan trusted local folders only.

Premiere XML expansion is capped at 32 MiB. SVG/OBJ/MTL adapters use a 4 MiB limit. The asset inventory only covers selected media extensions, does not infer usage from applications, and excludes paths under detected directory references. The graph shows up to 60 nodes and 120 observed links; the impact table remains the full detected result. There is no persistent cache, and every scan is fresh.

The simulator does not execute file operations, validate that a destination can be created, rewrite references, or guarantee application behavior. It does not consider all filesystem aliasing or case-only rename semantics. A move or rename may also affect files outside the selected directory. Export writes a new JSON file only when explicitly requested and refuses to overwrite an existing file.

**No detected references does not prove safety. Keep backups.**

## Development

```sh
python -m unittest discover -s tests -v
python -m compileall -q breakcheck
```

GitHub Actions runs tests on Windows, macOS, and Linux. The Windows package workflow builds both executables with PyInstaller and compiles a per-user installer with Inno Setup 6. It smoke-tests the desktop, CLI, installation, Explorer registration and uninstallation before publishing a new version on `main`. Existing versioned releases are not overwritten.

To build on a Windows x64 machine with Python 3.12 and Inno Setup 6 installed, run `./packaging/build-windows.ps1` in PowerShell. Outputs are written to `release/`. On a disposable test machine, run `./packaging/smoke-windows.ps1` to validate installation and removal. See [packaging/README.md](packaging/README.md).

## Roadmap

- [x] Windows Explorer context menu and standalone installer build pipeline (v0.2.0)
- [x] SVG, Wavefront OBJ/MTL and experimental Premiere Pro project adapter (v0.3.0)
- [ ] Native Blender project files, additional Adobe formats, Windows shortcuts
- [ ] Persistent index, incremental scans, and scan cancellation
- [x] Interactive dependency graph and media inventory (v0.3.0)
- [ ] Improved parser coverage and graph filtering
- [ ] Opt-in transactional reference rewriting with backups and undo

Contributions are welcome. Please include a minimal reproducible example and tests when adding a format adapter.

## License

MIT. See [LICENSE](LICENSE).
