"""Generate one API reference page per module under `src/` into `docs/reference/`.

Run before every docs build (the Makefile does it); the output is git-ignored.
"""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
REFERENCE = ROOT / "docs" / "reference"


def module_names(src: Path) -> list[str]:
    """List the dotted names of every documentable module below ``src``."""
    names: list[str] = []
    for path in sorted(src.rglob("*.py")):
        parts = list(path.relative_to(src).with_suffix("").parts)
        if parts[-1] == "__main__":
            continue
        if parts[-1] == "__init__":
            parts = parts[:-1]
        names.append(".".join(parts))
    return sorted(names)


def main() -> None:
    """Rewrite ``docs/reference/`` from scratch."""
    shutil.rmtree(REFERENCE, ignore_errors=True)
    REFERENCE.mkdir(parents=True)
    names = module_names(SRC)
    for name in names:
        (REFERENCE / f"{name}.md").write_text(f"# `{name}`\n\n::: {name}\n")
    links = "\n".join(f"- [`{name}`]({name}.md)" for name in names)
    (REFERENCE / "index.md").write_text(f"# API reference\n\n{links}\n")


if __name__ == "__main__":
    main()
