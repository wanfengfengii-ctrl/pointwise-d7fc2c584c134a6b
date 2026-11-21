from collections.abc import Iterable
from fractions import Fraction

from analysis.response_sweep import build_response_knots, first_half_crossing
from analysis.result import ReviewOutcome
from analysis.window_mass import NearZeroAffine, clip_near_zero, total_window_mass
from issue.package_codec import JointSegment


def compute_median_limit(segments: Iterable[JointSegment], tick: Fraction) -> ReviewOutcome:
    slices = []
    for segment in segments:
        part = clip_near_zero(segment, tick)
        if part is not None:
            slices.append(part)

    total = total_window_mass(slices)
    if total == NearZeroAffine():
        return ReviewOutcome.no_evidence()
    half = total.scale(Fraction(1, 2))
    crossing = first_half_crossing(build_response_knots(slices), half)
    return ReviewOutcome.numeric(crossing.intercept)
