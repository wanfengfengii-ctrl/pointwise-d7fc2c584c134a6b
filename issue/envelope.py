import json
from dataclasses import dataclass

from measurement_values import require_fields, require_identifier


@dataclass(frozen=True)
class IssueIdentity:
    issue_id: str
    batch_id: str
    revision_id: str

    def __post_init__(self) -> None:
        require_identifier(self.issue_id, 'issue id')
        require_identifier(self.batch_id, 'batch id')
        require_identifier(self.revision_id, 'revision id')


@dataclass(frozen=True)
class PackageEnvelope:
    identity: IssueIdentity
    body: dict


def encode_envelope(envelope: PackageEnvelope) -> str:
    identity = envelope.identity
    return json.dumps({
        'version': 1,
        'issue_id': identity.issue_id,
        'batch_id': identity.batch_id,
        'revision_id': identity.revision_id,
        'body': envelope.body,
    }, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _unique_fields(pairs: list[tuple[str, object]]) -> dict:
    fields = {}
    for key, value in pairs:
        if key in fields:
            raise ValueError(f'duplicate JSON field: {key}')
        fields[key] = value
    return fields


def _reject_json_constant(value: str) -> None:
    raise ValueError(f'invalid JSON constant: {value}')


def decode_envelope(package_text: object) -> PackageEnvelope:
    if not isinstance(package_text, str):
        raise ValueError('a V1 package must be JSON text')
    try:
        package_text.encode('utf-8')
        raw = json.loads(package_text, object_pairs_hook=_unique_fields,
                         parse_constant=_reject_json_constant)
    except (ValueError, RecursionError) as exc:
        raise ValueError(f'invalid package JSON: {exc}') from exc
    fields = require_fields(raw, {'version', 'issue_id', 'batch_id', 'revision_id', 'body'},
                            'package envelope')
    if type(fields['version']) is not int or fields['version'] != 1:
        raise ValueError('unsupported package version')
    if not isinstance(fields['body'], dict):
        raise ValueError('package body must be an object')
    identity = IssueIdentity(fields['issue_id'], fields['batch_id'], fields['revision_id'])
    return PackageEnvelope(identity, fields['body'])
