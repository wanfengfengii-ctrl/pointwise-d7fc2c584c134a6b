import json
import sqlite3
from fractions import Fraction

from analysis.request import ReviewRequestError, sign_mix
from issue.envelope import IssueIdentity
from receipt.intake import receive
from receipt.receipt_store import ReceiptStore
from report.mix_record import MixInterval
from report.publish import SignStorageError
from report.readback import ReportNotFound, read_mix
from report.report_store import ReportStore
from tests.fixtures import ProjectCase, receive_segments
from mix_inputs import receive_sample_pair


def _interval_text(intervals):
    return [(str(item.lo), str(item.hi), item.lo_closed, item.hi_closed) for item in intervals]


class MixSigningTests(ProjectCase):
    def test_sample_pair_declared_zero(self):
        station = self.open_station()
        center = self.open_center()
        left, right = receive_sample_pair(station, center)
        self.stop_station(station)
        signed = sign_mix(center, left.receipt_id, right.receipt_id, 0, 0, 0)
        report = signed.report
        self.assertEqual(report.receipt_ids, (left.receipt_id, right.receipt_id))
        self.assertEqual((report.tick, report.lo, report.hi),
                         (Fraction(0), Fraction(0), Fraction(0)))
        self.assertEqual(_interval_text(report.intervals), [('1/2', '1', False, True)])
        self.assertEqual(signed.acknowledgment.confirmation, f'mix-{report.report_id}')

        saved = read_mix(center, report.report_id)
        self.assertEqual(saved.report, report)
        self.assertEqual(saved.acknowledgment, signed.acknowledgment)
        self.assertEqual([parent.receipt_id for parent in saved.parents],
                         [left.receipt_id, right.receipt_id])
        self.assertEqual([parent.acknowledgment for parent in saved.parents], [left, right])
        self.assertEqual(len(saved.parents), 2)
        for parent, ack in zip(saved.parents, (left, right)):
            self.assertEqual(parent.acknowledgment, ack)
            self.assertTrue(parent.package_text)

    def test_swapped_order_mirrors_intervals(self):
        station = self.open_station()
        center = self.open_center()
        left, right = receive_sample_pair(station, center)
        self.stop_station(station)
        swapped = sign_mix(center, right.receipt_id, left.receipt_id, '0', '0', '0')
        self.assertEqual(_interval_text(swapped.report.intervals), [('0', '1/2', True, False)])
        self.assertEqual(swapped.report.receipt_ids, (right.receipt_id, left.receipt_id))

    def test_uniform_sweep_signs_full_domain(self):
        center = self.open_center()
        first = receive_segments(center, 'uniform-one', [(0, 0, -1, 1, 1)])
        identity = IssueIdentity('uniform-two-issue', 'fixture-batch-other', 'fixture-revision')
        fields = ('x0', 'x1', 'y0', 'y1', 'weight')
        text = json.dumps({
            'version': 1,
            'issue_id': identity.issue_id,
            'batch_id': identity.batch_id,
            'revision_id': identity.revision_id,
            'body': {'joint_segments': [dict(zip(fields, ('0', '0', '-1', '1', '1')))]},
        })
        other = receive(center, text, identity)
        signed = sign_mix(center, first.receipt_id, other.receipt_id, 0, 0, 0)
        self.assertEqual(_interval_text(signed.report.intervals), [('0', '1', True, True)])

    def test_singleton_and_empty_results(self):
        center = self.open_center()
        # Both pieces sweep in y at the tick with continuous density.
        a = receive_segments(center, 'sweep-a', [(0, 0, 0, 2, 1)])
        identity = IssueIdentity('sweep-b', 'fixture-batch-other', 'fixture-revision')
        fields = ('x0', 'x1', 'y0', 'y1', 'weight')
        text = json.dumps({
            'version': 1, 'issue_id': identity.issue_id, 'batch_id': identity.batch_id,
            'revision_id': identity.revision_id,
            'body': {'joint_segments': [dict(zip(fields, ('0', '0', '2', '4', '1')))]},
        })
        b = receive(center, text, identity)
        # m(p) = 3 only at p = 0 on this construction -> closed singleton.
        singleton = sign_mix(center, a.receipt_id, b.receipt_id, 0, 3, 3)
        self.assertEqual(_interval_text(singleton.report.intervals), [('0', '0', True, True)])
        # A target no median can reach -> empty tuple persisted and read back.
        empty = sign_mix(center, a.receipt_id, b.receipt_id, 0, 9, 9)
        self.assertEqual(empty.report.intervals, ())
        saved = read_mix(center, empty.report.report_id)
        self.assertEqual(saved.report.intervals, ())

    def test_no_evidence_when_windows_are_empty(self):
        center = self.open_center()
        a = receive_segments(center, 'far-a', [(1, 2, 3, 3, 1)])
        identity = IssueIdentity('far-b', 'fixture-batch-other', 'fixture-revision')
        fields = ('x0', 'x1', 'y0', 'y1', 'weight')
        text = json.dumps({
            'version': 1, 'issue_id': identity.issue_id, 'batch_id': identity.batch_id,
            'revision_id': identity.revision_id,
            'body': {'joint_segments': [dict(zip(fields, ('6', '7', '8', '8', '1')))]},
        })
        b = receive(center, text, identity)
        signed = sign_mix(center, a.receipt_id, b.receipt_id, 5, 0, 0)
        self.assertEqual(signed.report.intervals, ())
        saved = read_mix(center, signed.report.report_id)
        self.assertEqual(saved.report.intervals, ())

    def test_endpoint_openness_is_preserved(self):
        center = self.open_center()
        a = receive_segments(center, 'open-a', [(0, 1, 0, 0, 1)])
        identity = IssueIdentity('open-b', 'fixture-batch-other', 'fixture-revision')
        fields = ('x0', 'x1', 'y0', 'y1', 'weight')
        text = json.dumps({
            'version': 1, 'issue_id': identity.issue_id, 'batch_id': identity.batch_id,
            'revision_id': identity.revision_id,
            'body': {'joint_segments': [dict(zip(fields, ('0', '1', '2', '2', '1')))]},
        })
        b = receive(center, text, identity)
        zero_target = sign_mix(center, a.receipt_id, b.receipt_id, 0, 0, 0)
        # At the tie p = 1/2 both window masses are equal and the lower median
        # is the smaller response 0, so the left endpoint is closed.
        self.assertEqual(_interval_text(zero_target.report.intervals),
                         [('1/2', '1', True, True)])
        two_target = sign_mix(center, a.receipt_id, b.receipt_id, 0, 2, 2)
        self.assertEqual(_interval_text(two_target.report.intervals),
                         [('0', '1/2', True, False)])


class MixValidationTests(ProjectCase):
    def _two_receipts(self, center):
        a = receive_segments(center, 'valid-a', [(0, 0, 1, 1, 1)])
        identity = IssueIdentity('valid-b', 'fixture-batch-other', 'fixture-revision')
        fields = ('x0', 'x1', 'y0', 'y1', 'weight')
        text = json.dumps({
            'version': 1, 'issue_id': identity.issue_id, 'batch_id': identity.batch_id,
            'revision_id': identity.revision_id,
            'body': {'joint_segments': [dict(zip(fields, ('0', '0', '2', '2', '1')))]},
        })
        b = receive(center, text, identity)
        return a, b

    def test_invalid_tick_and_bounds(self):
        center = self.open_center()
        a, b = self._two_receipts(center)
        for kwargs in (
            dict(tick='1/0', lo=0, hi=0),
            dict(tick=0, lo=None, hi=0),
            dict(tick=0, lo=0.5, hi=0),
            dict(tick=True, lo=0, hi=0),
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ReviewRequestError):
                    sign_mix(center, a.receipt_id, b.receipt_id, **kwargs)
                self.assertEqual(center.execute('SELECT COUNT(*) FROM mix_reports').fetchone()[0], 0)

    def test_inverted_target_rejected(self):
        center = self.open_center()
        a, b = self._two_receipts(center)
        with self.assertRaisesRegex(ReviewRequestError, 'must not exceed'):
            sign_mix(center, a.receipt_id, b.receipt_id, 0, 1, 0)

    def test_unknown_and_invalid_receipt_ids(self):
        center = self.open_center()
        a, b = self._two_receipts(center)
        with self.assertRaisesRegex(ReviewRequestError, 'unknown'):
            sign_mix(center, a.receipt_id, b.receipt_id + 100, 0, 0, 0)
        for bad in (0, -1, 1.5, '1', None):
            with self.subTest(bad=bad):
                with self.assertRaises(ReviewRequestError):
                    sign_mix(center, bad, b.receipt_id, 0, 0, 0)
        self.assertEqual(center.execute('SELECT COUNT(*) FROM mix_reports').fetchone()[0], 0)

    def test_same_record_and_same_batch_rejected(self):
        station = self.open_station()
        center = self.open_center()
        left, right = receive_sample_pair(station, center)
        with self.assertRaisesRegex(ReviewRequestError, 'different records'):
            sign_mix(center, left.receipt_id, left.receipt_id, 0, 0, 0)
        same_batch = receive_segments(center, 'same-batch', [(0, 0, 1, 1, 1)])
        other = receive_segments(center, 'same-batch-again', [(0, 0, 2, 2, 1)])
        with self.assertRaisesRegex(ReviewRequestError, 'different batches'):
            sign_mix(center, same_batch.receipt_id, other.receipt_id, 0, 0, 0)
        self.assertEqual(center.execute('SELECT COUNT(*) FROM mix_reports').fetchone()[0], 0)

    def test_corrupt_stored_parent_rejected(self):
        center = self.open_center()
        a, b = self._two_receipts(center)
        center.execute('UPDATE receipts SET package_text = ? WHERE receipt_id = ?',
                       ('{not json', a.receipt_id))
        with self.assertRaisesRegex(ReviewRequestError, 'invalid stored'):
            sign_mix(center, a.receipt_id, b.receipt_id, 0, 0, 0)
        self.assertEqual(center.execute('SELECT COUNT(*) FROM mix_reports').fetchone()[0], 0)

    def test_unknown_mix_report_readback(self):
        center = self.open_center()
        with self.assertRaises(ReportNotFound):
            read_mix(center, 4242)


class MixStorageTests(ProjectCase):
    def test_sign_failure_rolls_back_and_is_retryable(self):
        center = self.open_center()
        a = receive_segments(center, 'store-a', [(0, 0, 1, 1, 1)])
        identity = IssueIdentity('store-b', 'fixture-batch-other', 'fixture-revision')
        fields = ('x0', 'x1', 'y0', 'y1', 'weight')
        text = json.dumps({
            'version': 1, 'issue_id': identity.issue_id, 'batch_id': identity.batch_id,
            'revision_id': identity.revision_id,
            'body': {'joint_segments': [dict(zip(fields, ('0', '0', '2', '2', '1')))]},
        })
        b = receive(center, text, identity)
        center.execute('''
            CREATE TEMP TRIGGER reject_mix_ack BEFORE INSERT ON mix_acknowledgments
            BEGIN SELECT RAISE(ABORT, 'mix acknowledgment storage is unavailable'); END
        ''')
        with self.assertRaisesRegex(SignStorageError, 'mix signing transaction failed'):
            sign_mix(center, a.receipt_id, b.receipt_id, 0, 0, 0)
        self.assertEqual(center.execute('SELECT COUNT(*) FROM mix_reports').fetchone()[0], 0)
        self.assertEqual(center.execute('SELECT COUNT(*) FROM mix_intervals').fetchone()[0], 0)
        self.assertEqual(center.execute('SELECT COUNT(*) FROM mix_acknowledgments').fetchone()[0], 0)

        center.execute('DROP TRIGGER reject_mix_ack')
        signed = sign_mix(center, a.receipt_id, b.receipt_id, 0, 0, 0)
        observer = self.open_center()
        row = observer.execute('SELECT COUNT(*) FROM mix_reports').fetchone()[0]
        self.assertEqual(row, 1)
        saved = read_mix(observer, signed.report.report_id)
        self.assertEqual(saved.acknowledgment, signed.acknowledgment)

    def test_reopen_preserves_report_parents_and_first_ack(self):
        station = self.open_station()
        center_path = self.center_path
        with sqlite3.connect(center_path) as center:
            ReceiptStore(center).initialize()
            ReportStore(center).initialize()
            left, right = receive_sample_pair(station, center)
            signed = sign_mix(center, left.receipt_id, right.receipt_id, '0', '0', '0')
            report_id = signed.report.report_id
        self.stop_station(station)

        reopened = self.open_center()
        saved = read_mix(reopened, report_id)
        self.assertEqual(saved.report, signed.report)
        self.assertEqual(saved.acknowledgment, signed.acknowledgment)
        self.assertEqual([parent.package_text for parent in saved.parents],
                         [left_pkg for left_pkg in (
                             ReceiptStore(reopened).get_receipt(left.receipt_id).package_text,
                             ReceiptStore(reopened).get_receipt(right.receipt_id).package_text)])
        self.assertEqual([parent.acknowledgment for parent in saved.parents], [left, right])

    def test_interval_dataclass_validation(self):
        interval = MixInterval(Fraction(0), Fraction(0), True, True)
        self.assertEqual(interval.as_text(), ('0', '0', 1, 1))
        with self.assertRaises(ValueError):
            MixInterval(Fraction(1), Fraction(0), True, True)
        with self.assertRaises(ValueError):
            MixInterval(Fraction(0), Fraction(0), False, True)
        with self.assertRaises(ValueError):
            MixInterval(Fraction(0), Fraction(0), True, False)
