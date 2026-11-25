<div align="center">

# BreakCheck

**Know what breaks before you break it.**

A local, read-only file dependency inspector for Windows, macOS and Linux.

![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg) ![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue) ![Status: MVP](https://img.shields.io/badge/status-MVP-orange)

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

## Quick start

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

## Important limitations

BreakCheck is an early-stage static analyzer, not a deletion-safety guarantee. It only indexes existing references inside the chosen scan directory. Dependencies outside the scan root, dynamic references, unsupported files, symbolic-link aliases, junctions, server-root-relative web paths, HTML base URLs, CSS embedded in HTML, `srcset`, complex Markdown syntax, and some Office-specific links may be missed. Relative paths in JSON or Office files may use application-specific semantics; findings can be false positives. Only UTF-8 text is supported. No file watcher is active; rescan after changes.

The tool skips `.git`, `.venv`, `node_modules`, `__pycache__`, symlink/junction directories, and non-regular files. Text files are capped at 4 MiB; Office relationship parts have per-entry and aggregate limits. Unsupported formats and skipped files are reported as coverage limitations. This is not a sandbox for hostile or concurrently modified directory trees; scan trusted local folders only.

The simulator does not execute file operations, validate that a destination can be created, rewrite references, or guarantee application behavior. It does not consider all filesystem aliasing or case-only rename semantics. A move or rename may also affect files outside the selected directory. Export writes a new JSON file only when explicitly requested and refuses to overwrite an existing file.

**No detected references does not prove safety. Keep backups.**

## Development

```sh
python -m unittest discover -s tests -v
python -m compileall -q breakcheck
```

The GitHub Actions workflow is configured to run tests on Windows, macOS, and Linux. It has not been run until this project is pushed to GitHub.

## Roadmap

- [ ] Windows Explorer context menu and standalone installer
- [ ] More format adapters: Blender, Adobe project files, Windows shortcuts
- [ ] Persistent index, incremental scans, and scan cancellation
- [ ] Dependency graph visualization and improved parser coverage
- [ ] Opt-in transactional reference rewriting with backups and undo

Contributions are welcome. Please include a minimal reproducible example and tests when adding a format adapter.

## License

MIT. See [LICENSE](LICENSE).
