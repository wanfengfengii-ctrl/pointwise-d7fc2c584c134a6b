from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from measurement_values import parse_rational


@dataclass(frozen=True)
class ReviewOutcome:
    status: str
    value: Fraction | None

    def __post_init__(self) -> None:
        if self.status == 'numeric' and isinstance(self.value, Fraction):
            return
        if self.status == 'no_evidence' and self.value is None:
            return
        raise ValueError('invalid review outcome state')

    @classmethod
    def numeric(cls, value: Fraction) -> ReviewOutcome:
        return cls('numeric', parse_rational(value, 'replacement reading'))

    @classmethod
    def no_evidence(cls) -> ReviewOutcome:
        return cls('no_evidence', None)
