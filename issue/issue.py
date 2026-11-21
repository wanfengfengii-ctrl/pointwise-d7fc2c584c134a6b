import hashlib
import json
import sqlite3

from issue.envelope import IssueIdentity, PackageEnvelope, encode_envelope
from issue.issue_store import IssueStore, IssuedPackage
from issue.package_codec import encode_joint_body
from issue.paired_measure import project_joint_measure
from station.revision_store import RevisionStore
from station.revisions import RevisionKey


class RevisionNotFound(LookupError):
    """The requested frozen revision does not exist."""


def issue(station: sqlite3.Connection, batch_id: str, revision_id: str) -> IssuedPackage:
    key = RevisionKey(batch_id, revision_id)
    revision = RevisionStore(station).get_revision(key)
    if revision is None:
        raise RevisionNotFound(f'unknown revision: {batch_id}/{revision_id}')
    encoded_key = json.dumps(key.as_tuple(), ensure_ascii=True, separators=(',', ':')).encode('ascii')
    issue_id = 'issue-' + hashlib.sha256(encoded_key).hexdigest()
    archive = IssueStore(station)
    existing = archive.get_issued(issue_id)
    if existing is not None:
        return existing
    identity = IssueIdentity(issue_id, batch_id, revision_id)
    body = encode_joint_body(project_joint_measure(revision))
    package_text = encode_envelope(PackageEnvelope(identity, body))
    return archive.save_issued(IssuedPackage(identity, package_text))
