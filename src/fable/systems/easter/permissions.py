import discord

async def grant_team_channel_access(bot, guild, user_id, channel_id):
    """
    Grants the user view access to the specified channel.
    """
    member = guild.get_member(user_id)
    if not member:
        try:
            member = await guild.fetch_member(user_id)
        except Exception:
            return False
    channel = bot.get_channel(channel_id)
    if not channel:
        return False
    try:
        await channel.set_permissions(member, view_channel=True)
        return True
    except Exception:
        return False
