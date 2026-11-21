from issue.envelope import IssueIdentity


def require_expected_identity(actual: IssueIdentity, expected: IssueIdentity) -> None:
    if not isinstance(expected, IssueIdentity) or actual != expected:
        raise ValueError('package does not match the expected issue, batch and revision')


def receipt_source_key(identity: IssueIdentity) -> str:
    return identity.issue_id


def same_frozen_package(stored: str, delivered: str) -> bool:
    return stored == delivered
