"""Deterministic pipeline extractors (T2.8); see docs/extractors.md."""

from extractors.common.reply import reply_extractor
from extractors.pipeline import behaviour, ci, images, libraries, structure

EXTRACTORS = (
    reply_extractor("pipeline"),
    *structure.EXTRACTORS,
    libraries.EXTRACTOR,
    *behaviour.EXTRACTORS,
    images.EXTRACTOR,
    ci.EXTRACTOR,
)
