"""Stable catalog identities and discovery storage for Soulforge Frontiers."""

from pathlib import Path
from typing import Optional

from discord.ext import commands

from .storage import DISCOVERY_EVENT_TYPES, FrontierCatalogStore


class FrontierCatalog(commands.Cog):
    """Infrastructure cog; player-facing commands live in Soulforge Frontiers."""

    def __init__(self, bot):
        self.bot = bot
        project_root = Path(__file__).resolve().parents[2]
        self.store = FrontierCatalogStore(bot.pool, project_root / "monsters.json")

    async def cog_load(self) -> None:
        await self.store.ensure_ready()


def get_frontier_catalog(bot) -> Optional[FrontierCatalogStore]:
    """Return the shared storage API, or ``None`` when its cog is not loaded."""
    cog = bot.get_cog("FrontierCatalog")
    return cog.store if cog is not None else None


async def setup(bot):
    await bot.add_cog(FrontierCatalog(bot))


__all__ = (
    "DISCOVERY_EVENT_TYPES",
    "FrontierCatalog",
    "FrontierCatalogStore",
    "get_frontier_catalog",
)
