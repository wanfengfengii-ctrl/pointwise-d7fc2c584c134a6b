import sqlite3

from issue.envelope import IssueIdentity, decode_envelope
from receipt.body_validation import validate_joint_body
from receipt.identity import require_expected_identity
from receipt.receipt_store import IntakeAcknowledgment, ReceiptStore


class ReceiptRejected(ValueError):
    """The center refused the submitted package."""


def receive(
    center: sqlite3.Connection, package_text: str, expected_identity: IssueIdentity
) -> IntakeAcknowledgment:
    try:
        envelope = decode_envelope(package_text)
        require_expected_identity(envelope.identity, expected_identity)
        validate_joint_body(envelope.body)
        saved = ReceiptStore(center).record_receipt(envelope.identity, package_text)
    except ValueError as exc:
        raise ReceiptRejected(str(exc)) from exc
    return saved.acknowledgment
