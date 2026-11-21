import hashlib
import sqlite3
from dataclasses import dataclass

from issue.envelope import IssueIdentity
from measurement_values import is_record_number
from receipt.identity import receipt_source_key, same_frozen_package


@dataclass(frozen=True)
class IntakeAcknowledgment:
    receipt_id: int
    confirmation: str


@dataclass(frozen=True)
class ReceiptRecord:
    receipt_id: int
    identity: IssueIdentity
    package_text: str
    acknowledgment: IntakeAcknowledgment


_RECEIPT_COLUMNS = 'receipt_id, issue_id, batch_id, revision_id, package_text, confirmation'


def _materialize(row: tuple) -> ReceiptRecord:
    receipt_id, issue_id, batch_id, revision_id, package_text, confirmation = row
    return ReceiptRecord(
        receipt_id, IssueIdentity(issue_id, batch_id, revision_id), package_text,
        IntakeAcknowledgment(receipt_id, confirmation),
    )


class ReceiptStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute('PRAGMA foreign_keys = ON')
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS receipts (
                receipt_id INTEGER PRIMARY KEY,
                issue_id TEXT NOT NULL UNIQUE,
                batch_id TEXT NOT NULL,
                revision_id TEXT NOT NULL,
                package_text TEXT NOT NULL,
                confirmation TEXT NOT NULL
            )
        ''')

    def record_receipt(self, identity: IssueIdentity, package_text: str) -> ReceiptRecord:
        source_key = receipt_source_key(identity)
        connection = self.connection
        connection.execute('BEGIN IMMEDIATE')
        with connection:
            existing = connection.execute(f'''
                SELECT {_RECEIPT_COLUMNS} FROM receipts WHERE issue_id = ?
            ''', (source_key,)).fetchone()
            if existing is not None:
                saved = _materialize(existing)
                if saved.identity != identity or not same_frozen_package(saved.package_text, package_text):
                    raise ValueError('frozen content conflicts with an existing issue')
                return saved
            confirmation = 'receipt-' + hashlib.sha256(package_text.encode('utf-8')).hexdigest()
            inserted = connection.execute('''
                INSERT INTO receipts (issue_id, batch_id, revision_id, package_text, confirmation)
                VALUES (?, ?, ?, ?, ?)
            ''', (source_key, identity.batch_id, identity.revision_id, package_text, confirmation))
            receipt_id = inserted.lastrowid
        return ReceiptRecord(
            receipt_id, identity, package_text, IntakeAcknowledgment(receipt_id, confirmation),
        )

    def get_receipt(self, receipt_id: int) -> ReceiptRecord | None:
        if not is_record_number(receipt_id):
            return None
        row = self.connection.execute(f'''
            SELECT {_RECEIPT_COLUMNS} FROM receipts WHERE receipt_id = ?
        ''', (receipt_id,)).fetchone()
        return None if row is None else _materialize(row)
