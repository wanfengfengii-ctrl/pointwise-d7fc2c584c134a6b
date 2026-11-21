import sqlite3
from fractions import Fraction

from analysis.median_limit import compute_median_limit
from issue.envelope import decode_envelope
from measurement_values import is_record_number, parse_rational
from receipt.body_validation import validate_joint_body
from receipt.receipt_store import ReceiptStore
from report.publish import publish_review
from report.report_record import ReviewPublication
from report.report_store import ReportStore


class ReviewRequestError(ValueError):
    """The requested tick or parent cannot be used for review."""


def parse_review_tick(tick: object) -> Fraction:
    try:
        return parse_rational(tick, 'old instrument tick')
    except ValueError as exc:
        raise ReviewRequestError(str(exc)) from exc


def review(center: sqlite3.Connection, receipt_id: int, tick: object) -> ReviewPublication:
    tick_value = parse_review_tick(tick)
    if not is_record_number(receipt_id):
        raise ReviewRequestError('receipt id must be a positive SQLite record number')
    parent = ReceiptStore(center).get_receipt(receipt_id)
    if parent is None:
        raise ReviewRequestError(f'unknown receipt: {receipt_id}')
    try:
        envelope = decode_envelope(parent.package_text)
        if envelope.identity != parent.identity:
            raise ValueError('receipt identity disagrees with the saved envelope')
        segments = validate_joint_body(envelope.body)
    except ValueError as exc:
        raise ReviewRequestError(f'invalid stored parent: {exc}') from exc
    outcome = compute_median_limit(segments, tick_value)
    return publish_review(ReportStore(center), parent.receipt_id, tick_value, outcome)
