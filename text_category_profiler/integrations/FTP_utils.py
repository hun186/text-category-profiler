"""Deprecated compatibility surface for removed FTP/SFTP sample helpers.

The historical module mixed incomplete examples, embedded connection details,
and network operations at import time.  Network transfer behavior is not part
of the supported package integrations.
"""


class UnsupportedFTPIntegrationError(RuntimeError):
    """Raised when a removed legacy FTP/SFTP helper is called."""


def _unsupported(*args, **kwargs):
    del args, kwargs
    raise UnsupportedFTPIntegrationError(
        "The legacy FTP/SFTP sample integration is deprecated and unsupported."
    )


def sftp_put(*args, **kwargs):
    """Reject use of the removed legacy upload sample."""
    return _unsupported(*args, **kwargs)


def sftp_get(*args, **kwargs):
    """Reject use of the removed legacy download sample."""
    return _unsupported(*args, **kwargs)


def ssh_client(*args, **kwargs):
    """Reject use of the removed legacy SSH sample."""
    return _unsupported(*args, **kwargs)


def rmtree(*args, **kwargs):
    """Reject use of the removed remote-tree deletion sample."""
    return _unsupported(*args, **kwargs)
