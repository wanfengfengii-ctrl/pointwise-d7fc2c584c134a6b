import sqlite3
from fractions import Fraction

from analysis.result import ReviewOutcome
from report.report_record import ReviewPublication
from report.report_store import ReportStore


class SignStorageError(RuntimeError):
    """The report and first acknowledgment could not be committed."""


def publish_review(
    store: ReportStore, receipt_id: int, tick: Fraction, outcome: ReviewOutcome
) -> ReviewPublication:
    try:
        return store.commit_report(receipt_id, tick, outcome)
    except sqlite3.Error as exc:
        raise SignStorageError('review signing transaction failed') from exc
