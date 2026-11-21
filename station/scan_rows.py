from dataclasses import dataclass
from fractions import Fraction

from measurement_values import parse_rational, require_fields, require_identifier


@dataclass(frozen=True)
class ScanRow:
    x0: Fraction
    x1: Fraction
    y0: Fraction
    y1: Fraction
    weight: Fraction
    source_record: str
    scan_start: Fraction
    scan_end: Fraction


def parse_scan_row(raw: object) -> ScanRow:
    row = require_fields(raw, {'x0', 'x1', 'y0', 'y1', 'weight', 'source'}, 'scan row')
    source = require_fields(row['source'], {'record', 'scan_start', 'scan_end'}, 'source')
    weight = parse_rational(row['weight'], 'weight')
    if weight <= 0:
        raise ValueError('weight must be positive')
    return ScanRow(
        x0=parse_rational(row['x0'], 'x0'),
        x1=parse_rational(row['x1'], 'x1'),
        y0=parse_rational(row['y0'], 'y0'),
        y1=parse_rational(row['y1'], 'y1'),
        weight=weight,
        source_record=require_identifier(source['record'], 'source record'),
        scan_start=parse_rational(source['scan_start'], 'scan_start'),
        scan_end=parse_rational(source['scan_end'], 'scan_end'),
    )
