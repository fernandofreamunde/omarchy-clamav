# glink.clamav

Omarchy bar plugin for [ClamAV](https://www.clamav.net/). Scan Downloads or
Home from the bar, watch live progress, and get reminded when virus definitions
go stale.

## Features

- Shield chip in the Omarchy shell bar
- Live scan progress (percent + current file)
- Start **Downloads** or **Home** scans from the popup (right-click starts the default)
- **Update database** via a polkit prompt (`pkexec`)
- Reminder when definitions are **≥ 7 days** old (soft stale note after 3 days)
- Desktop notification when a reminder becomes due, when a scan finishes, or when threats are found

## Requirements

- Omarchy (Quickshell bar)
- `clamav` package
- Recommended: `clamav-daemon` and `clamav-freshclam` enabled

```bash
sudo systemctl enable --now clamav-daemon.service clamav-freshclam.service
```

## Install

From this repo (development symlink):

```bash
mkdir -p ~/.config/omarchy/plugins
ln -sfn "$(pwd)" ~/.config/omarchy/plugins/glink.clamav
omarchy-shell shell rescanPlugins
omarchy plugin enable glink.clamav --section right
```

Or add from git once published:

```bash
omarchy plugin add <git-url> --enable --yes
```

## Usage

| Action | How |
|--------|-----|
| Open panel | Left click the shield |
| Scan Downloads | Panel button, `d`, or right-click (default) |
| Scan Home | Panel button or `h` |
| Update definitions | Panel button or `u` (polkit password) |
| Stop | Panel button, `x`, or right-click while busy |
| Refresh status | Middle click or `r` |

## Reminder policy

| Age of definitions | Behavior |
|--------------------|----------|
| &lt; 3 days | Quiet — bar looks normal |
| 3–7 days | Panel notes they’re getting old |
| ≥ 7 days | Bar goes urgent, `!` badge, one notification until you update |

With `clamav-freshclam` enabled, definitions usually stay fresh on their own.
The reminder is a safety net if the updater stops or the machine was offline.

## Layout

```
manifest.json      Plugin contract
Panel.qml          Bar chip + popup
Service.qml        Status polling / actions
Model.js           Labels and formatting
ctl.py             Scan/update worker + status JSON
update-helper.sh   Privileged freshclam refresh (pkexec)
```

Status file: `~/.local/state/omarchy/clamav/status.json`

## License

MIT
