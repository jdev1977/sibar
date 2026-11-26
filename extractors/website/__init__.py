"""Deterministic website extractors (T1.4); see docs/extractors.md.

One module per feature family. Each reads the output's files through
:func:`extractors.website.site.get_site`, which parses them once.
"""

from extractors.website import (
    accessibility, corners_shadows, dark_mode, file_structure, fonts, gradients,
    icons_emoji, layout, libraries, palette, responsiveness, stock_phrases,
)

EXTRACTORS = (
    palette.EXTRACTOR,
    fonts.EXTRACTOR,
    libraries.EXTRACTOR,
    layout.EXTRACTOR,
    corners_shadows.EXTRACTOR,
    gradients.EXTRACTOR,
    icons_emoji.EXTRACTOR,
    stock_phrases.EXTRACTOR,
    file_structure.EXTRACTOR,
    responsiveness.EXTRACTOR,
    dark_mode.EXTRACTOR,
    accessibility.EXTRACTOR,
)
