"""Single verification entry: original unittest regression plus mix business checks."""
import sys
import unittest

from check_project import main as run_regression


def _run_mix_business_checks() -> None:
    import sqlite3
    from contextlib import closing
    from fractions import Fraction

    from analysis.request import sign_mix
    from issue.issue_store import IssueStore
    from mix_inputs import receive_sample_pair
    from report.readback import read_mix
    from station.revision_store import RevisionStore

    with closing(sqlite3.connect(':memory:')) as center:
        from demo import initialize_center
        initialize_center(center)
        with closing(sqlite3.connect(':memory:')) as station:
            RevisionStore(station).initialize()
            IssueStore(station).initialize()
            left, right = receive_sample_pair(station, center)
        signed = sign_mix(center, left.receipt_id, right.receipt_id, '0', '0', '0')
        intervals = signed.report.intervals
        if len(intervals) != 1 or intervals[0].lo != Fraction(1, 2) \
                or intervals[0].hi != Fraction(1) or intervals[0].lo_closed \
                or not intervals[0].hi_closed:
            raise SystemExit('MIX_BUSINESS_CHECK_FAILED ' + str(intervals))
        swapped = sign_mix(center, right.receipt_id, left.receipt_id, '0', '0', '0')
        swapped_interval = swapped.report.intervals[0]
        if (swapped_interval.lo != Fraction(0) or swapped_interval.hi != Fraction(1, 2)
                or not swapped_interval.lo_closed or swapped_interval.hi_closed):
            raise SystemExit('MIX_SWAP_CHECK_FAILED ' + str(swapped.report.intervals))
        readback = read_mix(center, signed.report.report_id)
        if readback.report != signed.report or readback.acknowledgment != signed.acknowledgment:
            raise SystemExit('MIX_READBACK_CHECK_FAILED')
        if [parent.receipt_id for parent in readback.parents] != [left.receipt_id,
                                                                  right.receipt_id]:
            raise SystemExit('MIX_PARENT_ORDER_CHECK_FAILED')


def main() -> int:
    _run_mix_business_checks()
    print('MIX_BUSINESS_CHECKS PASS')
    return run_regression()


if __name__ == '__main__':
    raise SystemExit(main())
