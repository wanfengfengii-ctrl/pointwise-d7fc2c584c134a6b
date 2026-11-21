import json
import sqlite3
from contextlib import closing
from fractions import Fraction
from pathlib import Path

from analysis.request import review
from demo import initialize_center
from issue.issue import issue
from issue.issue_store import IssueStore
from receipt.intake import receive
from receipt.receipt_store import IntakeAcknowledgment
from report.readback import read
from station.import_batch import register
from station.revision_store import RevisionStore


SAMPLE = Path(__file__).resolve().parent / "samples" / "mix-scans.json"


def receive_sample_pair(
    station: sqlite3.Connection, center: sqlite3.Connection
) -> tuple[IntakeAcknowledgment, IntakeAcknowledgment]:
    acknowledgments = []
    for batch in json.loads(SAMPLE.read_text(encoding="utf-8")):
        revision = register(station, batch["batch_id"], batch["revision_id"], batch["rows"])
        package = issue(station, *revision.key.as_tuple())
        acknowledgments.append(receive(center, package.package_text, package.identity))
    left, right = acknowledgments
    return left, right


def main() -> None:
    with closing(sqlite3.connect(":memory:")) as center:
        initialize_center(center)
        with closing(sqlite3.connect(":memory:")) as station:
            RevisionStore(station).initialize()
            IssueStore(station).initialize()
            left, right = receive_sample_pair(station, center)
        for side, receipt, expected in (("甲", left, 0), ("乙", right, 2)):
            signed = review(center, receipt.receipt_id, 0)
            saved = read(center, signed.report.report_id)
            outcome = saved.report.outcome
            if (outcome.value != Fraction(expected) or saved.report != signed.report
                    or saved.acknowledgment != signed.acknowledgment
                    or saved.parent.acknowledgment != receipt):
                raise RuntimeError(f"{side}批的 V1 样例基准或出处不符")
            print(f"{side} {saved.parent.identity.batch_id} | 实收 {receipt.receipt_id}"
                  f" | 单件基准 {outcome.value} | 首执 {saved.acknowledgment.confirmation}")


if __name__ == "__main__":
    main()
