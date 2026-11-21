import sys
from fractions import Fraction

from analysis.median_limit import compute_median_limit
from analysis.request import review
from issue.issue import issue
from issue.issue_store import IssueStore
from receipt.intake import receive
from receipt.receipt_store import ReceiptStore
from report.readback import read
from station.revision_store import RevisionStore
from tests.fixtures import ProjectCase, register_sample, report_counts, scenario


class HistoryTests(ProjectCase):
    def test_revision_and_reopen(self):
        station = self.open_station()
        center = self.open_center()
        initial = register_sample(station, 'high-scan.json')
        first = issue(station, *initial.key.as_tuple())
        first_receipt = receive(center, first.package_text, first.identity)
        offline_path = self.stop_station(station)
        old = review(center, first_receipt.receipt_id, 0)
        self.assertEqual(old.report.outcome.value, Fraction(2))

        offline_path.rename(self.station_path)
        station = self.open_station()
        amended = register_sample(station, 'low-scan.json')
        second = issue(station, *amended.key.as_tuple())
        self.assertEqual(issue(station, *initial.key.as_tuple()), first)
        second_receipt = receive(center, second.package_text, second.identity)
        self.stop_station(station)
        new = review(center, second_receipt.receipt_id, 0)
        self.assertEqual(new.report.outcome.value, Fraction(0))
        self.assertNotEqual(old.report.report_id, new.report.report_id)
        center.close()

        reopened = self.open_center()
        again = [read(reopened, entry.report.report_id) for entry in (old, new)]
        for saved, signed, parent, intake in zip(again, (old, new), (first, second),
                                                (first_receipt, second_receipt)):
            self.assertEqual(saved.report, signed.report)
            self.assertEqual(saved.acknowledgment, signed.acknowledgment)
            self.assertEqual(saved.parent.identity, parent.identity)
            self.assertEqual(saved.parent.package_text, parent.package_text)
            self.assertEqual(saved.parent.acknowledgment, intake)
            self.assertEqual(saved.report.receipt_id, saved.parent.receipt_id)
        self.assertEqual(report_counts(reopened), (2, 2))
        scenario('V8', {'batch': initial.key.batch_id, 'revisions': ['Z', 'A'], 'tick': '0'},
                 ['2', '0'], [str(item.report.outcome.value) for item in again],
                 [[first_receipt.receipt_id, 'Z'], [second_receipt.receipt_id, 'A']],
                 [[item.parent.receipt_id, item.parent.identity.revision_id] for item in again],
                 ['station/revision_store.py', 'issue/issue_store.py', 'analysis/request.py',
                  'report/report_store.py', 'report/readback.py'],
                 'Hand-calculated positive-window medians, compared against the originally signed records and receipts.')

    def test_current_after_reopen(self):
        station = self.open_station()
        initial = register_sample(station, 'high-scan.json')
        first = issue(station, *initial.key.as_tuple())
        amended = register_sample(station, 'low-scan.json')
        second = issue(station, *amended.key.as_tuple())
        station.close()
        reopened = self.open_station()
        RevisionStore(reopened).initialize()
        IssueStore(reopened).initialize()
        store = RevisionStore(reopened)
        self.assertEqual(amended.key.revision_id, 'A')
        self.assertEqual(store.get_current(initial.key.batch_id), amended)
        self.assertEqual(store.get_revision(initial.key), initial)
        self.assertEqual(store.get_revision(amended.key), amended)
        self.assertEqual(issue(reopened, *initial.key.as_tuple()), first)
        self.assertEqual(issue(reopened, *amended.key.as_tuple()), second)

    def test_saved_history(self):
        station = self.open_station()
        center = self.open_center()
        initial = register_sample(station, 'high-scan.json')
        first = issue(station, *initial.key.as_tuple())
        ack = receive(center, first.package_text, first.identity)
        historic_parent = ReceiptStore(center).get_receipt(ack.receipt_id)
        self.stop_station(station)
        signed = review(center, ack.receipt_id, 0)
        center.close()
        reopened = self.open_center()
        observed = []
        review_code = {review.__code__, compute_median_limit.__code__}

        def watch(frame, event, arg):
            if event == 'call' and frame.f_code in review_code:
                observed.append(frame.f_code.co_name)

        prior = sys.getprofile()
        sys.setprofile(watch)
        try:
            original = read(reopened, signed.report.report_id)
        finally:
            sys.setprofile(prior)
        self.assertEqual(observed, [])
        self.assertEqual(original.report, signed.report)
        self.assertEqual(original.parent, historic_parent)
        self.assertEqual(original.acknowledgment, signed.acknowledgment)
        self.assertEqual(report_counts(reopened), (1, 1))
