import json
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from issue.envelope import IssueIdentity
from issue.issue_store import IssueStore
from receipt.intake import receive
from receipt.receipt_store import ReceiptStore
from report.report_store import ReportStore
from station.import_batch import register
from station.revision_store import RevisionStore


SAMPLES = Path(__file__).resolve().parents[1] / 'samples'


def read_sample(name: str) -> dict:
    return json.loads((SAMPLES / name).read_text(encoding='utf-8'))


def register_sample(station, name: str, *, batch_id: str | None = None):
    sample = read_sample(name)
    return register(station, batch_id or sample['batch_id'], sample['revision_id'], sample['rows'])


def receive_segments(center, issue_id: str, segments):
    identity = IssueIdentity(issue_id, 'fixture-batch', 'fixture-revision')
    fields = ('x0', 'x1', 'y0', 'y1', 'weight')
    text = json.dumps({
        'version': 1,
        'issue_id': issue_id,
        'batch_id': identity.batch_id,
        'revision_id': identity.revision_id,
        'body': {'joint_segments': [dict(zip(fields, map(str, row))) for row in segments]},
    })
    return receive(center, text, identity)


def report_counts(center) -> tuple[int, int]:
    return (
        center.execute('SELECT COUNT(*) FROM reports').fetchone()[0],
        center.execute('SELECT COUNT(*) FROM report_acknowledgments').fetchone()[0],
    )


def scenario(case_id, inputs, expected, actual, downstream_expected, downstream_actual,
             code_paths, oracle):
    print('POINTWISE_SCENARIO ' + json.dumps({
        'case_id': case_id,
        'input': inputs,
        'expected': expected,
        'actual': actual,
        'downstream_expected': downstream_expected,
        'downstream_actual': downstream_actual,
        'code_paths': code_paths,
        'oracle': oracle,
    }, ensure_ascii=False, sort_keys=True))


class ProjectCase(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.station_path = self.directory / 'station.sqlite3'
        self.center_path = self.directory / 'center.sqlite3'

    def open_station(self):
        connection = sqlite3.connect(self.station_path)
        self.addCleanup(connection.close)
        RevisionStore(connection).initialize()
        IssueStore(connection).initialize()
        return connection

    def open_center(self):
        connection = sqlite3.connect(self.center_path)
        self.addCleanup(connection.close)
        ReceiptStore(connection).initialize()
        ReportStore(connection).initialize()
        return connection

    def stop_station(self, connection):
        connection.close()
        return self.station_path.rename(self.directory / 'station.offline.sqlite3')
