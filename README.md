# freshenup

Pick outdated Homebrew formulae and casks — and, optionally, outdated Mac App Store apps and [`mise`](https://mise.jdx.dev) tools — from an `fzf` menu, then upgrade or uninstall them.

A formula node is a top-level (leaf) formula that is outdated itself or has outdated dependencies beneath it; a cask or App Store app is a standalone node. Nothing starts selected. Keys are shown in the `fzf` header. App Store rows show a slugified name (with the last 3 id digits only if names clash); the numeric id drives the action via `mas` (which needs root, so a `sudo` prompt appears only when an App Store row is selected). `mise` tools (global config only, via `mise outdated -C /`) are standalone nodes that upgrade within their configured version range; uninstalling one removes it from the global mise config (`mise unuse --global`).

## Install

**From PyPI** (released versions):

```bash
uv tool install freshenup   # install
uv tool upgrade freshenup   # update
uvx freshenup               # or run once without installing
```

**From a local checkout** (runs your working copy; edits apply immediately):

```bash
uv tool install --force --editable /path/to/freshenup
```

## Usage

```bash
freshenup          # scan and pick
freshenup -u       # force `brew update` first (brew otherwise auto-refreshes at most once/24h)
```

- **enter** — upgrade the selected nodes
- **ctrl-x** — uninstall the highlighted node (confirmed)
- **tab** — toggle selection
- **ctrl-t** — invert selection (selects everything when nothing is selected)

## Dependencies

- [`fzf`](https://github.com/junegunn/fzf) 0.60+ — the interactive picker (`brew install fzf`)
- Homebrew
- Python 3.14+ and [`pydantic`](https://docs.pydantic.dev) (installed automatically with the package)
- Optional: [`mas`](https://github.com/mas-cli/mas) for Mac App Store support (detected at runtime)
- Optional: [`mise`](https://mise.jdx.dev) for dev-tool/runtime updates (detected at runtime; global config only)

## Development

Managed with [`uv`](https://docs.astral.sh/uv/); lint/format with Ruff, type-checked with pyright (strict).

```bash
uv sync              # create the venv and install deps
uv run pytest        # run tests
uv run ruff check    # lint
uv run ruff format   # format
uv run pyright       # type-check (strict)
```

## License

MIT
