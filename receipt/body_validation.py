from issue.package_codec import JointSegment, decode_joint_body


def validate_joint_body(body: object) -> tuple[JointSegment, ...]:
    return decode_joint_body(body)
