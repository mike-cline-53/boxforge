"""Joinery edge profile generators.

Phase 1 ships with finger joints only. Adding a new joinery type is a
matter of dropping a module next to :mod:`finger` and extending the type
dispatch in :mod:`boxforge.box`.
"""

from . import finger, slots

__all__ = ["finger", "slots"]
