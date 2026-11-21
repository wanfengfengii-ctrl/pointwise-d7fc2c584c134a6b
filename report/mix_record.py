from dataclasses import dataclass
from fractions import Fraction

from measurement_values import parse_rational
from receipt.receipt_store import ReceiptRecord
from report.report_record import FirstAcknowledgment


@dataclass(frozen=True)
class MixInterval:
    lo: Fraction
    hi: Fraction
    lo_closed: bool
    hi_closed: bool

    def __post_init__(self) -> None:
        lo = parse_rational(self.lo, 'mix interval lo')
        hi = parse_rational(self.hi, 'mix interval hi')
        if type(self.lo_closed) is not bool or type(self.hi_closed) is not bool:
            raise ValueError('mix interval endpoint flags must be booleans')
        if lo > hi:
            raise ValueError('mix interval lo must not exceed hi')
        if lo == hi and not (self.lo_closed and self.hi_closed):
            raise ValueError('a singleton mix interval must be closed at both ends')
        object.__setattr__(self, 'lo', lo)
        object.__setattr__(self, 'hi', hi)

    def as_text(self) -> tuple[str, str, int, int]:
        return (str(self.lo), str(self.hi), int(self.lo_closed), int(self.hi_closed))

    @classmethod
    def from_stored(cls, lo: str, hi: str, lo_closed: int, hi_closed: int) -> 'MixInterval':
        return cls(Fraction(lo), Fraction(hi), bool(lo_closed), bool(hi_closed))


@dataclass(frozen=True)
class MixReport:
    report_id: int
    receipt_ids: tuple[int, int]
    tick: Fraction
    lo: Fraction
    hi: Fraction
    intervals: tuple[MixInterval, ...]


@dataclass(frozen=True)
class MixPublication:
    report: MixReport
    acknowledgment: FirstAcknowledgment


@dataclass(frozen=True)
class MixReadback:
    report: MixReport
    acknowledgment: FirstAcknowledgment
    parents: tuple[ReceiptRecord, ReceiptRecord]
