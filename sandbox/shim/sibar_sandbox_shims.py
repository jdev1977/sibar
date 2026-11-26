"""Optional fixes for some tasks run in the sibar sandbox (T2.7).

Turned on by the sandbox through ``SIBAR_SANDBOX_SHIMS``. Not a boundary.
"""


def install():
    """Install the shims named in the environment; return import hooks."""
    return {}
