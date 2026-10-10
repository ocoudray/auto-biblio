import pytest
from pydantic import ValidationError

from auto_biblio.repo_config.profile import Profile, Theme, Watch


def make_theme(theme_id: str, repos: tuple[str, ...] = ()) -> Theme:
    return Theme(id=theme_id, label=theme_id, description="d", watch=Watch(repos=repos))


def test_profile_rejects_duplicate_theme_ids() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        Profile(themes=(make_theme("a"), make_theme("a")))


def test_profile_requires_a_theme() -> None:
    with pytest.raises(ValidationError):
        Profile(themes=())


def test_theme_id_must_be_slug() -> None:
    with pytest.raises(ValidationError):
        make_theme("Not A Slug")


def test_watch_repo_format() -> None:
    with pytest.raises(ValidationError):
        Watch(repos=("not-a-repo",))


def test_watched_repos_union_sorted_lowercase() -> None:
    profile = Profile(
        themes=(
            make_theme("a", ("Pydantic/Pydantic-AI", "astral-sh/uv")),
            make_theme("b", ("pydantic/pydantic-ai",)),
        )
    )
    assert profile.watched_repos() == ("astral-sh/uv", "pydantic/pydantic-ai")
