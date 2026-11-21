from dataclasses import dataclass
from fractions import Fraction

from analysis.result import ReviewOutcome
from measurement_values import parse_rational


@dataclass(frozen=True)
class ReportRecord:
    report_id: int
    receipt_id: int
    tick: Fraction
    outcome: ReviewOutcome


@dataclass(frozen=True)
class FirstAcknowledgment:
    report_id: int
    confirmation: str


@dataclass(frozen=True)
class ReviewPublication:
    report: ReportRecord
    acknowledgment: FirstAcknowledgment


def encode_report_result(outcome: ReviewOutcome) -> tuple[str, str | None]:
    if outcome.value is None:
        return outcome.status, None
    return outcome.status, str(outcome.value)


def decode_report_result(status: str, value: str | None) -> ReviewOutcome:
    if status == 'numeric':
        return ReviewOutcome.numeric(parse_rational(value, 'stored replacement reading'))
    if status == 'no_evidence' and value is None:
        return ReviewOutcome.no_evidence()
    raise ValueError('invalid stored report result')
