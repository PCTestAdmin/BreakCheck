# Changelog

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
