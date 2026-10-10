"""Low-level file helpers shared by the stores."""

import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, content: str) -> None:
    """Write a text file atomically: readers see the old or the new content, never a mix.

    Args:
        path: Destination file; parent directories are created if needed.
        content: Full UTF-8 content.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def read_lines(path: Path) -> list[str]:
    """Read the non-blank lines of a text file.

    Args:
        path: File to read.

    Returns:
        Its non-blank lines, without line terminators.
    """
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def month_key(year: int, month: int) -> str:
    """Name of a monthly partition.

    Args:
        year: Calendar year.
        month: Calendar month (1-12).

    Returns:
        ``YYYY-MM``.
    """
    return f"{year:04d}-{month:02d}"
