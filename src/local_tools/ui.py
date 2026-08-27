"""Small presentation helpers shared by the tool pages."""

from __future__ import annotations

import socket

_BYTES_PER_UNIT = 1024


def format_size(num_bytes: int) -> str:
    """Render a byte count as a short human-readable string.

    Args:
        num_bytes: Size in bytes.

    Returns:
        The size scaled to B, KB, MB or GB with one decimal place.
    """
    size = float(num_bytes)
    for unit in ("B", "KB", "MB"):
        if size < _BYTES_PER_UNIT:
            return f"{size:,.1f} {unit}"
        size /= _BYTES_PER_UNIT
    return f"{size:,.1f} GB"


def format_duration(seconds: float) -> str:
    """Render a duration in seconds as ``1m 05s``.

    Args:
        seconds: Elapsed wall-clock time.

    Returns:
        A compact ``<m>m <ss>s`` string, dropping the minutes when they are zero.
    """
    minutes, remainder = divmod(int(seconds), 60)
    return f"{minutes}m {remainder:02d}s" if minutes else f"{remainder}s"


def host_label() -> str:
    """Return the hostname of the machine running the server.

    The app is reached over the network, so every path a page shows or accepts
    belongs to this host rather than to the visitor's own computer. Pages use
    this to say so.

    Returns:
        The short hostname, or ``"this server"`` if it cannot be determined.
    """
    return socket.gethostname() or "this server"
