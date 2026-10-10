from pathlib import Path

import pytest
from builders import NOW, make_features, make_item, make_run, make_verdict

from auto_biblio.domain.errors import TriageRunMissingError
from auto_biblio.domain.triage import ScoredItem
from auto_biblio.publish import Mail
from auto_biblio.repo_config.profile import Profile
from auto_biblio.stages.digest import DigestStage
from auto_biblio.store.items import ItemStore
from auto_biblio.store.runs import RunStore
from auto_biblio.store.triage import TriageStore

PROFILE = Profile.model_validate(
    {"themes": [{"id": "agentic", "label": "Agents", "description": "a"}]}
)


class Outbox:
    def __init__(self) -> None:
        self.sent: list[Mail] = []

    def send(self, mail: Mail) -> None:
        self.sent.append(mail)


def stage(tmp_path: Path, outbox: Outbox | None, to: str | None = "me@example.com") -> DigestStage:
    items = ItemStore.open(tmp_path)
    items.upsert(make_item(title="Agent harness"))
    scored = ScoredItem(
        item_id=make_item().id,
        features=make_features(),
        prescore=0.5,
        verdict=make_verdict(),
        final_score=0.9,
        slot="theme",
        theme="agentic",  # pyright: ignore[reportArgumentType] - ThemeId at runtime
    )
    TriageStore(tmp_path).write(make_run("2026-W41", (scored,)))
    return DigestStage(
        TriageStore(tmp_path),
        items,
        RunStore(tmp_path),
        PROFILE,
        sender=outbox,
        repo="me/data",
        to=to,
        clock=lambda: NOW,
    )


def test_send_latest_week(tmp_path: Path) -> None:
    outbox = Outbox()
    mail = stage(tmp_path, outbox).run()
    assert outbox.sent == [mail]
    assert mail.subject == "Veille IA — 2026-W41"
    assert "Agent harness" in mail.html
    assert mail.to == "me@example.com"


def test_dry_run_writes_file_and_sends_nothing(tmp_path: Path) -> None:
    outbox = Outbox()
    target = tmp_path / "digest.html"
    stage(tmp_path, outbox).run(week="2026-W41", dry_run_path=target)
    assert "Agent harness" in target.read_text()
    assert outbox.sent == []


def test_missing_run(tmp_path: Path) -> None:
    with pytest.raises(TriageRunMissingError, match="2026-W40"):
        stage(tmp_path, Outbox()).run(week="2026-W40")
    with pytest.raises(TriageRunMissingError, match="any week"):
        DigestStage(
            TriageStore(tmp_path / "empty"),
            ItemStore.open(tmp_path),
            RunStore(tmp_path),
            PROFILE,
            sender=None,
            repo=None,
            to=None,
            clock=lambda: NOW,
        ).run()


def test_sending_needs_sender_and_recipient(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="needs a mail sender"):
        stage(tmp_path, None).run()
    with pytest.raises(ValueError, match="needs a mail sender"):
        stage(tmp_path, Outbox(), to=None).run()
