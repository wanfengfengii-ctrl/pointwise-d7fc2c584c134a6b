import sqlite3
from fractions import Fraction

from analysis.median_limit import compute_median_limit
from analysis.mixture import build_decomposition, merge_components
from issue.envelope import decode_envelope
from measurement_values import is_record_number, parse_rational
from receipt.body_validation import validate_joint_body
from receipt.receipt_store import ReceiptRecord, ReceiptStore
from report.mix_record import MixInterval, MixPublication
from report.publish import SignStorageError, publish_review
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


def _parse_bound(value: object, label: str) -> Fraction:
    try:
        return parse_rational(value, label)
    except ValueError as exc:
        raise ReviewRequestError(str(exc)) from exc


def _load_mix_parent(center: sqlite3.Connection, receipt_id: object, label: str) -> ReceiptRecord:
    if not is_record_number(receipt_id):
        raise ReviewRequestError(f'{label} receipt id must be a positive SQLite record number')
    parent = ReceiptStore(center).get_receipt(receipt_id)
    if parent is None:
        raise ReviewRequestError(f'unknown {label} receipt: {receipt_id}')
    try:
        envelope = decode_envelope(parent.package_text)
        if envelope.identity != parent.identity:
            raise ValueError('receipt identity disagrees with the saved envelope')
        validate_joint_body(envelope.body)
    except ValueError as exc:
        raise ReviewRequestError(f'invalid stored {label} parent: {exc}') from exc
    return parent


def sign_mix(
    center: sqlite3.Connection,
    left_receipt_id: object,
    right_receipt_id: object,
    tick: object,
    lo: object,
    hi: object,
) -> MixPublication:
    tick_value = parse_review_tick(tick)
    lo_value = _parse_bound(lo, 'mix target lo')
    hi_value = _parse_bound(hi, 'mix target hi')
    if lo_value > hi_value:
        raise ReviewRequestError('mix target lo must not exceed hi')
    if left_receipt_id == right_receipt_id:
        raise ReviewRequestError('the two mix receipts must be different records')

    left_parent = _load_mix_parent(center, left_receipt_id, 'left')
    right_parent = _load_mix_parent(center, right_receipt_id, 'right')
    if left_parent.identity.batch_id == right_parent.identity.batch_id:
        raise ReviewRequestError('the two mix receipts must come from different batches')

    left_segments = validate_joint_body(decode_envelope(left_parent.package_text).body)
    right_segments = validate_joint_body(decode_envelope(right_parent.package_text).body)
    components = build_decomposition(
        left_segments, right_segments, tick_value, lo_value, hi_value,
    )
    intervals = tuple(
        MixInterval(item.lo, item.hi, item.lo_closed, item.hi_closed)
        for item in merge_components(components)
    )
    try:
        return ReportStore(center).commit_mix_report(
            (left_parent.receipt_id, right_parent.receipt_id),
            tick_value, lo_value, hi_value, intervals,
        )
    except sqlite3.Error as exc:
        raise SignStorageError('mix signing transaction failed') from exc
