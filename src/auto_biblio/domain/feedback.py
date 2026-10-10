"""Feedback on digest items, and the parsing of the GitHub issues that carry it."""

import re
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict

from auto_biblio.domain.errors import FeedbackParseError
from auto_biblio.domain.ids import ItemId

Polarity = Literal[1, -1]

_TITLE = re.compile(r"^\s*(👍|👎|\+1|-1)\s+(\S+)\s*$")
_WEEK = re.compile(r"^\s*week:\s*(\d{4}-W\d{2})\s*$", re.MULTILINE)
_ID_PREFIXES = ("arxiv:", "gh:", "doi:", "url:")
_POLARITY: dict[str, Polarity] = {"👍": 1, "+1": 1, "👎": -1, "-1": -1}


class FeedbackEvent(BaseModel):
    """One reaction to an item shown in a digest."""

    model_config = ConfigDict(frozen=True)

    item_id: ItemId
    polarity: Polarity
    channel: Literal["explicit"]
    at: AwareDatetime
    digest_week: str | None
    origin: str
    """Where the event came from, e.g. `issue#123`; unique per event."""


class ParsedIssue(BaseModel):
    """What a well-formed feedback issue title says."""

    model_config = ConfigDict(frozen=True)

    item_id: ItemId
    polarity: Polarity


def parse_issue_title(title: str, origin: str) -> ParsedIssue:
    """Parse a feedback issue title such as `👍 arxiv:2410.12345`.

    `+1` and `-1` are accepted as aliases of the thumbs, for clients that mangle emojis.

    Args:
        title: The issue title.
        origin: Where the issue comes from, used in error messages.

    Returns:
        The item and the polarity.

    Raises:
        FeedbackParseError: If the title does not follow the format.
    """
    match = _TITLE.match(title)
    if match is None:
        msg = f"expected '👍 <item id>' or '👎 <item id>', got {title!r}"
        raise FeedbackParseError(origin, msg)
    thumb, item_id = match.groups()
    if not item_id.startswith(_ID_PREFIXES):
        msg = f"unknown item id {item_id!r} (expected one of {', '.join(_ID_PREFIXES)})"
        raise FeedbackParseError(origin, msg)
    return ParsedIssue(item_id=ItemId(item_id), polarity=_POLARITY[thumb])


def parse_issue_week(body: str | None) -> str | None:
    """Read the `week: YYYY-Www` line of a feedback issue body.

    Args:
        body: The issue body.

    Returns:
        The ISO week of the digest, if present.
    """
    if body is None:
        return None
    match = _WEEK.search(body)
    return match.group(1) if match else None
