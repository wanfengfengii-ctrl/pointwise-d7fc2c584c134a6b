import sqlite3
from fractions import Fraction

from analysis.result import ReviewOutcome
from measurement_values import is_record_number
from report.mix_record import MixInterval, MixReport, MixPublication
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
            connection.execute('''
                CREATE TABLE IF NOT EXISTS mix_reports (
                    report_id INTEGER PRIMARY KEY,
                    left_receipt_id INTEGER NOT NULL REFERENCES receipts (receipt_id),
                    right_receipt_id INTEGER NOT NULL REFERENCES receipts (receipt_id),
                    tick TEXT NOT NULL,
                    lo TEXT NOT NULL,
                    hi TEXT NOT NULL,
                    CHECK (left_receipt_id <> right_receipt_id)
                )
            ''')
            connection.execute('''
                CREATE TABLE IF NOT EXISTS mix_intervals (
                    report_id INTEGER NOT NULL REFERENCES mix_reports (report_id),
                    ordinal INTEGER NOT NULL,
                    lo TEXT NOT NULL,
                    hi TEXT NOT NULL,
                    lo_closed INTEGER NOT NULL CHECK (lo_closed IN (0, 1)),
                    hi_closed INTEGER NOT NULL CHECK (hi_closed IN (0, 1)),
                    PRIMARY KEY (report_id, ordinal)
                )
            ''')
            connection.execute('''
                CREATE TABLE IF NOT EXISTS mix_acknowledgments (
                    report_id INTEGER PRIMARY KEY REFERENCES mix_reports (report_id),
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

    def commit_mix_report(
        self,
        receipt_ids: tuple[int, int],
        tick: Fraction,
        low: Fraction,
        high: Fraction,
        intervals: tuple[MixInterval, ...],
    ) -> MixPublication:
        left_receipt_id, right_receipt_id = receipt_ids
        connection = self.connection
        connection.execute('BEGIN IMMEDIATE')
        with connection:
            inserted = connection.execute('''
                INSERT INTO mix_reports
                    (left_receipt_id, right_receipt_id, tick, lo, hi)
                VALUES (?, ?, ?, ?, ?)
            ''', (left_receipt_id, right_receipt_id, str(tick), str(low), str(high)))
            report_id = inserted.lastrowid
            connection.executemany('''
                INSERT INTO mix_intervals
                    (report_id, ordinal, lo, hi, lo_closed, hi_closed)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', [
                (report_id, ordinal, *interval.as_text())
                for ordinal, interval in enumerate(intervals)
            ])
            confirmation = f'mix-{report_id}'
            connection.execute('''
                INSERT INTO mix_acknowledgments (report_id, confirmation) VALUES (?, ?)
            ''', (report_id, confirmation))
        return MixPublication(
            MixReport(report_id, receipt_ids, tick, low, high, intervals),
            FirstAcknowledgment(report_id, confirmation),
        )

    def get_mix_report(self, report_id: int) -> MixPublication | None:
        if not is_record_number(report_id):
            return None
        row = self.connection.execute('''
            SELECT left_receipt_id, right_receipt_id, tick, lo, hi, confirmation
            FROM mix_reports JOIN mix_acknowledgments USING (report_id)
            WHERE report_id = ?
        ''', (report_id,)).fetchone()
        if row is None:
            return None
        left_receipt_id, right_receipt_id, tick, low, high, confirmation = row
        interval_rows = self.connection.execute('''
            SELECT lo, hi, lo_closed, hi_closed FROM mix_intervals
            WHERE report_id = ? ORDER BY ordinal
        ''', (report_id,)).fetchall()
        intervals = tuple(MixInterval.from_stored(*stored) for stored in interval_rows)
        return MixPublication(
            MixReport(
                report_id, (left_receipt_id, right_receipt_id), Fraction(tick),
                Fraction(low), Fraction(high), intervals,
            ),
            FirstAcknowledgment(report_id, confirmation),
        )
