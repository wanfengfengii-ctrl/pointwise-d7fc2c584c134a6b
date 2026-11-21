from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction

from measurement_values import parse_rational, require_fields


_FIELDS = ('x0', 'x1', 'y0', 'y1', 'weight')


@dataclass(frozen=True)
class JointSegment:
    x0: Fraction
    x1: Fraction
    y0: Fraction
    y1: Fraction
    weight: Fraction

    def __post_init__(self) -> None:
        for field in _FIELDS:
            value = parse_rational(getattr(self, field), field)
            object.__setattr__(self, field, value)
        if self.weight <= 0:
            raise ValueError('joint segment weight must be positive')


def encode_joint_body(segments: Iterable[JointSegment]) -> dict:
    rows = [{field: str(getattr(segment, field)) for field in _FIELDS} for segment in segments]
    if not rows:
        raise ValueError('joint body must contain at least one segment')
    return {'joint_segments': rows}


def decode_joint_body(body: object) -> tuple[JointSegment, ...]:
    record = require_fields(body, {'joint_segments'}, 'joint body')
    rows = record['joint_segments']
    if not isinstance(rows, list) or not rows:
        raise ValueError('joint_segments must be a nonempty list')
    decoded = []
    for index, row in enumerate(rows, start=1):
        try:
            fields = require_fields(row, set(_FIELDS), 'joint segment')
            decoded.append(JointSegment(**fields))
        except ValueError as exc:
            raise ValueError(f'joint segment {index}: {exc}') from exc
    return tuple(decoded)
