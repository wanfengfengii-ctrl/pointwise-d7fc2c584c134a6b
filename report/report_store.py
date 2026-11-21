import sqlite3
from fractions import Fraction

from analysis.result import ReviewOutcome
from measurement_values import is_record_number
from report.report_record import (
    FirstAcknowledgment, ReportRecord, ReviewPublication, decode_report_result,
    encode_report_result,
)


class ReportStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def initialize(self) -> None:
        connection = self.connection
        connection.execute('PRAGMA foreign_keys = ON')
        connection.execute('BEGIN IMMEDIATE')
        with connection:
            connection.execute('''
                CREATE TABLE IF NOT EXISTS reports (
                    report_id INTEGER PRIMARY KEY,
                    receipt_id INTEGER NOT NULL REFERENCES receipts (receipt_id),
                    tick TEXT NOT NULL,
                    result_status TEXT NOT NULL,
                    result_value TEXT,
                    CHECK ((result_status = 'numeric' AND result_value IS NOT NULL)
                        OR (result_status = 'no_evidence' AND result_value IS NULL))
                )
            ''')
            connection.execute('''
                CREATE TABLE IF NOT EXISTS report_acknowledgments (
                    report_id INTEGER PRIMARY KEY REFERENCES reports (report_id),
                    confirmation TEXT NOT NULL UNIQUE
                )
            ''')

    def commit_report(
        self, receipt_id: int, tick: Fraction, outcome: ReviewOutcome
    ) -> ReviewPublication:
        status, value = encode_report_result(outcome)
        connection = self.connection
        connection.execute('BEGIN IMMEDIATE')
        with connection:
            inserted = connection.execute('''
                INSERT INTO reports (receipt_id, tick, result_status, result_value)
                VALUES (?, ?, ?, ?)
            ''', (receipt_id, str(tick), status, value))
            report_id = inserted.lastrowid
            confirmation = f'review-{report_id}'
            connection.execute('''
                INSERT INTO report_acknowledgments (report_id, confirmation) VALUES (?, ?)
            ''', (report_id, confirmation))
        return ReviewPublication(
            ReportRecord(report_id, receipt_id, tick, outcome),
            FirstAcknowledgment(report_id, confirmation),
        )

    def get_report(self, report_id: int) -> ReviewPublication | None:
        if not is_record_number(report_id):
            return None
        row = self.connection.execute('''
            SELECT r.receipt_id, r.tick, r.result_status, r.result_value, a.confirmation
            FROM reports AS r JOIN report_acknowledgments AS a USING (report_id)
            WHERE r.report_id = ?
        ''', (report_id,)).fetchone()
        if row is None:
            return None
        receipt_id, tick, status, value, confirmation = row
        return ReviewPublication(
            ReportRecord(report_id, receipt_id, Fraction(tick), decode_report_result(status, value)),
            FirstAcknowledgment(report_id, confirmation),
        )
