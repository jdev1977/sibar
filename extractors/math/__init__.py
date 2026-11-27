"""Deterministic math and science extractors (T2.8); see docs/extractors.md."""

from extractors.common.reply import reply_extractor
from extractors.math import notation, values

EXTRACTORS = (reply_extractor("math"), *notation.EXTRACTORS, *values.EXTRACTORS)
