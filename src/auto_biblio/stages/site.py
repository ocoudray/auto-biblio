"""Site build: the knowledge base and the archived digests, as a static site."""

import logging
from pathlib import Path
from typing import Protocol

from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.kb.notes import Note
from auto_biblio.domain.triage import TriageRun
from auto_biblio.domain.website.plan import SiteInputs, SitePlan, plan_site
from auto_biblio.publish.render import render_digest_markdown
from auto_biblio.publish.view import HealthSummary, KBLinks, build_view, kb_changes, note_links
from auto_biblio.repo_config.loader import RepoConfig
from auto_biblio.store.analysis import AnalysisStore
from auto_biblio.store.items import ItemStore
from auto_biblio.store.kb import KBStore
from auto_biblio.store.triage import TriageStore

logger = logging.getLogger(__name__)

ARCHIVE_LINKS = KBLinks(relative_to="../")
"""Digest pages live in `digests/`: their links climb one folder to reach the notes."""


class SiteBuilderPort(Protocol):
    """Turns a planned site into HTML (see `SiteBuilder`)."""

    def build(self, plan: SitePlan, title: str, out: Path, /) -> None:
        """Build the site into `out`."""
        ...


class SiteStage:
    """Plans the site from the data repository and builds it."""

    def __init__(  # noqa: PLR0913 - dependencies are injected explicitly
        self,
        config: RepoConfig,
        kb: KBStore,
        triage: TriageStore,
        items: ItemStore,
        analyses: AnalysisStore,
        *,
        builder: SiteBuilderPort,
    ) -> None:
        """Build the stage.

        Args:
            config: The data repository configuration (profile and site title).
            kb: The knowledge base.
            triage: Weekly journals, one archived digest each.
            items: Collected items.
            analyses: Analysis journals, for the knowledge base changes of each week.
            builder: Turns the plan into HTML.
        """
        self._config = config
        self._kb = kb
        self._triage = triage
        self._items = items
        self._analyses = analyses
        self._builder = builder

    def run(self, out: Path) -> SitePlan:
        """Plan the site and build it into `out`.

        Args:
            out: Destination directory, replaced by the new site.

        Returns:
            The plan that was built.
        """
        notes = {note.meta.id: note for note in self._kb.all_notes()}
        inputs = SiteInputs(
            title=self._config.site.title,
            profile=self._config.profile,
            kb_files=self._kb.files(),
            digests={run.week: self._digest(run, notes) for run in self._triage.all()},
        )
        plan = plan_site(inputs)
        for warning in plan.warnings:
            logger.warning("site: %s", warning)
        self._builder.build(plan, self._config.site.title, out)
        logger.info("site built in %s: %d pages", out, len(plan.pages))
        return plan

    def _digest(self, run: TriageRun, notes: dict[ItemId, Note]) -> str:
        items = {s.item_id: item for s in run.selected() if (item := self._items.get(s.item_id))}
        analysis = self._analyses.read(run.week)
        changes = (
            kb_changes(
                analysis.changelog, self._kb.note_paths(), self._config.profile, ARCHIVE_LINKS
            )
            if analysis is not None
            else None
        )
        view = build_view(
            run,
            items,
            self._config.profile,
            HealthSummary(),
            None,
            notes=note_links(run, notes, ARCHIVE_LINKS),
            changes=changes,
        )
        return render_digest_markdown(view)
