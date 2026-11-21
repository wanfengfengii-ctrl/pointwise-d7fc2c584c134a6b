import sqlite3
from fractions import Fraction

from station.revisions import BatchRevision, RevisionKey, assemble_revision
from station.scan_rows import ScanRow
from station.source_schema import initialize_source_schema


def _stored_scan_row(key: RevisionKey, ordinal: int, row: ScanRow) -> tuple:
    return (
        *key.as_tuple(), ordinal, str(row.x0), str(row.x1), str(row.y0), str(row.y1),
        str(row.weight), row.source_record, str(row.scan_start), str(row.scan_end),
    )


def _read_scan_row(row: tuple) -> ScanRow:
    x0, x1, y0, y1, weight, source_record, scan_start, scan_end = row
    return ScanRow(
        Fraction(x0), Fraction(x1), Fraction(y0), Fraction(y1), Fraction(weight),
        source_record, Fraction(scan_start), Fraction(scan_end),
    )


class RevisionStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def initialize(self) -> None:
        initialize_source_schema(self.connection)

    def save_revision(self, revision: BatchRevision) -> BatchRevision:
        connection = self.connection
        key = revision.key
        connection.execute('BEGIN IMMEDIATE')
        with connection:
            inserted = connection.execute('''
                INSERT INTO revisions (batch_id, revision_id) VALUES (?, ?)
                ON CONFLICT (batch_id, revision_id) DO NOTHING
            ''', key.as_tuple())
            if inserted.rowcount != 1:
                raise ValueError(f'revision already exists: {key.batch_id}/{key.revision_id}')
            connection.executemany('''
                INSERT INTO scan_rows (
                    batch_id, revision_id, ordinal, x0, x1, y0, y1, weight,
                    source_record, scan_start, scan_end
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (_stored_scan_row(key, ordinal, row) for ordinal, row in enumerate(revision.rows)))
            connection.execute('''
                INSERT INTO current_revisions (batch_id, revision_id) VALUES (?, ?)
                ON CONFLICT (batch_id) DO UPDATE SET revision_id = excluded.revision_id
            ''', key.as_tuple())
        return revision

    def get_revision(self, key: RevisionKey) -> BatchRevision | None:
        rows = self.connection.execute('''
            SELECT x0, x1, y0, y1, weight, source_record, scan_start, scan_end
            FROM scan_rows WHERE batch_id = ? AND revision_id = ? ORDER BY ordinal
        ''', key.as_tuple()).fetchall()
        if not rows:
            return None
        return assemble_revision(key, map(_read_scan_row, rows))

    def get_current(self, batch_id: str) -> BatchRevision | None:
        current = self.connection.execute('''
            SELECT revision_id FROM current_revisions WHERE batch_id = ?
        ''', (batch_id,)).fetchone()
        if current is None:
            return None
        return self.get_revision(RevisionKey(batch_id, current[0]))
