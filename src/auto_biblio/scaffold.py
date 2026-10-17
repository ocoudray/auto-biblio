"""Create a ready-to-run data repository (`auto-biblio init`)."""

from importlib.resources import files
from pathlib import Path
from string import Template

from auto_biblio.domain.errors import AutoBiblioError

_TEMPLATES = files("auto_biblio.scaffold_templates")
# Destination path in the data repository -> template file name.
_LAYOUT = {
    "config/profile.yaml": "profile.yaml",
    "config/sources.yaml": "sources.yaml",
    "config/llm.yaml": "llm.yaml",
    "config/triage.yaml": "triage.yaml",
    "config/analysis.yaml": "analysis.yaml",
    ".github/workflows/daily.yml": "daily.yml",
    ".github/workflows/weekly.yml": "weekly.yml",
    ".github/workflows/wiki-check.yml": "wiki-check.yml",
    ".gitignore": "gitignore",
}
# Destination path -> template copied as is: skills contain `$ARGUMENTS`, not a substitution.
_VERBATIM = {
    ".claude/skills/wiki-plan/SKILL.md": "skill_wiki_plan.md",
    ".claude/skills/wiki-rediger/SKILL.md": "skill_wiki_rediger.md",
    ".claude/skills/wiki-reprendre/SKILL.md": "skill_wiki_reprendre.md",
    "wiki/GUIDE.md": "wiki_guide.md",
}
_KEEP = ("state/.gitkeep", "kb/.gitkeep")


class ScaffoldExistsError(AutoBiblioError):
    """`init` would overwrite existing files."""

    def __init__(self, paths: tuple[Path, ...]) -> None:
        """Build the error.

        Args:
            paths: The files that already exist.
        """
        self.paths = paths
        listing = ", ".join(str(p) for p in paths)
        super().__init__(f"refusing to overwrite existing files: {listing}")


def scaffold_data_repo(target: Path, version: str) -> list[Path]:
    """Write the configuration, workflows, wiki skills and state skeleton of a new data repository.

    Nothing is written if any destination file already exists.

    Args:
        target: Root of the data repository (created if needed).
        version: auto-biblio version the daily workflow installs.

    Returns:
        The created files.

    Raises:
        ScaffoldExistsError: If a destination file already exists.
    """
    destinations = [target / relative for relative in (*_LAYOUT, *_VERBATIM, *_KEEP)]
    existing = tuple(path for path in destinations if path.exists())
    if existing:
        raise ScaffoldExistsError(existing)
    for relative, template in _LAYOUT.items():
        content = _TEMPLATES.joinpath(template).read_text(encoding="utf-8")
        _write(target / relative, Template(content).substitute(version=version))
    for relative, template in _VERBATIM.items():
        _write(target / relative, _TEMPLATES.joinpath(template).read_text(encoding="utf-8"))
    for keep in _KEEP:
        _write(target / keep, "")
    return destinations


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
