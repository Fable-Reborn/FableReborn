import discord

def render_hp_bar(current, maximum, length=10):
    if maximum <= 0:
        return 'N/A'
    percent = max(0, min(1, current / maximum))
    filled = int(round(percent * length))
    empty = length - filled
    return '▰' * filled + '▱' * empty + f' {int(percent*100)}%'

async def build_leaderboard_embed(easter_cog, guild):
    teams = easter_cog.teams
    placements = easter_cog.placements
    embed = discord.Embed(
        title='🏆 Guardian Race Leaderboard',
        description='Live status of all guardians. First team to defeat their assigned rival wins 1st place!'
    )
    place_emojis = ['🥇', '🥈', '🥉']
    for idx, (team_name, team_data) in enumerate(teams.items()):
        guardian = team_data['guardian']
        hp = guardian.get('hp', guardian.get('base_hp', 1))
        max_hp = guardian.get('base_hp', 1)
        hp_bar = render_hp_bar(hp, max_hp)
        w = team_data.get('victories', 0)
        l = team_data.get('defeats', 0)
        if team_name in placements:
            place = place_emojis[placements.index(team_name)]
            status = f'{place} {placements.index(team_name)+1} Place!'
        elif guardian.get('defeated', False):
            status = 'Defeated'
        else:
            status = 'Racing...'
        embed.add_field(
            name=f"{team_data['emoji']} {guardian['name']}",
            value=f"HP: {hp_bar}\nVictories: {w} | Defeats: {l}\nStatus: {status}",
            inline=False
        )
    return embed
