"""Who may click gear menus.

Same rule as `$armory` and `$alt`: the character the command ran as, plus
the Discord user who typed `$alt` (`ctx.alt_invoker_id`). Anyone else is refused.
Gold, listings, and forge work stay on `ctx.author` (the linked alt).
"""
from __future__ import annotations


def menu_actor_ids(ctx) -> set[int]:
    allowed = {int(ctx.author.id)}
    alt_invoker_id = getattr(ctx, "alt_invoker_id", None)
    if alt_invoker_id is not None:
        allowed.add(int(alt_invoker_id))
    return allowed


def is_menu_actor(ctx, user_id: int) -> bool:
    return int(user_id) in menu_actor_ids(ctx)


async def require_menu_actor(ctx, interaction, message: str) -> bool:
    if is_menu_actor(ctx, interaction.user.id):
        return True
    if not interaction.response.is_done():
        await interaction.response.send_message(message, ephemeral=True)
    return False


async def actor_may_use_character(conn, actor_id: int, character_id: int) -> bool:
    """Persistent buttons have no command ctx. Allow the character, or their linked main."""
    actor_id = int(actor_id)
    character_id = int(character_id)
    if actor_id == character_id:
        return True
    return bool(
        await conn.fetchval(
            "SELECT 1 FROM alt_links WHERE main = $1 AND alt = $2",
            actor_id,
            character_id,
        )
    )
