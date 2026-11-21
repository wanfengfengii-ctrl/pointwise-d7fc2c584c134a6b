from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction

from issue.package_codec import JointSegment


@dataclass(frozen=True, order=True)
class NearZeroAffine:
    """An exact value a + b*epsilon ordered for sufficiently small epsilon > 0."""

    intercept: Fraction = Fraction(0)
    slope: Fraction = Fraction(0)

    def __add__(self, other: NearZeroAffine) -> NearZeroAffine:
        return NearZeroAffine(self.intercept + other.intercept, self.slope + other.slope)

    def __sub__(self, other: NearZeroAffine) -> NearZeroAffine:
        return NearZeroAffine(self.intercept - other.intercept, self.slope - other.slope)

    def scale(self, factor: Fraction) -> NearZeroAffine:
        return NearZeroAffine(self.intercept * factor, self.slope * factor)


@dataclass(frozen=True)
class WindowSlice:
    response_lo: NearZeroAffine
    response_hi: NearZeroAffine
    mass: NearZeroAffine
    density: Fraction


_ZERO = NearZeroAffine()
_ONE = NearZeroAffine(Fraction(1))


def clip_near_zero(segment: JointSegment, tick: Fraction) -> WindowSlice | None:
    slope_x = segment.x1 - segment.x0
    if slope_x == 0:
        if segment.x0 != tick:
            return None
        start, end = _ZERO, _ONE
    else:
        center = (tick - segment.x0) / slope_x
        offset = 1 / slope_x
        from_lower_x = NearZeroAffine(center, -offset)
        from_upper_x = NearZeroAffine(center, offset)
        start = max(_ZERO, min(from_lower_x, from_upper_x))
        end = min(_ONE, max(from_lower_x, from_upper_x))
        if end <= start:
            return None

    mass = (end - start).scale(segment.weight)
    slope_y = segment.y1 - segment.y0
    origin = NearZeroAffine(segment.y0)
    first = origin + start.scale(slope_y)
    last = origin + end.scale(slope_y)
    density = segment.weight / abs(slope_y) if slope_y else Fraction(0)
    return WindowSlice(min(first, last), max(first, last), mass, density)


def total_window_mass(slices: Iterable[WindowSlice]) -> NearZeroAffine:
    return sum((part.mass for part in slices), _ZERO)
