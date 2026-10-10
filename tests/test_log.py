import logging

from auto_biblio import __version__
from auto_biblio.log import configure_logging


def test_configure_logging_sets_root_level() -> None:
    configure_logging("WARNING")
    assert logging.getLogger().level == logging.WARNING


def test_version_is_exposed() -> None:
    assert __version__ == "0.1.0"
