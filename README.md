# freshenup

Pick outdated Homebrew formulae and casks — and, optionally, outdated Mac App Store apps — from an `fzf` menu, then upgrade or uninstall them.

A formula node is a top-level (leaf) formula that is outdated itself or has outdated dependencies beneath it; a cask or App Store app is a standalone node. Everything starts selected. Keys are shown in the `fzf` header. App Store rows show a slugified name; the numeric id drives the action via `mas` (which needs root, so a `sudo` prompt appears only when an App Store row is selected).

## Install

```bash
brew install akirayamamoto/tap/freshenup
```

## Usage

```bash
freshenup          # scan and pick
freshenup -u       # force `brew update` first (brew otherwise auto-refreshes at most once/24h)
```

- **enter** — upgrade the selected nodes
- **ctrl-x** — uninstall the highlighted node (confirmed)
- **tab** — toggle selection
- **ctrl-t** — invert selection

## Dependencies

- [`fzf`](https://github.com/junegunn/fzf) (installed automatically via Homebrew)
- Homebrew, plus standard `awk`/`comm` (present on macOS)
- Optional: [`mas`](https://github.com/mas-cli/mas) for Mac App Store support (detected at runtime)

## License

MIT
