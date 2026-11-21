from dataclasses import dataclass

from receipt.receipt_store import ReceiptRecord
from report.report_record import FirstAcknowledgment, ReportRecord, ReviewPublication


@dataclass(frozen=True)
class ReportReadback:
    report: ReportRecord
    parent: ReceiptRecord
    acknowledgment: FirstAcknowledgment


def export_readback(publication: ReviewPublication, parent: ReceiptRecord) -> ReportReadback:
    if publication.report.receipt_id != parent.receipt_id:
        raise ValueError('readback parent does not match the committed report')
    return ReportReadback(publication.report, parent, publication.acknowledgment)
