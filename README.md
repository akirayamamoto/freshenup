# brew-pick

Pick outdated Homebrew formulae and casks from an `fzf` menu, then upgrade or uninstall them.

A formula node is a top-level (leaf) formula that is outdated itself or has outdated dependencies beneath it; a cask node is just the outdated cask. Everything starts selected. Keys are shown in the `fzf` header.

## Install

```bash
brew install akirayamamoto/tap/brew-pick
```

## Usage

```bash
brew-pick          # scan and pick
brew-pick -u       # force `brew update` first (brew otherwise auto-refreshes at most once/24h)
```

- **enter** — upgrade the selected nodes
- **ctrl-x** — uninstall the highlighted node (confirmed)
- **tab** — toggle selection
- **ctrl-t** — invert selection

## Dependencies

- [`fzf`](https://github.com/junegunn/fzf) (installed automatically via Homebrew)
- Homebrew, plus standard `awk`/`comm` (present on macOS)

## License

MIT
