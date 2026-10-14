"""Weekly digest: render the latest triage and send it."""

import logging
from datetime import timedelta
from pathlib import Path

from auto_biblio.domain.errors import TriageRunMissingError
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.models import Clock
from auto_biblio.domain.triage import TriageRun
from auto_biblio.publish import Mail, MailSender
from auto_biblio.publish.render import render_digest
from auto_biblio.publish.view import (
    HealthSummary,
    KBChanges,
    KBLinks,
    NoteLink,
    build_view,
    kb_changes,
    note_links,
)
from auto_biblio.repo_config.profile import Profile
from auto_biblio.store.analysis import AnalysisStore
from auto_biblio.store.items import ItemStore
from auto_biblio.store.kb import KBStore
from auto_biblio.store.runs import RunStore
from auto_biblio.store.triage import TriageStore

logger = logging.getLogger(__name__)

HEALTH_DAYS = 14
"""How far back run reports are read for the health footer."""


class DigestStage:
    """Renders the digest of a triaged week, then sends it or writes it to disk."""

    def __init__(  # noqa: PLR0913 - dependencies are injected explicitly
        self,
        triage: TriageStore,
        items: ItemStore,
        runs: RunStore,
        profile: Profile,
        *,
        sender: MailSender | None,
        repo: str | None,
        to: str | None,
        clock: Clock,
        kb: KBStore | None = None,
        analyses: AnalysisStore | None = None,
        site_url: str | None = None,
    ) -> None:
        """Build the stage.

        Args:
            triage: Weekly journals.
            items: Collected items.
            runs: Run reports, for the health footer.
            profile: The interest profile.
            sender: Sends the mail; None is only allowed for dry runs.
            repo: `owner/repo` of the data repository, for the feedback links.
            to: Recipient address.
            clock: Current time provider.
            kb: The knowledge base, to link items to their notes.
            analyses: Analysis journals, for the knowledge base changes of the week.
            site_url: Address of the published site; links go to GitHub without it.
        """
        self._links = KBLinks(repo=repo, site_url=site_url)
        self._kb = kb
        self._analyses = analyses
        self._triage = triage
        self._items = items
        self._runs = runs
        self._profile = profile
        self._sender = sender
        self._repo = repo
        self._to = to
        self._clock = clock

    def run(self, week: str | None = None, dry_run_path: Path | None = None) -> Mail:
        """Render the digest and deliver it.

        Args:
            week: ISO week (default: the latest triaged week).
            dry_run_path: Write the HTML there instead of sending the mail.

        Returns:
            The rendered mail.

        Raises:
            TriageRunMissingError: If the week was not triaged.
            ValueError: If no sender or recipient is configured outside a dry run.
        """
        run = self._triage.read(week) if week else self._triage.latest()
        if run is None:
            raise TriageRunMissingError(week)
        items = {s.item_id: item for s in run.selected() if (item := self._items.get(s.item_id))}
        reports = self._runs.recent_reports(self._clock() - timedelta(days=HEALTH_DAYS))
        view = build_view(
            run,
            items,
            self._profile,
            HealthSummary.from_runs(reports),
            self._repo,
            notes=self._note_links(run),
            changes=self._changes(run.week),
            online_url=self._links.digest(run.week),
        )
        html, text = render_digest(view)
        mail = Mail(subject=f"Veille IA — {run.week}", html=html, text=text, to=self._to or "")
        if dry_run_path is not None:
            dry_run_path.write_text(html, encoding="utf-8")
            logger.info("digest of %s written to %s", run.week, dry_run_path)
            return mail
        if self._sender is None or not self._to:
            msg = "sending the digest needs a mail sender and a recipient"
            raise ValueError(msg)
        self._sender.send(mail)
        logger.info("digest of %s sent to %s", run.week, self._to)
        return mail

    def _note_links(self, run: TriageRun) -> dict[ItemId, NoteLink]:
        if self._kb is None:
            return {}
        notes = {note.meta.id: note for note in self._kb.all_notes()}
        return note_links(run, notes, self._links)

    def _changes(self, week: str) -> KBChanges | None:
        analysis = self._analyses.read(week) if self._analyses else None
        if analysis is None or self._kb is None:
            return None
        return kb_changes(analysis.changelog, self._kb.note_paths(), self._profile, self._links)
