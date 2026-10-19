"""Night Watch role. Opt-in ping for the Hollow Manor and the phantom door."""

import discord


WATCH_ROLE_NAME = "Night Watch"
WATCH_COLOR = discord.Color.from_rgb(228, 87, 46)


def find_watch_role(guild: discord.Guild):
    return discord.utils.find(lambda item: item.name.lower() == WATCH_ROLE_NAME.lower(), guild.roles)


async def ensure_watch_role(guild: discord.Guild):
    role = find_watch_role(guild)
    if role is not None:
        return role
    me = guild.me
    if me is None or not me.guild_permissions.manage_roles:
        return None
    try:
        return await guild.create_role(
            name=WATCH_ROLE_NAME,
            color=WATCH_COLOR,
            mentionable=True,
            reason="Halloween Night Watch ping role",
        )
    except discord.HTTPException:
        return None


async def ping_watchers(channel, text: str):
    """Mention Night Watch if the role exists. Everyone can still see the channel."""
    role = find_watch_role(channel.guild)
    try:
        if role is None:
            await channel.send(text)
        else:
            await channel.send(
                f"{role.mention} {text}",
                allowed_mentions=discord.AllowedMentions(roles=[role]),
            )
    except discord.HTTPException:
        return role
    return role


async def set_watching(member: discord.Member, enabled: bool) -> str:
    guild = member.guild
    role = await ensure_watch_role(guild)
    if role is None:
        return "I could not find or create the Night Watch role. I need Manage Roles."
    me = guild.me
    if role.managed or (me is not None and role >= me.top_role):
        return "Move the Night Watch role below my highest role so I can assign it."
    try:
        if enabled and role not in member.roles:
            await member.add_roles(role, reason="Night Watch opt-in")
        elif not enabled and role in member.roles:
            await member.remove_roles(role, reason="Night Watch opt-out")
    except discord.HTTPException:
        return "I do not have permission to manage the Night Watch role."
    if enabled:
        return (
            "You are on **Night Watch**. I will ping this role when the Hollow Manor "
            "opens and when a phantom door appears."
        )
    return "You are off Night Watch. The channels still appear; you just will not be pinged."
