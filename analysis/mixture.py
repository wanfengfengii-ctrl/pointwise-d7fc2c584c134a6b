"""Exact two-batch mixture signing over the V1 near-zero median limit.

Each V1 package is first normalized by its own full-piece total mass. The
ordered mixture assigns factor ``p`` to the left (first/甲) package and
``1 - p`` to the right (second/乙) package. For every rational ``p`` in
``[0, 1]`` the V1 closed-window lower median and its right limit as the
tolerance tends to zero are reused unchanged.

All arithmetic is exact :class:`~fractions.Fraction` arithmetic. The median
limit is a fractional-linear function of ``p`` on finitely many open cells.
Every comparison that can change inside ``[0, 1]`` contributes its rational
roots, so the qualified proportions always form finite unions of intervals
with rational endpoints and exact open/closed flags.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from analysis.response_sweep import build_response_knots, first_half_crossing
from analysis.window_mass import NearZeroAffine, WindowSlice, clip_near_zero, total_window_mass
from issue.package_codec import JointSegment

_ZERO = Fraction(0)
_ONE = Fraction(1)
_HALF = Fraction(1, 2)


@dataclass(frozen=True)
class Lin:
    """An exact linear form ``a * p + b`` kept symbolic over the mix ratio."""

    a: Fraction
    b: Fraction

    def __add__(self, other: Lin) -> Lin:
        return Lin(self.a + other.a, self.b + other.b)

    def __sub__(self, other: Lin) -> Lin:
        return Lin(self.a - other.a, self.b - other.b)

    def scale(self, factor: Fraction) -> Lin:
        return Lin(self.a * factor, self.b * factor)

    def __call__(self, p: Fraction) -> Fraction:
        return self.a * p + self.b


LIN_ZERO = Lin(_ZERO, _ZERO)


@dataclass(frozen=True)
class SymbolicKnot:
    position: NearZeroAffine
    density_change: Lin
    atom_intercept: Lin
    atom_slope: Lin


def normalized_base_slices(
    segments: tuple[JointSegment, ...], tick: Fraction
) -> tuple[WindowSlice, ...]:
    """Clip a package around ``tick`` and normalize by the full-piece mass."""
    piece_mass = sum((segment.weight for segment in segments), _ZERO)
    inverse = _ONE / piece_mass
    slices = []
    for segment in segments:
        part = clip_near_zero(segment, tick)
        if part is None:
            continue
        slices.append(WindowSlice(
            part.response_lo,
            part.response_hi,
            part.mass.scale(inverse),
            part.density * inverse,
        ))
    return tuple(slices)


def _factor_lin(is_left: bool) -> Lin:
    # Left (甲) carries p; right (乙) carries 1 - p.
    return Lin(_ONE, _ZERO) if is_left else Lin(-_ONE, _ONE)


def _scaled_slices(slices: tuple[WindowSlice, ...], factor: Fraction) -> list[WindowSlice]:
    if factor == 0:
        return []
    return [
        WindowSlice(
            part.response_lo,
            part.response_hi,
            part.mass.scale(factor),
            part.density * factor,
        )
        for part in slices
    ]


def evaluate_limit(
    left_slices: tuple[WindowSlice, ...],
    right_slices: tuple[WindowSlice, ...],
    p: Fraction,
) -> Fraction | None:
    """Concrete median limit at one rational ratio. ``None`` means no evidence."""
    slices = _scaled_slices(left_slices, p) + _scaled_slices(right_slices, _ONE - p)
    total = total_window_mass(slices)
    if total == NearZeroAffine():
        return None
    half = total.scale(_HALF)
    crossing = first_half_crossing(build_response_knots(slices), half)
    return crossing.intercept


def _build_symbolic_knots(
    left_slices: tuple[WindowSlice, ...],
    right_slices: tuple[WindowSlice, ...],
) -> tuple[tuple[SymbolicKnot, ...], Lin, Lin]:
    density_events: dict[NearZeroAffine, Lin] = {}
    atom_intercepts: dict[NearZeroAffine, Lin] = {}
    atom_slopes: dict[NearZeroAffine, Lin] = {}
    total_intercept = LIN_ZERO
    total_slope = LIN_ZERO

    def add(store: dict[NearZeroAffine, Lin], key: NearZeroAffine, value: Lin) -> None:
        store[key] = store.get(key, LIN_ZERO) + value

    for is_left, slices in ((True, left_slices), (False, right_slices)):
        factor = _factor_lin(is_left)
        for part in slices:
            mass_intercept = factor.scale(part.mass.intercept)
            mass_slope = factor.scale(part.mass.slope)
            total_intercept += mass_intercept
            total_slope += mass_slope
            if part.response_lo == part.response_hi:
                add(atom_intercepts, part.response_lo, mass_intercept)
                add(atom_slopes, part.response_lo, mass_slope)
            else:
                density = factor.scale(part.density)
                add(density_events, part.response_lo, density)
                add(density_events, part.response_hi, density.scale(-_ONE))

    positions = sorted(set(density_events) | set(atom_intercepts))
    knots = tuple(
        SymbolicKnot(
            position,
            density_events.get(position, LIN_ZERO),
            atom_intercepts.get(position, LIN_ZERO),
            atom_slopes.get(position, LIN_ZERO),
        )
        for position in positions
    )
    return knots, total_intercept, total_slope


def _root_in_open(value: Fraction, low: Fraction, high: Fraction) -> Fraction | None:
    if low < value < high:
        return value
    return None


def _lin_root(form: Lin, low: Fraction, high: Fraction) -> Fraction | None:
    if form.a == 0:
        return None
    return _root_in_open(-form.b / form.a, low, high)


def _tied_slope_root(
    intercept_form: Lin, slope_form: Lin, low: Fraction, high: Fraction
) -> Fraction | None:
    """Root of a slope comparison when the intercepts agree identically.

    A :class:`NearZeroAffine` ordering first compares intercepts. When the
    intercept difference is a nonzero (possibly constant) form, the slope can
    never change the order, so its roots are spurious. When the intercepts tie
    identically, the slope decides the order for every ratio and its root is a
    genuine branch breakpoint.
    """
    if intercept_form != LIN_ZERO:
        return None
    return _lin_root(slope_form, low, high)


def _sweep_breakpoints(
    knots: tuple[SymbolicKnot, ...],
    total_intercept: Lin,
    total_slope: Lin,
) -> set[Fraction]:
    """Roots of every comparison the concrete sweep can make on (0, 1)."""
    roots: set[Fraction] = set()
    half_intercept = total_intercept.scale(_HALF)
    half_slope = total_slope.scale(_HALF)
    accumulated = LIN_ZERO
    accumulated_slope = LIN_ZERO
    density = LIN_ZERO
    previous: NearZeroAffine | None = None

    for knot in knots:
        position = knot.position
        if previous is not None and (density.a != 0 or density.b != 0):
            delta = position - previous
            at_left = accumulated + density.scale(delta.intercept)
            at_left_slope = accumulated_slope + density.scale(delta.slope)
            intercept_form = at_left - half_intercept
            slope_form = at_left_slope - half_slope
            root = _lin_root(intercept_form, _ZERO, _ONE)
            if root is not None:
                roots.add(root)
            root = _tied_slope_root(intercept_form, slope_form, _ZERO, _ONE)
            if root is not None:
                roots.add(root)
            # A positive effective density only vanishes at p = 0 or p = 1,
            # never inside (0, 1), so it contributes no interior root.
            accumulated = at_left
            accumulated_slope = at_left_slope
        accumulated += knot.atom_intercept
        accumulated_slope += knot.atom_slope
        intercept_form = accumulated - half_intercept
        slope_form = accumulated_slope - half_slope
        root = _lin_root(intercept_form, _ZERO, _ONE)
        if root is not None:
            roots.add(root)
        root = _tied_slope_root(intercept_form, slope_form, _ZERO, _ONE)
        if root is not None:
            roots.add(root)
        density += knot.density_change
        previous = position
    return roots


def _concrete_ge(
    left_intercept: Lin,
    left_slope: Lin,
    right_intercept: Lin,
    right_slope: Lin,
    ref_p: Fraction,
) -> bool:
    left = NearZeroAffine(left_intercept(ref_p), left_slope(ref_p))
    right = NearZeroAffine(right_intercept(ref_p), right_slope(ref_p))
    return left >= right


def _symbolic_crossing(
    knots: tuple[SymbolicKnot, ...],
    total_intercept: Lin,
    total_slope: Lin,
    ref_p: Fraction,
) -> tuple[str, object]:
    """Replay the fixed branch path inside one open cell.

    Returns ``('atom', intercept_fraction)`` for a point-mass crossing or
    ``('continuous', previous_intercept, acc_i, acc_s, density, half_i,
    half_s)`` for a crossing inside a positive-density response interval. Both
    the constant (epsilon^0) and slope (epsilon^1) mass forms are retained,
    because the median intercept can depend on either order of the window mass.
    """
    half_intercept = total_intercept.scale(_HALF)
    half_slope = total_slope.scale(_HALF)
    accumulated = LIN_ZERO
    accumulated_slope = LIN_ZERO
    density = LIN_ZERO
    previous: NearZeroAffine | None = None

    for knot in knots:
        position = knot.position
        if previous is not None and (density.a != 0 or density.b != 0):
            delta = position - previous
            at_left = accumulated + density.scale(delta.intercept)
            at_left_slope = accumulated_slope + density.scale(delta.slope)
            if _concrete_ge(at_left, at_left_slope, half_intercept, half_slope, ref_p):
                return ('continuous', previous.intercept, accumulated, accumulated_slope,
                        density, half_intercept, half_slope)
            accumulated = at_left
            accumulated_slope = at_left_slope
        accumulated += knot.atom_intercept
        accumulated_slope += knot.atom_slope
        if _concrete_ge(accumulated, accumulated_slope, half_intercept, half_slope, ref_p):
            return ('atom', position.intercept)
        density += knot.density_change
        previous = position
    raise ArithmeticError('positive mixture mass never reached its half threshold')


@dataclass(frozen=True)
class TargetCell:
    """Interior target-bound roots of one open ratio cell."""

    roots: frozenset[Fraction]


def _target_roots(
    crossing: tuple[str, object], low: Fraction, high: Fraction, cell_low: Fraction,
    cell_high: Fraction,
) -> TargetCell:
    kind = crossing[0]
    if kind == 'atom':
        # An atom crossing pins the median to one fixed response value, so it
        # cannot cross a target bound inside the open cell.
        return TargetCell(frozenset())
    (_, previous_intercept, accumulated, accumulated_slope, density,
     half_intercept, half_slope) = crossing
    roots: set[Fraction] = set()
    # The median intercept is previous_intercept plus the ratio by which the
    # continuous response interval reaches its half threshold. The threshold
    # lives on either the intercept (epsilon^0) or the slope (epsilon^1) order
    # depending on the branch, and both can move the median across a target
    # bound at an interior rational ratio, so both orders contribute target
    # roots. density(p) > 0 throughout the open cell makes cross
    # multiplication safe; identically zero equations hold on the whole cell
    # and are classified by the midpoint, contributing no split.
    forms = (
        density.scale(low - previous_intercept) - half_intercept + accumulated,
        density.scale(high - previous_intercept) - half_intercept + accumulated,
        density.scale(low - previous_intercept) - half_slope + accumulated_slope,
        density.scale(high - previous_intercept) - half_slope + accumulated_slope,
    )
    for form in forms:
        if form.a == 0:
            continue
        value = -form.b / form.a
        if cell_low < value < cell_high:
            roots.add(value)
    return TargetCell(frozenset(roots))


@dataclass(frozen=True)
class RatioComponent:
    """An elementary piece of [0, 1]: a critical point or an open gap."""

    kind: str  # 'point' or 'gap'
    qualified: bool
    evidenced: bool
    lo: Fraction
    hi: Fraction


def build_decomposition(
    left_segments: tuple[JointSegment, ...],
    right_segments: tuple[JointSegment, ...],
    tick: Fraction,
    low: Fraction,
    high: Fraction,
) -> tuple[RatioComponent, ...]:
    """Split [0, 1] into rational critical points alternating with open gaps.

    Sweep breakpoints partition the ratio line into cells with one fixed
    median branch. Target-bound roots are computed per cell against that
    cell's own crossing branch; adding a root splits the cell, so the pass is
    repeated until no new roots appear. On each final open cell the median is
    either wholly qualified, wholly unqualified, or separated by a collected
    root, so a midpoint evaluation classifies the whole gap.
    """
    left_slices = normalized_base_slices(left_segments, tick)
    right_slices = normalized_base_slices(right_segments, tick)

    knots, total_intercept, total_slope = _build_symbolic_knots(left_slices, right_slices)
    breakpoints = _sweep_breakpoints(knots, total_intercept, total_slope)
    critical = sorted(breakpoints | {_ZERO, _ONE})

    while True:
        extra_roots: set[Fraction] = set()
        for cell_low, cell_high in zip(critical, critical[1:]):
            ref_p = (cell_low + cell_high) * _HALF
            if evaluate_limit(left_slices, right_slices, ref_p) is None:
                continue
            crossing = _symbolic_crossing(knots, total_intercept, total_slope, ref_p)
            extra_roots |= set(_target_roots(crossing, low, high, cell_low, cell_high).roots)
        refined = sorted(set(critical) | extra_roots)
        if refined == critical:
            break
        critical = refined

    components: list[RatioComponent] = []
    for index, point in enumerate(critical):
        value = evaluate_limit(left_slices, right_slices, point)
        components.append(RatioComponent(
            'point', value is not None and low <= value <= high,
            value is not None, point, point,
        ))
        if index + 1 < len(critical):
            next_point = critical[index + 1]
            midpoint = (point + next_point) * _HALF
            gap_value = evaluate_limit(left_slices, right_slices, midpoint)
            components.append(RatioComponent(
                'gap', gap_value is not None and low <= gap_value <= high,
                gap_value is not None, point, next_point,
            ))
    return tuple(components)


@dataclass(frozen=True)
class SignedInterval:
    lo: Fraction
    hi: Fraction
    lo_closed: bool
    hi_closed: bool


def merge_components(components: tuple[RatioComponent, ...]) -> tuple[SignedInterval, ...]:
    """Merge adjacent qualified components into maximal ascending intervals."""
    intervals: list[SignedInterval] = []
    current: SignedInterval | None = None

    def open_interval(component: RatioComponent) -> SignedInterval:
        if component.kind == 'point':
            return SignedInterval(component.lo, component.hi, True, True)
        return SignedInterval(component.lo, component.hi, False, False)

    for component in components:
        if not component.qualified:
            if current is not None:
                intervals.append(current)
                current = None
            continue
        if current is None:
            current = open_interval(component)
            continue
        if component.kind == 'point' and component.lo == current.hi:
            current = SignedInterval(current.lo, component.hi, current.lo_closed, True)
        elif component.kind == 'gap' and component.lo == current.hi:
            # The shared point was already qualified, so the closed flag carries.
            current = SignedInterval(current.lo, component.hi, current.lo_closed, False)
        else:  # defensive: components are known to alternate and touch
            intervals.append(current)
            current = open_interval(component)
    if current is not None:
        intervals.append(current)
    return tuple(intervals)
