"""Night-shift two-batch mix signing demo with the station source offline."""
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from analysis.request import sign_mix
from issue.issue_store import IssueStore
from mix_inputs import receive_sample_pair
from report.readback import read_mix
from station.revision_store import RevisionStore


def _interval_text(intervals) -> list[str]:
    if not intervals:
        return []
    spans = []
    for interval in intervals:
        left = '[' if interval.lo_closed else '('
        right = ']' if interval.hi_closed else ')'
        spans.append(f'{left}{interval.lo}, {interval.hi}{right}')
    return spans


def main() -> None:
    with TemporaryDirectory(prefix='mix-changeover-') as directory:
        work = Path(directory)
        station_path = work / 'station.sqlite3'
        unavailable = work / 'station.offline.sqlite3'
        center_path = work / 'center.sqlite3'

        with closing(sqlite3.connect(center_path)) as center:
            from demo import initialize_center
            initialize_center(center)
            with closing(sqlite3.connect(station_path)) as station:
                RevisionStore(station).initialize()
                IssueStore(station).initialize()
                left, right = receive_sample_pair(station, center)
            # The station library is stopped before any mix analysis runs.
            station_path.rename(unavailable)
            signed = sign_mix(center, left.receipt_id, right.receipt_id, '0', '0', '0')
            swapped = sign_mix(center, right.receipt_id, left.receipt_id, '0', '0', '0')
            report_id = signed.report.report_id
            swapped_id = swapped.report.report_id
            print('停源后混配签发（甲=MIX-A，乙=MIX-B，目标 [0,0]）:')
            print('  报告', report_id, '| 比例集合', _interval_text(signed.report.intervals),
                  '| 首执', signed.acknowledgment.confirmation)
            print('交换甲乙后:')
            print('  报告', swapped_id, '| 比例集合', _interval_text(swapped.report.intervals),
                  '| 首执', swapped.acknowledgment.confirmation)

        with closing(sqlite3.connect(center_path)) as reopened:
            from demo import initialize_center
            initialize_center(reopened)
            saved = read_mix(reopened, report_id)
            print('重开中心后按原号领取:')
            print('  报告', saved.report.report_id, '| tick', saved.report.tick,
                  '| 目标', f'[{saved.report.lo}, {saved.report.hi}]',
                  '| 比例集合', _interval_text(saved.report.intervals))
            print('  甲乙实收号', saved.report.receipt_ids,
                  '| 首执', saved.acknowledgment.confirmation)
            for side, parent in zip(('甲', '乙'), saved.parents):
                envelope = json.loads(parent.package_text)
                print(f'  {side}出处 批 {envelope["batch_id"]} 修订 {envelope["revision_id"]}'
                      f' | 实收凭据 {parent.acknowledgment.confirmation}')

        if _interval_text(saved.report.intervals) != ['(1/2, 1]']:
            raise SystemExit('MIX_INTERVAL_MISMATCH '
                             + str(_interval_text(saved.report.intervals)))
        if _interval_text(swapped.report.intervals) != ['[0, 1/2)']:
            raise SystemExit('MIX_SWAP_MISMATCH '
                             + str(_interval_text(swapped.report.intervals)))
        if saved.parents[0].acknowledgment != left or saved.parents[1].acknowledgment != right:
            raise SystemExit('MIX_PARENT_MISMATCH')
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'MIX1',
            'input': {'samples': ['samples/mix-scans.json'], 'tick': '0', 'target': ['0', '0']},
            'expected': ['(1/2,1]', '[0,1/2)'],
            'actual': [_interval_text(signed.report.intervals)[0],
                       _interval_text(swapped.report.intervals)[0]],
            'code_paths': ['analysis/request.py', 'analysis/mixture.py',
                           'report/report_store.py', 'report/readback.py'],
            'oracle': 'Each piece is normalized by its full-piece mass; the tie at p=1/2 '
                      'resolves to the lower median response.',
        }, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
