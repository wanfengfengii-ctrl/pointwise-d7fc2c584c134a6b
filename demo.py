import json
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from analysis.request import review
from issue.issue import issue
from issue.issue_store import IssueStore
from receipt.intake import receive
from receipt.receipt_store import ReceiptStore
from report.readback import read
from report.report_store import ReportStore
from station.import_batch import register
from station.revision_store import RevisionStore


SAMPLES = Path(__file__).resolve().parent / 'samples'


def prepare_package(station_path: Path, filename: str):
    sample = json.loads((SAMPLES / filename).read_text(encoding='utf-8'))
    with closing(sqlite3.connect(station_path)) as station:
        RevisionStore(station).initialize()
        IssueStore(station).initialize()
        revision = register(station, sample['batch_id'], sample['revision_id'], sample['rows'])
        return issue(station, *revision.key.as_tuple())


def initialize_center(center: sqlite3.Connection) -> None:
    ReceiptStore(center).initialize()
    ReportStore(center).initialize()


def main() -> None:
    with TemporaryDirectory(prefix='changeover-') as directory:
        work = Path(directory)
        station_path = work / 'station.sqlite3'
        unavailable = work / 'station.offline.sqlite3'
        center_path = work / 'center.sqlite3'
        records = []
        with closing(sqlite3.connect(center_path)) as center:
            initialize_center(center)
            for filename in ('high-scan.json', 'low-scan.json'):
                package = prepare_package(station_path, filename)
                intake = receive(center, package.package_text, package.identity)
                station_path.rename(unavailable)
                try:
                    signed = review(center, intake.receipt_id, '0')
                finally:
                    unavailable.rename(station_path)
                records.append((package, intake, signed))
            station_path.rename(unavailable)

        with closing(sqlite3.connect(center_path)) as reopened:
            initialize_center(reopened)
            saved_values = []
            saved_revisions = []
            for package, intake, signed in records:
                saved = read(reopened, signed.report.report_id)
                if (saved.report != signed.report or saved.acknowledgment != signed.acknowledgment
                        or saved.parent.package_text != package.package_text
                        or saved.parent.identity != package.identity
                        or saved.parent.acknowledgment != intake):
                    raise RuntimeError('reopened report does not match its original handoff')
                value = str(saved.report.outcome.value)
                revision = saved.parent.identity.revision_id
                saved_values.append(value)
                saved_revisions.append(revision)
                print(f'报告 {saved.report.report_id} | 修订 {revision} | 实收 {saved.parent.receipt_id}'
                      f' | 复测基准 {value} | 首执 {saved.acknowledgment.confirmation}')

        if saved_values != ['2', '0'] or saved_revisions != ['Z', 'A']:
            raise SystemExit(f'MEDIAN_LIMIT_MISMATCH values={saved_values} revisions={saved_revisions}')
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'V8',
            'input': {'samples': ['samples/high-scan.json', 'samples/low-scan.json'], 'tick': '0'},
            'expected': ['2', '0'],
            'actual': saved_values,
            'downstream_expected': ['Z', 'A'],
            'downstream_actual': saved_revisions,
            'code_paths': ['station/import_batch.py', 'issue/issue.py', 'receipt/intake.py',
                           'analysis/request.py', 'report/report_store.py', 'report/readback.py'],
            'oracle': 'In the positive window, the extra epsilon/4 mass shifts the first half crossing to 2 or 0.',
        }, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
