"""Inert legacy compatibility surface for removed FTP/SFTP samples.

This deployment snapshot no longer contains connection details or performs
network operations.  The original helpers were incomplete examples and are
unsupported.
"""


class UnsupportedFTPIntegrationError(RuntimeError):
    """Raised when a removed legacy FTP/SFTP helper is called."""


def _unsupported(*args, **kwargs):
    del args, kwargs
    raise UnsupportedFTPIntegrationError(
        "The legacy FTP/SFTP sample integration is deprecated and unsupported."
    )


def sftp_put(*args, **kwargs):
    return _unsupported(*args, **kwargs)


def sftp_get(*args, **kwargs):
    return _unsupported(*args, **kwargs)


def ssh_client(*args, **kwargs):
    return _unsupported(*args, **kwargs)


def rmtree(*args, **kwargs):
    return _unsupported(*args, **kwargs)
