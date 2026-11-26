"""Every extractor, by project type.

Each project type's package (``extractors.<type>``) lists its extractors in
an ``EXTRACTORS`` tuple, in the order they run. To add a type, create
its package and add its module name to :data:`PACKAGES`.
"""

import importlib

PACKAGES = ("extractors.website", "extractors.pipeline", "extractors.math")


def all_extractors():
    """Every registered extractor, packages in :data:`PACKAGES` order.

    Raises ValueError if two share a name.
    """
    found, names = [], set()
    for package in PACKAGES:
        for extractor in importlib.import_module(package).EXTRACTORS:
            if extractor.name in names:
                raise ValueError(f"two extractors are named {extractor.name!r}")
            names.add(extractor.name)
            found.append(extractor)
    return tuple(found)


def extractors_for(project_type):
    """The extractors that apply to ``project_type``, in run order."""
    return tuple(e for e in all_extractors() if e.project_type == project_type)


def by_name():
    """``{name: extractor}`` for every registered extractor."""
    return {e.name: e for e in all_extractors()}
