"""Item store: one JSONL file per month of `first_seen`, sorted by id."""

from collections.abc import Iterator
from pathlib import Path
from typing import Literal, Self

from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.merge import merge_items, normalized_title, same_content
from auto_biblio.domain.models import Item
from auto_biblio.store._files import atomic_write_text, month_key, read_lines

UpsertOutcome = Literal["new", "merged", "unchanged"]


class ItemStore:
    """In-memory index of every item, persisted to `state/items/YYYY-MM.jsonl`."""

    def __init__(self, directory: Path, items: dict[ItemId, Item]) -> None:
        """Wrap already-loaded items; use `ItemStore.open` instead.

        Args:
            directory: The `state/items` directory.
            items: Loaded items by id.
        """
        self._dir = directory
        self._items: dict[ItemId, Item] = {}
        self._by_title: dict[str, ItemId] = {}
        for item in items.values():
            self._index(item)
        self._dirty: set[str] = set()

    @classmethod
    def open(cls, state_dir: Path) -> Self:
        """Load every item stored under `state_dir`.

        Args:
            state_dir: The data repository's `state/` directory.

        Returns:
            The store.
        """
        directory = state_dir / "items"
        items: dict[ItemId, Item] = {}
        for path in sorted(directory.glob("*.jsonl")):
            for line in read_lines(path):
                item = Item.model_validate_json(line)
                items[item.id] = item
        return cls(directory, items)

    def get(self, item_id: ItemId) -> Item | None:
        """Return the item with this id, if known."""
        return self._items.get(item_id)

    def all(self) -> Iterator[Item]:
        """Iterate over every item, sorted by id.

        Yields:
            The items.
        """
        for item_id in sorted(self._items):
            yield self._items[item_id]

    def upsert(self, item: Item) -> UpsertOutcome:
        """Insert an item, or merge it into the same item already known.

        Papers without a shared id are matched on their normalized title.

        Args:
            item: The observed item.

        Returns:
            Whether the item was new, merged into an existing one, or brought nothing new.
        """
        existing = self._find(item)
        if existing is None:
            self._put(item)
            return "new"
        merged = merge_items(existing, item)
        if merged == existing:
            return "unchanged"
        self._dirty.add(_partition(existing))
        self._unindex(existing)
        self._put(merged)
        return "merged"

    def flush(self) -> None:
        """Rewrite the partitions changed since the last flush."""
        for key in sorted(self._dirty):
            items = sorted(
                (i for i in self._items.values() if _partition(i) == key), key=lambda i: i.id
            )
            path = self._dir / f"{key}.jsonl"
            if items:
                atomic_write_text(path, "".join(f"{i.model_dump_json()}\n" for i in items))
            else:
                path.unlink(missing_ok=True)
        self._dirty.clear()

    def _find(self, item: Item) -> Item | None:
        if item.id in self._items:
            return self._items[item.id]
        if item.kind != "paper":
            return None
        match = self._by_title.get(normalized_title(item.title))
        candidate = self._items.get(match) if match is not None else None
        return candidate if candidate is not None and same_content(candidate, item) else None

    def _put(self, item: Item) -> None:
        self._index(item)
        self._dirty.add(_partition(item))

    def _index(self, item: Item) -> None:
        self._items[item.id] = item
        if item.kind == "paper":
            self._by_title.setdefault(normalized_title(item.title), item.id)

    def _unindex(self, item: Item) -> None:
        key = normalized_title(item.title)
        if self._by_title.get(key) == item.id:
            del self._by_title[key]


def _partition(item: Item) -> str:
    return month_key(item.first_seen.year, item.first_seen.month)
