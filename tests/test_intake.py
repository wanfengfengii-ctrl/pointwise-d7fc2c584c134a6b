import json
from fractions import Fraction

from issue.issue import RevisionNotFound, issue
from issue.issue_store import IssueStore
from receipt.intake import ReceiptRejected, receive
from receipt.receipt_store import ReceiptStore
from station.import_batch import RegistrationError, register
from station.revision_store import RevisionStore
from station.revisions import RevisionKey
from tests.fixtures import ProjectCase, read_sample, register_sample, scenario


def _public_marginal(rows, first, last):
    masses = {}
    for row in rows:
        bounds = Fraction(row[first]), Fraction(row[last])
        masses[bounds] = masses.get(bounds, Fraction(0)) + Fraction(row['weight'])
    return masses


def _small_window_atoms(rows, epsilon):
    masses = {}
    for row in rows:
        x0, x1, y0, y1, weight = (Fraction(row[key]) for key in ('x0', 'x1', 'y0', 'y1', 'weight'))
        if y0 != y1 or x0 < 0 or x1 < x0:
            raise AssertionError('the hand-audited samples use constant responses and ascending X')
        if x0 == x1:
            mass = weight if x0 <= epsilon else Fraction(0)
        else:
            mass = weight * max(Fraction(0), min(x1, epsilon) - x0) / (x1 - x0)
        if mass:
            masses[str(y0)] = str(Fraction(masses.get(str(y0), '0')) + mass)
    return masses


class IntakeTests(ProjectCase):
    def test_receive_frozen_revision(self):
        station = self.open_station()
        center = self.open_center()
        initial = register_sample(station, 'high-scan.json')
        first = issue(station, *initial.key.as_tuple())
        amended = register_sample(station, 'low-scan.json')
        self.assertEqual(RevisionStore(station).get_current(initial.key.batch_id), amended)
        self.assertEqual(issue(station, *initial.key.as_tuple()), first)
        self.assertEqual(IssueStore(station).get_issued(first.identity.issue_id), first)
        stored_rows = RevisionStore(station).get_revision(initial.key).rows
        self.assertEqual([row.source_record for row in stored_rows],
                         ['bench-Z-01', 'bench-Z-02', 'bench-Z-03', 'bench-Z-04'])
        self.assertEqual(stored_rows[-1].scan_start, Fraction(31))

        acknowledgment = receive(center, first.package_text, first.identity)
        repeated = receive(center, first.package_text, first.identity)
        self.assertEqual(repeated, acknowledgment)
        stored = ReceiptStore(center).get_receipt(acknowledgment.receipt_id)
        self.assertEqual(stored.identity, first.identity)
        self.assertEqual(stored.package_text, first.package_text)
        self.assertEqual(stored.acknowledgment, acknowledgment)
        self.assertEqual(center.execute('SELECT COUNT(*) FROM receipts').fetchone()[0], 1)

    def test_joint_mass(self):
        station = self.open_station()
        center = self.open_center()
        high = register_sample(station, 'high-scan.json', batch_id='QH-high')
        low = register_sample(station, 'low-scan.json', batch_id='QH-low')
        packages = [issue(station, *revision.key.as_tuple()) for revision in (high, low)]
        identities = []
        joint_rows = []
        for package in packages:
            ack = receive(center, package.package_text, package.identity)
            stored = ReceiptStore(center).get_receipt(ack.receipt_id)
            identities.append(stored.identity.batch_id)
            public_body = json.loads(stored.package_text)['body']
            self.assertEqual(set(public_body), {'joint_segments'})
            for row in public_body['joint_segments']:
                self.assertEqual(set(row), {'x0', 'x1', 'y0', 'y1', 'weight'})
            self.assertNotIn('bench-', stored.package_text)
            joint_rows.append(public_body['joint_segments'])
        self.assertEqual(_public_marginal(joint_rows[0], 'x0', 'x1'),
                         _public_marginal(joint_rows[1], 'x0', 'x1'))
        self.assertEqual(_public_marginal(joint_rows[0], 'y0', 'y1'),
                         _public_marginal(joint_rows[1], 'y0', 'y1'))
        epsilon = Fraction(1, 2)
        actual = [_small_window_atoms(rows, epsilon) for rows in joint_rows]
        expected = [{'0': '1/4', '2': '1/4', '3': '1/8'},
                    {'-1': '1/8', '0': '1/4', '2': '1/4'}]
        self.assertEqual(actual, expected)
        self.assertEqual(identities, ['QH-high', 'QH-low'])
        scenario('V1.joint_mass', {'epsilon': str(epsilon), 'bodies': joint_rows},
                 expected, actual, ['QH-high', 'QH-low'], identities,
                 ['issue/paired_measure.py', 'issue/issue.py', 'receipt/intake.py',
                  'receipt/receipt_store.py'],
                 'Each point has mass 1/4 and half of the first ramp contributes 1/8 at its constant response.')

    def test_invalid_body_and_conflicting_reissue(self):
        station = self.open_station()
        center = self.open_center()
        revision = register_sample(station, 'high-scan.json')
        package = issue(station, *revision.key.as_tuple())
        for weight in ('0', '-1', '1/0', True):
            with self.subTest(weight=weight):
                malformed = json.loads(package.package_text)
                malformed['body']['joint_segments'][-1]['weight'] = weight
                with self.assertRaises(ReceiptRejected):
                    receive(center, json.dumps(malformed), package.identity)
        missing = json.loads(package.package_text)
        del missing['body']['joint_segments'][0]['x0']
        with self.assertRaises(ReceiptRejected):
            receive(center, json.dumps(missing), package.identity)
        duplicate_field = package.package_text.replace('"version":1', '"version":1,"version":1')
        with self.assertRaises(ReceiptRejected):
            receive(center, duplicate_field, package.identity)
        self.assertEqual(center.execute('SELECT COUNT(*) FROM receipts').fetchone()[0], 0)

        first = receive(center, package.package_text, package.identity)
        changed = json.loads(package.package_text)
        changed['body']['joint_segments'][-1]['weight'] = '5/4'
        with self.assertRaisesRegex(ReceiptRejected, 'conflicts'):
            receive(center, json.dumps(changed), package.identity)
        self.assertEqual(receive(center, package.package_text, package.identity), first)
        self.assertEqual(center.execute('SELECT COUNT(*) FROM receipts').fetchone()[0], 1)

    def test_bad_revision_preserves_current(self):
        station = self.open_station()
        initial = register_sample(station, 'high-scan.json')
        store = RevisionStore(station)
        for bad_weight in ('0', '-1/4'):
            with self.subTest(weight=bad_weight):
                change = read_sample('low-scan.json')
                change['rows'][-1]['weight'] = bad_weight
                with self.assertRaisesRegex(RegistrationError, 'row 4.*positive'):
                    register(station, change['batch_id'], change['revision_id'], change['rows'])
                self.assertEqual(store.get_current(initial.key.batch_id), initial)
                self.assertIsNone(store.get_revision(RevisionKey(change['batch_id'], change['revision_id'])))
        with self.assertRaisesRegex(RegistrationError, 'already exists'):
            register(station, *initial.key.as_tuple(), read_sample('low-scan.json')['rows'])
        self.assertEqual(store.get_current(initial.key.batch_id), initial)
        self.assertEqual(station.execute('SELECT COUNT(*) FROM scan_rows').fetchone()[0], 4)
        with self.assertRaises(RevisionNotFound):
            issue(station, initial.key.batch_id, 'A')
        self.assertEqual(station.execute('SELECT COUNT(*) FROM issued_packages').fetchone()[0], 0)
        self.assertEqual(issue(station, *initial.key.as_tuple()).identity.revision_id, 'Z')

    def test_wrong_package(self):
        station = self.open_station()
        center = self.open_center()
        initial = register_sample(station, 'high-scan.json')
        amended = register_sample(station, 'low-scan.json')
        first = issue(station, *initial.key.as_tuple())
        second = issue(station, *amended.key.as_tuple())
        with self.assertRaisesRegex(ReceiptRejected, 'expected issue'):
            receive(center, second.package_text, first.identity)
        self.assertEqual(center.execute('SELECT receipt_id, confirmation FROM receipts').fetchall(), [])
        accepted = receive(center, first.package_text, first.identity)
        self.assertEqual(receive(center, first.package_text, first.identity), accepted)
        self.assertEqual(ReceiptStore(center).get_receipt(accepted.receipt_id).identity, first.identity)
