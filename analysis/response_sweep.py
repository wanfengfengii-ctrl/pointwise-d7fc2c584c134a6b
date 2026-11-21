from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction

from analysis.window_mass import NearZeroAffine, WindowSlice


@dataclass(frozen=True)
class ResponseKnot:
    position: NearZeroAffine
    density_change: Fraction
    atom_mass: NearZeroAffine


def build_response_knots(slices: Iterable[WindowSlice]) -> tuple[ResponseKnot, ...]:
    density_events = defaultdict(Fraction)
    atom_events = defaultdict(NearZeroAffine)
    for part in slices:
        if part.response_lo == part.response_hi:
            atom_events[part.response_lo] += part.mass
        else:
            density_events[part.response_lo] += part.density
            density_events[part.response_hi] -= part.density
    positions = sorted(density_events.keys() | atom_events.keys())
    return tuple(
        ResponseKnot(position, density_events.get(position, Fraction(0)),
                     atom_events.get(position, NearZeroAffine()))
        for position in positions
    )


def first_half_crossing(
    knots: Iterable[ResponseKnot], half_mass: NearZeroAffine
) -> NearZeroAffine:
    accumulated = NearZeroAffine()
    density = Fraction(0)
    previous = None
    for knot in knots:
        position = knot.position
        if previous is not None and density:
            at_left_limit = accumulated + (position - previous).scale(density)
            if at_left_limit >= half_mass:
                return previous + (half_mass - accumulated).scale(1 / density)
            accumulated = at_left_limit
        accumulated += knot.atom_mass
        if accumulated >= half_mass:
            return position
        density += knot.density_change
        previous = position
    raise ArithmeticError('positive window mass never reached its half threshold')
