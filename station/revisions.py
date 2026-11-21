from collections.abc import Iterable
from dataclasses import dataclass

from measurement_values import require_identifier
from station.scan_rows import ScanRow


@dataclass(frozen=True)
class RevisionKey:
    batch_id: str
    revision_id: str

    def __post_init__(self) -> None:
        require_identifier(self.batch_id, 'batch id')
        require_identifier(self.revision_id, 'revision id')

    def as_tuple(self) -> tuple[str, str]:
        return self.batch_id, self.revision_id


@dataclass(frozen=True)
class BatchRevision:
    key: RevisionKey
    rows: tuple[ScanRow, ...]


def assemble_revision(key: RevisionKey, rows: Iterable[ScanRow]) -> BatchRevision:
    ordered = tuple(rows)
    if not ordered:
        raise ValueError('a revision needs at least one scan row')
    return BatchRevision(key, ordered)
