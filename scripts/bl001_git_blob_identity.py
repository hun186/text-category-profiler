"""BL-001 Git blob identity helpers shared by legacy manifests and audits.

Only already-reviewed manifest entries may use CRLF checkout normalization.
The authority is a Git blob digest and byte length, not a worktree spelling.
Nothing is written back to disk.
"""
import hashlib


def git_blob_sha(data):
    return hashlib.sha1(
        ("blob %d" % len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def legacy_git_blob_bytes(content, expected_sha, expected_size):
    """Preserve exact blob identity through Git's Windows CRLF checkout.

    Accept raw bytes first, then CRLF->LF solely when the resulting bytes
    match BOTH a known manifest SHA and expected byte count. Any other
    difference remains unmodified and must fail the caller's identity gate.
    """
    if git_blob_sha(content) == expected_sha and len(content) == expected_size:
        return content
    normalized = content.replace(b"\r\n", b"\n")
    if (normalized != content and git_blob_sha(normalized) == expected_sha
            and len(normalized) == expected_size):
        return normalized
    return content
