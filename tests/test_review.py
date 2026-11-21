from fractions import Fraction

from analysis.request import ReviewRequestError, review
from issue.envelope import IssueIdentity
from issue.issue import issue
from receipt.intake import receive
from report.publish import SignStorageError
from report.readback import ReportNotFound, read
from tests.fixtures import ProjectCase, SAMPLES, receive_segments, register_sample, report_counts, scenario


class ReviewTests(ProjectCase):
    def test_two_paired_batches(self):
        station = self.open_station()
        center = self.open_center()
        high = register_sample(station, 'high-scan.json', batch_id='QH-high')
        low = register_sample(station, 'low-scan.json', batch_id='QH-low')
        packages = [issue(station, *revision.key.as_tuple()) for revision in (high, low)]
        receipts = [receive(center, package.package_text, package.identity) for package in packages]
        self.stop_station(station)
        self.assertFalse(self.station_path.exists())
        signed = [review(center, receipt.receipt_id, '0') for receipt in receipts]
        actual = [entry.report.outcome.value for entry in signed]
        self.assertEqual(actual, [Fraction(2), Fraction(0)])
        self.assertEqual([entry.report.outcome.status for entry in signed], ['numeric', 'numeric'])
        parents = []
        for entry, receipt, package in zip(signed, receipts, packages):
            saved = read(center, entry.report.report_id)
            self.assertEqual(saved.report, entry.report)
            self.assertEqual(saved.acknowledgment, entry.acknowledgment)
            self.assertEqual(saved.parent.package_text, package.package_text)
            self.assertEqual(saved.parent.identity, package.identity)
            self.assertEqual(saved.parent.acknowledgment, receipt)
            self.assertEqual(saved.report.receipt_id, receipt.receipt_id)
            parents.append(saved.parent.receipt_id)
        scenario('V4', {'tick': '0', 'batches': ['QH-high', 'QH-low'],
                        'samples': ['samples/high-scan.json', 'samples/low-scan.json']},
                 ['2', '0'], list(map(str, actual)),
                 [item.receipt_id for item in receipts], parents,
                 ['issue/issue.py', 'receipt/intake.py', 'analysis/request.py',
                  'analysis/median_limit.py', 'report/readback.py'],
                 'For 0 < epsilon < 1 the added mass epsilon/4 is above 2 or below 0. Compare it to half the total mass.')

    def test_direct_joint(self):
        center = self.open_center()
        self.assertFalse(self.station_path.exists())
        package = (SAMPLES / 'high-joint-v1.json').read_text(encoding='utf-8')
        identity = IssueIdentity('handoff-QH-27-Z', 'QH-27', 'Z')
        receipt = receive(center, package, identity)
        signed = review(center, receipt.receipt_id, 0)
        self.assertEqual(signed.report.outcome.value, Fraction(2))
        stored = read(center, signed.report.report_id)
        self.assertEqual(stored.parent.identity, identity)
        self.assertEqual(stored.parent.package_text, package)
        self.assertEqual(stored.report, signed.report)
        scenario('V4.direct_joint', {'tick': '0', 'sample': 'samples/high-joint-v1.json'},
                 '2', str(stored.report.outcome.value), identity.issue_id,
                 stored.parent.identity.issue_id,
                 ['receipt/intake.py', 'analysis/median_limit.py', 'report/readback.py'],
                 'At 0 the cumulative mass is 1/4, below the threshold 1/4 + epsilon/8.')

    def test_zero_result(self):
        station = self.open_station()
        center = self.open_center()
        low = register_sample(station, 'low-scan.json')
        package = issue(station, *low.key.as_tuple())
        receipt = receive(center, package.package_text, package.identity)
        self.stop_station(station)
        signed = review(center, receipt.receipt_id, 0)
        saved = read(center, signed.report.report_id)
        self.assertEqual((saved.report.outcome.status, saved.report.outcome.value),
                         ('numeric', Fraction(0)))
        self.assertEqual(center.execute('SELECT result_value FROM reports').fetchone()[0], '0')

    def test_continuous_boundary_and_empty(self):
        center = self.open_center()
        receipt = receive_segments(center, 'ascending', [(0, 1, 5, 6, 1)])
        at_start = review(center, receipt.receipt_id, '0')
        out_of_range = review(center, receipt.receipt_id, '3')
        self.assertEqual(at_start.report.outcome.value, Fraction(5))
        self.assertEqual(out_of_range.report.outcome.status, 'no_evidence')
        self.assertIsNone(out_of_range.report.outcome.value)
        self.assertEqual(read(center, at_start.report.report_id).report, at_start.report)
        saved_empty = read(center, out_of_range.report.report_id)
        self.assertEqual(saved_empty.report, out_of_range.report)
        self.assertEqual(saved_empty.parent.receipt_id, receipt.receipt_id)
        self.assertEqual(saved_empty.acknowledgment, out_of_range.acknowledgment)
        scenario('V5', {'segment': [0, 1, 5, 6, 1], 'ticks': ['0', '3']},
                 ['5', 'no_evidence'], [str(at_start.report.outcome.value), out_of_range.report.outcome.status],
                 [receipt.receipt_id, 'no_evidence'],
                 [saved_empty.parent.receipt_id, saved_empty.report.outcome.status],
                 ['analysis/window_mass.py', 'analysis/response_sweep.py', 'report/readback.py'],
                 'The endpoint median is 5 + epsilon/2, and windows around 3 eventually miss the segment.')

    def test_descending_endpoint(self):
        center = self.open_center()
        for issue_id, y0, y1, expected in [('tail-six', 5, 6, 6), ('tail-zero', -1, 0, 0)]:
            with self.subTest(issue_id=issue_id):
                receipt = receive_segments(center, issue_id, [(1, 0, y0, y1, 1)])
                signed = review(center, receipt.receipt_id, 0)
                saved = read(center, signed.report.report_id)
                self.assertEqual(saved.report.outcome.status, 'numeric')
                self.assertEqual(saved.report.outcome.value, Fraction(expected))
                self.assertEqual(saved.parent.receipt_id, receipt.receipt_id)

    def test_overlap_mass_and_half_threshold(self):
        center = self.open_center()
        cases = [
            ('point-overlap', [(0, 0, 0, 0, 1), (0, 0, 0, 0, 1), (0, 0, 2, 2, '3/2')], 0),
            ('continuous-overlap', [(0, 0, 0, 2, 2), (0, 0, 3, 1, 2)], '3/2'),
            ('exact-half-gap', [(0, 0, 0, 1, 1), (0, 0, 2, 3, 1)], 1),
        ]
        for issue_id, rows, expected in cases:
            with self.subTest(issue_id=issue_id):
                receipt = receive_segments(center, issue_id, rows)
                result = review(center, receipt.receipt_id, 0)
                self.assertEqual(result.report.outcome.value, Fraction(expected))

    def test_unknown_receipt(self):
        center = self.open_center()
        receipt = receive_segments(center, 'known', [(0, 0, 1, 1, 1)])
        with self.assertRaisesRegex(ReviewRequestError, 'unknown receipt'):
            review(center, receipt.receipt_id + 1, 0)
        self.assertEqual(report_counts(center), (0, 0))
        with self.assertRaises(ReportNotFound):
            read(center, 1)

    def test_invalid_tick(self):
        center = self.open_center()
        receipt = receive_segments(center, 'valid-parent', [(0, 0, 1, 1, 1)])
        for tick in ['1/0', None, True, 0.5]:
            with self.subTest(tick=tick):
                with self.assertRaisesRegex(ReviewRequestError, 'exact rational'):
                    review(center, receipt.receipt_id, tick)
                self.assertEqual(report_counts(center), (0, 0))

    def test_sign_failure_rolls_back(self):
        center = self.open_center()
        receipt = receive_segments(center, 'signing', [(0, 0, 1, 1, 1)])
        center.execute('''
            CREATE TEMP TRIGGER reject_next_ack BEFORE INSERT ON report_acknowledgments
            BEGIN SELECT RAISE(ABORT, 'first acknowledgment storage is unavailable'); END
        ''')
        with self.assertRaisesRegex(SignStorageError, 'signing transaction failed'):
            review(center, receipt.receipt_id, 0)
        observer = self.open_center()
        self.assertEqual(report_counts(observer), (0, 0))
        with self.assertRaises(ReportNotFound):
            read(observer, 1)

        center.execute('DROP TRIGGER reject_next_ack')
        signed = review(center, receipt.receipt_id, 0)
        self.assertEqual(report_counts(observer), (1, 1))
        self.assertEqual(read(observer, signed.report.report_id).acknowledgment, signed.acknowledgment)
