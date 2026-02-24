from __future__ import annotations

"""Compatibility shim for NewWerewolf runtime.

The canonical 1:1 multiplayer implementation lives in `cogs.newwerewolf.core`.
`NewWerewolfGame` aliases that implementation so existing imports continue to work.
"""

from .core import Game as NewWerewolfGame

__all__ = ["NewWerewolfGame"]