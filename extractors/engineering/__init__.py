"""Deterministic engineering extractors (T2.8); see docs/extractors.md."""

from extractors.common.reply import reply_extractor
from extractors.engineering import design

EXTRACTORS = (reply_extractor("engineering"), *design.EXTRACTORS)
