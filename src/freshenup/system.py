"""I/O shell: run brew/mas, scan concurrently, and act on selections.

Thin by design — the logic lives in the pure parse/nodes functions; this module just shells out
and wires their injected lookups (``deps_of``, ``apps_of``, ``owner_of``) to real
queries. The pure functions here, ``blocked_casks`` and ``unindexed_apps``, take their filesystem
and Spotlight data as arguments so they are unit-tested without touching ``/Applications``.
"""

from __future__ import annotations

import os
import plistlib
import pwd
import subprocess
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from .models import Deps, Item, Kind, SelfUpdating
from .parse import (
    parse_brew_outdated,
    parse_descriptions,
    parse_formula_deps,
    parse_mas,
    parse_mise,
    parse_receipt,
    parse_self_updating,
)

_BREW = "brew"
_MAS = "mas"
_MISE = "mise"
_MDFIND = "/usr/bin/mdfind"
_MDIMPORT = "/usr/bin/mdimport"
_APPS = Path("/Applications")
_MAS_RECEIPT = Path("Contents") / "_MASReceipt" / "receipt"


def current_user() -> str:
    return pwd.getpwuid(os.getuid()).pw_name


def _capture(*args: str) -> str:
    """stdout of a command, or "" if it fails — scans tolerate a missing or erroring tool."""
    proc = subprocess.run(args, capture_output=True, text=True)
    return proc.stdout if proc.returncode == 0 else ""


@dataclass(frozen=True, slots=True)
class Scan:
    formulae: list[Item]
    casks: list[Item]
    mas: list[Item]
    mise: list[Item]
    leaves: set[str]
    installed_deps: dict[str, Deps]
    descriptions: dict[str, str]
    self_updating: list[SelfUpdating]


def scan(*, refresh: bool, has_mas: bool, has_mise: bool) -> Scan:
    if refresh:
        print("Refreshing Homebrew…", flush=True)
        subprocess.run([_BREW, "update"], stdout=subprocess.DEVNULL)
    # brew's per-call startup is ~2.5s, so run the independent lookups concurrently.
    with ThreadPoolExecutor(max_workers=6) as pool:
        formulae = pool.submit(_capture, _BREW, "outdated", "--formula", "--verbose")
        casks = pool.submit(_capture, _BREW, "outdated", "--cask", "--verbose")
        leaves = pool.submit(_capture, _BREW, "leaves", "--installed-on-request")
        # One `brew info` covers every installed package: inverting its dependencies answers
        # "who uses X?" for all formulae at once, where a `brew uses` each pays brew's startup.
        installed = pool.submit(_capture, _BREW, "info", "--json=v2", "--installed")
        mas = pool.submit(_capture, _MAS, "outdated", "--json") if has_mas else None
        # `-C /` scopes mise to the global config, ignoring any project mise.toml in the cwd.
        mise = pool.submit(_capture, _MISE, "outdated", "-C", "/", "--json") if has_mise else None
    mas_text = mas.result().strip() if mas is not None else ""
    mise_text = mise.result().strip() if mise is not None else ""
    return Scan(
        formulae=parse_brew_outdated(Kind.FORMULA, formulae.result()),
        casks=parse_brew_outdated(Kind.CASK, casks.result()),
        mas=parse_mas(mas_text) if mas_text else [],
        mise=parse_mise(mise_text) if mise_text else [],
        leaves=set(leaves.result().split()),
        installed_deps=parse_formula_deps(installed.result()) if installed.result() else {},
        descriptions=parse_descriptions(installed.result()) if installed.result() else {},
        self_updating=parse_self_updating(installed.result()) if installed.result() else [],
    )


def dry_run_formulae(names: list[str]) -> list[str]:
    """Formulae `brew upgrade` would actually touch when given ``names`` — more than asked for,
    since brew also upgrades outdated dependents. An empty list means every outdated formula to
    brew, so it never reaches the command."""
    if not names:
        return []
    text = _capture(_BREW, "upgrade", "--formula", "--dry-run", *names)
    return [line.split()[0] for line in text.splitlines() if line and not line.startswith("==>")]


def formula_deps(names: list[str]) -> dict[str, Deps]:
    text = _capture(_BREW, "info", "--json=v2", *names) if names else ""
    return parse_formula_deps(text) if text else {}


@cache
def _caskroom() -> Path:
    prefix = _capture(_BREW, "--prefix").strip() or "/opt/homebrew"
    return Path(prefix) / "Caskroom"


def _receipt(token: str) -> Path:
    return _caskroom() / token / ".metadata" / "INSTALL_RECEIPT.json"


def deps_of(token: str) -> list[str]:
    """Cask tokens that cask ``token`` depends on (from its install receipt)."""
    receipt = _receipt(token)
    if not receipt.exists():
        return []
    deps, _apps = parse_receipt(receipt.read_text())
    return deps


def apps_of(token: str) -> list[str]:
    """Installed .app bundle names for cask ``token`` (from its install receipt)."""
    receipt = _receipt(token)
    if not receipt.exists():
        return []
    _deps, apps = parse_receipt(receipt.read_text())
    return apps


def owner_of(app: str) -> str | None:
    """Owning username of ``/Applications/<app>``, or None if absent/unknown."""
    try:
        return pwd.getpwuid((_APPS / app).stat().st_uid).pw_name
    except FileNotFoundError, KeyError:
        return None


def blocked_casks(
    tokens: Iterable[str],
    apps_of: Callable[[str], Iterable[str]],
    owner_of: Callable[[str], str | None],
    me: str,
) -> list[tuple[str, str]]:
    """Return (token, owner) for casks whose installed .app is owned by someone else (typically
    root, after a vendor self-updater reinstalled it) — brew can't upgrade those without sudo."""
    blocked: list[tuple[str, str]] = []
    for token in tokens:
        for app in apps_of(token):
            owner = owner_of(app)
            if owner is not None and owner != me:
                blocked.append((token, owner))
                break
    return blocked


def chown_cask(token: str, me: str) -> bool:
    """chown the cask's installed .app bundle(s) back to ``me`` (needs sudo). True on success."""
    ok = True
    for app in apps_of(token):
        path = _APPS / app
        if path.exists():
            result = subprocess.run(["sudo", "chown", "-R", f"{me}:admin", str(path)])
            ok = ok and result.returncode == 0
    return ok


@dataclass(frozen=True, slots=True)
class InstalledApp:
    path: str
    version: str


def installed_app(cask: SelfUpdating) -> InstalledApp | None:
    """The app bundle a self-updating cask installed, read from the bundle itself — brew's own
    record goes stale as soon as the app updates itself. A bundle found by id only counts if it is
    named after the cask: some casks quit a helper (an updater, a driver) rather than their app."""
    by_id = [
        path
        for bundle_id in cask.bundle_ids
        for path in _capture(_MDFIND, f"kMDItemCFBundleIdentifier == '{bundle_id}'").splitlines()
        if Path(path).stem in cask.names
    ]
    for path in [*cask.app_paths, *by_id]:
        version = _bundle_version(Path(path))
        if version:
            return InstalledApp(path=path, version=version)
    return None


def _bundle_version(app: Path) -> str:
    plist = app / "Contents" / "Info.plist"
    if not plist.exists():
        return ""
    info = plistlib.loads(plist.read_bytes())
    return str(info.get("CFBundleShortVersionString") or info.get("CFBundleVersion") or "")


def open_app(path: str) -> None:
    subprocess.run(["open", path])


def upgrade(kind: Kind, names: list[str]) -> None:
    if not names:
        return
    if kind is Kind.MAS:
        subprocess.run(["sudo", _MAS, "upgrade", *names])
    elif kind is Kind.MISE:
        subprocess.run([_MISE, "upgrade", "-C", "/", *names])
    else:
        flag = "--cask" if kind is Kind.CASK else "--formula"
        subprocess.run([_BREW, "upgrade", flag, *names])


def uninstall(kind: Kind, name: str, mas_id: str = "") -> None:
    if kind in (Kind.CASK, Kind.APP):
        subprocess.run([_BREW, "uninstall", "--cask", name])
    elif kind is Kind.MAS:
        if mas_id:
            subprocess.run(["sudo", _MAS, "uninstall", mas_id])
    elif kind is Kind.MISE:
        # `mise uninstall` leaves the global config entry, so mise would just reinstall it;
        # `unuse` drops the entry and prunes the installation.
        subprocess.run([_MISE, "unuse", "--global", name])
    elif subprocess.run([_BREW, "uninstall", "--formula", name]).returncode == 0:
        subprocess.run([_BREW, "autoremove"])


def installed_mas_apps() -> list[str]:
    """App bundles carrying an App Store receipt — how mas decides an app came from the Store."""
    return [
        str(app)
        for folder in (_APPS, _APPS / "Utilities")
        for app in folder.glob("*.app")
        if (app / _MAS_RECEIPT).exists()
    ]


def spotlight_indexed_apps() -> list[str]:
    return _capture(_MDFIND, "-onlyin", str(_APPS), "kMDItemAppStoreAdamID == '*'").splitlines()


def unindexed_apps(installed: Iterable[str], indexed: Iterable[str]) -> list[str]:
    """Installed App Store apps that Spotlight holds no App Store metadata for. Matched on bundle
    name, not full path: Spotlight reports ``/System/Volumes/Data/Applications`` while the
    filesystem walk reports the ``/Applications`` firmlink."""
    indexed_names = {Path(path).name for path in indexed}
    return sorted(path for path in installed if Path(path).name not in indexed_names)


def refresh_mas_index() -> None:
    """Reindex App Store apps Spotlight has lost. mas warns about these and only repairs them
    after it exits, so doing it here is what keeps the next scan quiet."""
    indexed = spotlight_indexed_apps()
    if not indexed:  # query failed or Spotlight is off — can't tell what is genuinely missing
        return
    reindex(unindexed_apps(installed_mas_apps(), indexed))


def reindex(paths: list[str]) -> None:
    """Queue a Spotlight re-import and return immediately — mdimport hands the paths to the mds
    daemon, which finishes after freshenup exits."""
    if not paths:
        return
    subprocess.Popen(
        [_MDIMPORT, *paths],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
