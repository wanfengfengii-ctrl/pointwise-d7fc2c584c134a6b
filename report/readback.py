import sqlite3

from receipt.receipt_store import ReceiptStore
from report.export import ReportReadback, export_readback
from report.report_store import ReportStore


class ReportNotFound(LookupError):
    """No signed report exists for this number."""


def read(center: sqlite3.Connection, report_id: int) -> ReportReadback:
    publication = ReportStore(center).get_report(report_id)
    if publication is None:
        raise ReportNotFound(f'unknown report: {report_id}')
    parent = ReceiptStore(center).get_receipt(publication.report.receipt_id)
    if parent is None:
        raise RuntimeError('committed report is missing its stored parent')
    return export_readback(publication, parent)
