import pytest
from pydantic import ValidationError

from auto_biblio.repo_config.site import SiteConfig


def test_site_url_gets_a_trailing_slash() -> None:
    assert SiteConfig(site_url="https://veille.pages.dev").site_url == "https://veille.pages.dev/"


def test_site_url_keeps_its_trailing_slash() -> None:
    assert SiteConfig(site_url="https://veille.pages.dev/").site_url == "https://veille.pages.dev/"


def test_site_url_must_be_https() -> None:
    with pytest.raises(ValidationError, match="https"):
        SiteConfig(site_url="http://veille.pages.dev/")


def test_defaults() -> None:
    assert SiteConfig() == SiteConfig(site_url=None, title="Veille IA")
