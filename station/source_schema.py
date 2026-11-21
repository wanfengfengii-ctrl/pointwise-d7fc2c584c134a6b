import sqlite3


def initialize_source_schema(connection: sqlite3.Connection) -> None:
    connection.execute('PRAGMA foreign_keys = ON')
    connection.execute('BEGIN IMMEDIATE')
    with connection:
        connection.execute('''
            CREATE TABLE IF NOT EXISTS revisions (
                batch_id TEXT NOT NULL,
                revision_id TEXT NOT NULL,
                PRIMARY KEY (batch_id, revision_id)
            )
        ''')
        connection.execute('''
            CREATE TABLE IF NOT EXISTS scan_rows (
                batch_id TEXT NOT NULL,
                revision_id TEXT NOT NULL,
                ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
                x0 TEXT NOT NULL,
                x1 TEXT NOT NULL,
                y0 TEXT NOT NULL,
                y1 TEXT NOT NULL,
                weight TEXT NOT NULL,
                source_record TEXT NOT NULL,
                scan_start TEXT NOT NULL,
                scan_end TEXT NOT NULL,
                PRIMARY KEY (batch_id, revision_id, ordinal),
                FOREIGN KEY (batch_id, revision_id)
                    REFERENCES revisions (batch_id, revision_id)
            )
        ''')
        connection.execute('''
            CREATE TABLE IF NOT EXISTS current_revisions (
                batch_id TEXT PRIMARY KEY NOT NULL,
                revision_id TEXT NOT NULL,
                FOREIGN KEY (batch_id, revision_id)
                    REFERENCES revisions (batch_id, revision_id)
            )
        ''')
