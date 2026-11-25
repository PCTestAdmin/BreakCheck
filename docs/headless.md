# Headless monitoring

No desktop, Tk, root privileges or cloud service required. Python 3.10+ with SQLite is needed. From v0.5.0 onward, download `BreakCheck.pyz` from the published release and run `python3 BreakCheck.pyz watch /path/to/project`; the examples below also work from an extracted source checkout.

## Linux / SSH

Extract the source archive into a user-owned directory, then run:

```sh
cd /path/to/BreakCheck
python3 -m breakcheck watch /path/to/project /path/to/other-project
python3 -m breakcheck watch /path/to/project --once --json
python3 -m breakcheck duplicates /path/to/project --json
```

Ctrl+C stops the watcher. Use `--poll` to force polling, or `--interval 120` for a longer reconciliation interval. Optional event support: create a virtual environment and install `'.[watch]'`.

To remember one default project, run `python3 -m breakcheck monitor-config --folder /path/to/project`, then `python3 -m breakcheck watch`. Clear it with `monitor-config --clear`. The desktop app shares this preference; stop desktop monitoring before using the CLI on the same project.

## Keep monitoring after logout

On Linux systems with systemd user services, from the source directory:

```sh
python3 -m venv ~/.local/share/breakcheck-venv
~/.local/share/breakcheck-venv/bin/pip install '.[watch]'
~/.local/share/breakcheck-venv/bin/python -m breakcheck monitor-config --folder /path/to/project
mkdir -p ~/.config/systemd/user
cp packaging/breakcheck.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now breakcheck.service
journalctl --user -u breakcheck.service -f
```

Stop and disable with `systemctl --user disable --now breakcheck.service`. To keep a user service running after logout, an administrator may need to enable lingering with `loginctl enable-linger USER`, subject to local policy. If systemd is unavailable, run the foreground command under the site's approved supervisor or persistent terminal multiplexer.

## IGEL OS

IGEL OS is a managed thin-client platform, not a general-purpose package installation target. No native IGEL app package is provided or certified. For an SSH or terminal session on a Linux server, run BreakCheck on that server. It sees only files accessible to that process, not arbitrary files on other endpoints or remote desktops.

For local execution, an administrator must provision Python 3.10+ with SQLite, the source files and a writable persistent data location through an approved custom application/partition. Example (replace both paths with provisioned locations):

```sh
cd /path/to/persistent/BreakCheck
BREAKCHECK_STATE_DIR=/path/to/persistent/state python3 -m breakcheck watch /path/to/project --poll
```

Do not modify the managed base OS or bypass restrictions. The administrator should configure any persistent service using supported IGEL mechanisms. See the [IGEL OS custom partition documentation](https://kb.igel.com/en/igel-os-base-system/12.7.5/custom-partition-in-igel-os-12) and [custom application documentation](https://kb.igel.com/en/igel-os-base-system/12.7.1/custom-application-in-igel-os-12).

## State and limitations

Set `BREAKCHECK_STATE_DIR` to an absolute writable directory outside all monitored folders to relocate the SQLite index and preferences. The default is `$XDG_DATA_HOME/BreakCheck` or `~/.local/share/BreakCheck` on Linux. State includes local paths, metadata and observed references, not file contents. Monitor only trusted directories; do not run multiple monitors for the same root. Native events are hints, not guaranteed records, and snapshots detect only previously observed broken references. No pre-deletion interception, backup or automatic repair.

## Optional file recovery

Use `watch /path/to/project --backup --quota-mib 256` to explicitly opt in to automatic file versions for that terminal process. Or use `recovery capture /path/to/project`, `recovery list`, and `recovery restore VERSION /path/to/new-file`. All commands also work with `python3 BreakCheck.pyz`. The recovery database contains unencrypted file content. It has bounded content limits; see the [README](../README.md#recovery-limits). Existing files are never overwritten. No automatic deletion or pruning.

## Link repair

Run `repair suggest /path/to/project` for historical move hints. Preview with `repair preview /path/to/project index.html old.png new.png`, then review the JSON diff. To apply, run `repair apply /path/to/project index.html old.png new.png --confirm TOKEN` using the exact preview token. Run `repair history` to obtain the ID, then `repair undo ID --yes` to revert an unchanged repaired file. Close external editors before apply or undo. See README for supported formats and limitations.

## Storage intelligence

Run `storage /path/to/folder --json` for machine-readable results. Optional `--older-days 365 --min-mib 500` filters review candidates; `--max-entries 1000000` increases the traversal limit. Exit code 1 indicates partial coverage or an error. Logical size is not reclaimable disk space. No source files are modified.

## Guarded operations

`guard preview /project old.txt --destination new.txt` outputs a risk report and confirmation token. Review it, close external editors, then run `guard apply /project old.txt --destination new.txt --confirm TOKEN`. `guard add-rule /project/important --mode block`, `guard rules`, and `guard remove-rule /project/important` manage local rules. Rules only affect this workflow. `guard preview /project old.txt --operation delete` is advisory. `update-check` makes an explicit GitHub release lookup. Linux requires atomic no-replace rename support.
