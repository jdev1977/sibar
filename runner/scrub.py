"""Removing API keys from text before it is printed or stored (T0.5).

Keys are read from environment variables only and sent only in request
headers. Console output and error text pass through a :class:`Scrubber`
holding the keys in use, which also replaces anything shaped like a well-known
key or bearer token. Model output (raw responses, extracted files) gets only
the exact keys in use replaced (:meth:`Scrubber.exact`), so the model's own
key-shaped placeholders stay as written.
"""

import re

REDACTED = "[redacted]"
MIN_SECRET_LENGTH = 8
_SHAPES = re.compile(
    r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{16,}"         # Anthropic, OpenAI, DeepSeek
    r"|(?<![A-Za-z0-9])AIza[A-Za-z0-9_-]{30,}"       # Google
    r"|(?i:bearer)\s+[A-Za-z0-9._~+/=-]{16,}"        # any bearer token
)


class Scrubber:
    def __init__(self, secrets=()):
        self._secrets = []
        for secret in secrets:
            self.add(secret)

    def add(self, secret):
        """Also replace ``secret`` (ignored if shorter than 8 characters)."""
        if isinstance(secret, str) and len(secret) >= MIN_SECRET_LENGTH:
            if secret not in self._secrets:
                self._secrets.append(secret)
                self._secrets.sort(key=len, reverse=True)

    def exact(self, text):
        """``text`` with only the keys in use replaced: for model output
        (raw responses, extracted files), which may legitimately contain
        key-shaped placeholders that must stay as written."""
        text = str(text)
        for secret in self._secrets:
            text = text.replace(secret, REDACTED)
        return text

    def __call__(self, text):
        """``text`` (any object, as ``str``) with the keys in use and anything
        key-shaped replaced: for console output and error text."""
        return _SHAPES.sub(REDACTED, self.exact(text))
