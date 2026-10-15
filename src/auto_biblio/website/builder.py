"""Write a planned site to disk and turn it into HTML with zensical."""

import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from auto_biblio.domain.errors import SiteBuildError, SiteOutputError
from auto_biblio.domain.website.plan import NavEntry, SitePlan

MARKER = ".auto-biblio-site"
"""File left in every built site: only such a directory, or an empty one, is ever replaced."""
FEATURES = ("navigation.indexes", "navigation.instant", "navigation.top", "search.highlight")
_PALETTES = """
[[project.theme.palette]]
media = "(prefers-color-scheme: light)"
scheme = "default"
toggle.icon = "lucide/moon"
toggle.name = "Passer en mode sombre"

[[project.theme.palette]]
media = "(prefers-color-scheme: dark)"
scheme = "slate"
toggle.icon = "lucide/sun"
toggle.name = "Passer en mode clair"
"""


def _toml(value: str) -> str:
    # A JSON string is a valid TOML basic string.
    return json.dumps(value, ensure_ascii=False)


def _nav_entry(entry: NavEntry, indent: str) -> str:
    if entry.path is not None:
        return f"{indent}{{ {_toml(entry.title)} = {_toml(entry.path)} }},"
    children = "\n".join(_nav_entry(child, indent + "  ") for child in entry.children)
    return f"{indent}{{ {_toml(entry.title)} = [\n{children}\n{indent}] }},"


def render_config(title: str, nav: Sequence[NavEntry]) -> str:
    """Write the zensical configuration of the site.

    Args:
        title: Title of the site.
        nav: The navigation.

    Returns:
        The content of `zensical.toml`.
    """
    entries = "\n".join(_nav_entry(entry, "  ") for entry in nav)
    features = ", ".join(_toml(f) for f in FEATURES)
    return (
        "[project]\n"
        f"site_name = {_toml(title)}\n"
        'docs_dir = "docs"\n'
        'site_dir = "site"\n'
        f"nav = [\n{entries}\n]\n\n"
        "[project.theme]\n"
        'language = "fr"\n'
        f"features = [{features}]\n"
        f"{_PALETTES}"
    )


class SiteBuilder:
    """Builds the HTML site of a plan with zensical."""

    def __init__(self, *, strict: bool = False) -> None:
        """Build the builder.

        Args:
            strict: Fail on any warning (broken link...); used by tests, not in production.
        """
        self._strict = strict

    def build(self, plan: SitePlan, title: str, out: Path) -> None:
        """Build the site into `out`, replacing what it held.

        Args:
            plan: The pages and navigation.
            title: Title of the site.
            out: Destination directory.

        Raises:
            SiteOutputError: If `out` exists and is neither empty nor a site built here.
            SiteBuildError: If zensical fails.
        """
        _check_output(out)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for path, text in plan.pages.items():
                target = root / "docs" / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
            config = root / "zensical.toml"
            config.write_text(render_config(title, plan.nav), encoding="utf-8")
            command = [sys.executable, "-m", "zensical", "build", "-f", str(config)]
            result = subprocess.run(  # noqa: S603 - fixed command, no shell, no user input
                [*command, *(["--strict"] if self._strict else [])],
                capture_output=True,
                text=True,
                check=False,
                cwd=root,
            )
            if result.returncode != 0:
                raise SiteBuildError(result.stderr or result.stdout)
            (root / "site" / MARKER).write_text("", encoding="utf-8")
            if out.exists():
                shutil.rmtree(out)
            shutil.copytree(root / "site", out)


def _check_output(out: Path) -> None:
    # `out` is wiped before the copy: refuse anything that could hold the user's data.
    if not out.exists():
        return
    if not out.is_dir():
        raise SiteOutputError(str(out), "not a directory")
    if any(out.iterdir()) and not (out / MARKER).exists():
        raise SiteOutputError(str(out), "not a site built by auto-biblio and not empty")
