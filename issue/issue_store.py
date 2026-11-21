import sqlite3
from dataclasses import dataclass

from issue.envelope import IssueIdentity, decode_envelope


@dataclass(frozen=True)
class IssuedPackage:
    identity: IssueIdentity
    package_text: str


class IssueStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute('PRAGMA foreign_keys = ON')
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS issued_packages (
                issue_id TEXT PRIMARY KEY NOT NULL,
                batch_id TEXT NOT NULL,
                revision_id TEXT NOT NULL,
                package_text TEXT NOT NULL,
                UNIQUE (batch_id, revision_id),
                FOREIGN KEY (batch_id, revision_id)
                    REFERENCES revisions (batch_id, revision_id)
            )
        ''')

    def save_issued(self, issued: IssuedPackage) -> IssuedPackage:
        identity = issued.identity
        if decode_envelope(issued.package_text).identity != identity:
            raise ValueError('archive identity differs from the package envelope')
        connection = self.connection
        connection.execute('BEGIN IMMEDIATE')
        with connection:
            existing = connection.execute('''
                SELECT issue_id, package_text FROM issued_packages
                WHERE batch_id = ? AND revision_id = ?
            ''', (identity.batch_id, identity.revision_id)).fetchone()
            if existing is not None:
                issue_id, package_text = existing
                saved_identity = IssueIdentity(issue_id, identity.batch_id, identity.revision_id)
                return IssuedPackage(saved_identity, package_text)
            connection.execute('''
                INSERT INTO issued_packages (issue_id, batch_id, revision_id, package_text)
                VALUES (?, ?, ?, ?)
            ''', (identity.issue_id, identity.batch_id, identity.revision_id, issued.package_text))
        return issued

    def get_issued(self, issue_id: str) -> IssuedPackage | None:
        row = self.connection.execute('''
            SELECT batch_id, revision_id, package_text FROM issued_packages WHERE issue_id = ?
        ''', (issue_id,)).fetchone()
        if row is None:
            return None
        batch_id, revision_id, package_text = row
        return IssuedPackage(IssueIdentity(issue_id, batch_id, revision_id), package_text)
