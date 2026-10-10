from datetime import timedelta
from pathlib import Path

from builders import NOW

from auto_biblio.domain.feedback import FeedbackEvent
from auto_biblio.store.feedback import FeedbackStore


def event(origin: str, days_ago: int = 0) -> FeedbackEvent:
    return FeedbackEvent.model_validate(
        {
            "item_id": "arxiv:2410.1",
            "polarity": 1,
            "channel": "explicit",
            "at": NOW - timedelta(days=days_ago),
            "digest_week": "2026-W41",
            "origin": origin,
        }
    )


def test_feedback_dedup_by_origin(tmp_path: Path) -> None:
    store = FeedbackStore.open(tmp_path)
    assert store.add(event("issue#1"))
    assert not store.add(event("issue#1", days_ago=3))
    assert len(store.all()) == 1


def test_feedback_roundtrip(tmp_path: Path) -> None:
    store = FeedbackStore.open(tmp_path)
    store.add(event("issue#2"))
    store.add(event("issue#1", days_ago=40))
    store.flush()
    assert sorted(p.name for p in (tmp_path / "feedback").iterdir()) == [
        "2026-08.jsonl",
        "2026-10.jsonl",
    ]
    reopened = FeedbackStore.open(tmp_path)
    assert [e.origin for e in reopened.all()] == ["issue#1", "issue#2"]
    assert not reopened.add(event("issue#2"))
