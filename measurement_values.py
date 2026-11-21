from collections.abc import Mapping
from fractions import Fraction


def parse_rational(value: object, label: str) -> Fraction:
    if isinstance(value, Fraction):
        return value
    if type(value) is int:
        return Fraction(value)
    if isinstance(value, str):
        try:
            return Fraction(value)
        except (ValueError, ZeroDivisionError) as exc:
            raise ValueError(f'{label} must be an exact rational') from exc
    raise ValueError(f'{label} must be an exact rational')


def require_identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.isprintable() or value != value.strip():
        raise ValueError(f'{label} must be nonempty printable text without outer spaces')
    return value


def require_fields(value: object, fields: set[str], label: str) -> Mapping:
    if not isinstance(value, Mapping) or value.keys() != fields:
        raise ValueError(f'{label} must have exactly these fields: {", ".join(sorted(fields))}')
    return value


def is_record_number(value: object) -> bool:
    return type(value) is int and 0 < value < 2**63
