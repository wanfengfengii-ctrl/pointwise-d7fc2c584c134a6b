from collections import defaultdict
from fractions import Fraction

from issue.package_codec import JointSegment
from station.revisions import BatchRevision


def project_joint_measure(revision: BatchRevision) -> tuple[JointSegment, ...]:
    weights: dict[tuple[Fraction, Fraction, Fraction, Fraction], Fraction] = defaultdict(Fraction)
    for row in revision.rows:
        paired_endpoints = row.x0, row.x1, row.y0, row.y1
        weights[paired_endpoints] += row.weight
    return tuple(
        JointSegment(*endpoints, weight)
        for endpoints, weight in sorted(weights.items())
    )
