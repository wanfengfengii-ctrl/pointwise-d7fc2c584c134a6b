import sqlite3
from collections.abc import Iterable, Mapping

from station.revision_store import RevisionStore
from station.revisions import BatchRevision, RevisionKey, assemble_revision
from station.scan_rows import parse_scan_row


class RegistrationError(ValueError):
    """The batch revision was rejected."""


def register(
    station: sqlite3.Connection, batch_id: str, revision_id: str, rows: Iterable[object]
) -> BatchRevision:
    try:
        key = RevisionKey(batch_id, revision_id)
        if isinstance(rows, (str, bytes, Mapping)):
            raise ValueError('rows must be an ordered collection of scan rows')
        parsed = []
        for ordinal, raw in enumerate(rows, start=1):
            try:
                parsed.append(parse_scan_row(raw))
            except ValueError as exc:
                raise ValueError(f'row {ordinal}: {exc}') from exc
        revision = assemble_revision(key, parsed)
        return RevisionStore(station).save_revision(revision)
    except (TypeError, ValueError) as exc:
        raise RegistrationError(str(exc)) from exc
