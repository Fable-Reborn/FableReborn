"""
The IdleRPG Discord Bot
Copyright (C) 2018-2021 Diniboy and Gelbpunkt
Copyright (C) 2023-2024 Lunar (PrototypeX37)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
import random

import discord
from discord.ext import commands
import asyncio
from PIL import Image, ImageDraw, ImageEnhance
from io import BytesIO

from fable.utils.checks import is_gm


class WarMap(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    def lerp(self, a, b, t):
        """Linear interpolation between a and b."""
        return a + (b - a) * t

    def gradient_arrow(self, draw, start, end, start_color, end_color, steps=100):
        """Draw an arrow with a gradient from start_color to end_color."""
        for i in range(steps):
            t = i / steps
            color = (
                int(self.lerp(start_color[0], end_color[0], t)),
                int(self.lerp(start_color[1], end_color[1], t)),
                int(self.lerp(start_color[2], end_color[2], t))
            )
            segment_start = (self.lerp(start[0], end[0], t), self.lerp(start[1], end[1], t))
            segment_end = (self.lerp(start[0], end[0], t + 1 / steps), self.lerp(start[1], end[1], t + 1 / steps))
            draw.line([segment_start, segment_end], fill=color, width=5)

        # Draw the arrowhead (triangle)
        arrowhead_length = 15
        arrowhead_width = 10
        arrow_direction = ((end[0] - start[0]), (end[1] - start[1]))
        arrow_direction_normalized = (
            arrow_direction[0] / (arrow_direction[0] ** 2 + arrow_direction[1] ** 2) ** 0.5,
            arrow_direction[1] / (arrow_direction[0] ** 2 + arrow_direction[1] ** 2) ** 0.5)

        point1 = end
        point2 = (
            end[0] - arrowhead_length * arrow_direction_normalized[0] + arrowhead_width * 0.5 *
            arrow_direction_normalized[1],
            end[1] - arrowhead_length * arrow_direction_normalized[1] - arrowhead_width * 0.5 *
            arrow_direction_normalized[0])
        point3 = (
            end[0] - arrowhead_length * arrow_direction_normalized[0] - arrowhead_width * 0.5 *
            arrow_direction_normalized[1],
            end[1] - arrowhead_length * arrow_direction_normalized[1] + arrowhead_width * 0.5 *
            arrow_direction_normalized[0])

        draw.polygon([point1, point2, point3], fill=end_color)

    @is_gm()
    @commands.command()
    async def warmap(self, ctx):
        try:
            await ctx.send("Generating War Map. Please wait..")

            await asyncio.sleep(1)

            await ctx.send("No current war, Showing Default Map..!")

            await asyncio.sleep(4)

            # Load your map
            base_map = Image.open("assets/images/conquest/Map.png")

            enhancer = ImageEnhance.Brightness(base_map)
            base_map = enhancer.enhance(0.65)  # Decrease brightness (0.7 is just an example, adjust as needed)

            # Load flags and resize them
            flag_size = (75, 150)
            asterea_flag = Image.open("assets/images/conquest/Good_Flag.png").resize(flag_size)
            sepulchre_flag = Image.open("assets/images/conquest/Evil_Flag.png").resize(flag_size)
            drakath_flag = Image.open("assets/images/conquest/Chaos_Flag.png").resize(flag_size)
            neutral_flag = Image.open("assets/images/conquest/Neutral.png").resize(flag_size)

            # Define predefined coordinates for territories
            territories_coords = {
                "Drakath": (1344, 306),
                "Zanjuro": (1172, 405),
                "OrderTemple": (944, 209),
                "Isyldill": (932, 500),
                "Shir": (1305, 822),
                "Ollin": (787, 702),
                "Sepulchre": (440, 874),
                "Lankerque": (710, 498),
                "DragonFoe": (552, 695),
                "Asterea": (119, 144),
                "BuhayCitadel": (327, 309),
                "BreftValley": (473, 135),
                "WellOfUnity": (615, 289),
                "Manumit": (260, 470),
                "BoneDunes": (157, 549),
                "DragonMountain": (75, 781),
                "Lakoldon": (468, 448),
                "Telfinor": (741, 179),
                "OnlookerPeak": (298, 774),
            }

            connections = [
                ("Drakath", "Zanjuro"),
                ("Zanjuro", "OrderTemple"),
                ("OrderTemple", "Isyldill"),
                ("Isyldill", "Shir"),
                ("Zanjuro", "Shir"),
                ("Shir", "Ollin"),
                ("Ollin", "Lankerque"),
                ("Sepulchre", "OnlookerPeak"),
                ("Lankerque", "DragonFoe"),
                ("Asterea", "BuhayCitadel"),
                ("BuhayCitadel", "BreftValley"),
                ("BreftValley", "WellOfUnity"),
                ("BuhayCitadel", "Manumit"),
                ("Manumit", "BoneDunes"),
                ("BoneDunes", "DragonMountain"),
                ("OnlookerPeak", "DragonMountain"),
                ("Lakoldon", "Manumit"),
                ("Lakoldon", "Lankerque"),
                ("Telfinor", "BreftValley"),
                ("Telfinor", "OrderTemple"),
                ("Lankerque", "WellOfUnity"),
                ("Lankerque", "Isyldill"),
                ("Isyldill", "WellOfUnity"),
                ("OnlookerPeak", "DragonFoe"),
            ]

            # Example data from your database (replace this with actual data)
            territories_control = {
                "Drakath": "Drakath",
                "Sepulchre": "Sepulchre",
                "Asterea": "Asterea",
            }

            # Overlay flags on territories
            color_map = {
                'Asterea': (255, 255, 0),
                'Sepulchre': (255, 0, 0),
                'Drakath': (128, 0, 128),
                'Neutral': (255, 255, 255)  # White color for neutral
            }

            # Overlay flags on territories
            for territory, coords in territories_coords.items():
                god = territories_control.get(territory, "Neutral")  # Default to "Neutral" if not found
                adjusted_coords = (coords[0] - flag_size[0] // 2, coords[1] - flag_size[1])

                flag_map = {
                    'Asterea': asterea_flag,
                    'Sepulchre': sepulchre_flag,
                    'Drakath': drakath_flag,
                    'Neutral': neutral_flag
                }
                flag = flag_map.get(god)

                if flag:
                    base_map.paste(flag, adjusted_coords, flag)

            draw = ImageDraw.Draw(base_map)

            # Draw arrows for connections and flags on top of arrows
            for start, end in connections:
                start_coords = territories_coords[start]
                end_coords = territories_coords[end]
                start_color = color_map.get(territories_control.get(start, "Neutral"))
                end_color = color_map.get(territories_control.get(end, "Neutral"))

                self.gradient_arrow(draw, start_coords, end_coords, start_color, end_color)

                # Place flags on top of the arrows
                start_flag = flag_map.get(territories_control.get(start, "Neutral"))
                end_flag = flag_map.get(territories_control.get(end, "Neutral"))

                if start_flag:
                    base_map.paste(start_flag, (start_coords[0] - flag_size[0] // 2, start_coords[1] - flag_size[1]),
                                   start_flag)
                if end_flag:
                    base_map.paste(end_flag, (end_coords[0] - flag_size[0] // 2, end_coords[1] - flag_size[1]),
                                   end_flag)

            # Save the Resulting Map
            base_map.save("result.png")

            # Load the generated map image
            map_image = Image.open("result.png")

            # Convert the PIL image to bytes
            image_bytes = BytesIO()
            map_image.save(image_bytes, format="PNG")
            image_bytes.seek(0)

            # Send the image to the Discord channel
            await ctx.send(file=discord.File(image_bytes, filename="result.png"))

        except Exception as e:
            # Handle exceptions and send an error message
            await ctx.send(f"An error occurred: {str(e)}")

    async def set_default_values(self):
        async with self.bot.pool.acquire() as connection:
            query = """
            UPDATE wardata 
            SET wood = $1, 
                stone = $2, 
                iron = $3, 
                defenselevel = $4, 
                strength = $5
            """
            await connection.execute(query, 100, 100, 0, 0, 1000)

    @is_gm()
    @commands.command()
    async def gmstartwar(self, ctx):
        await ctx.send("Initializing war data...")
        await self.set_default_values()
        await ctx.send("War data initialized with default values!")


    @is_gm()
    @commands.command()
    async def war_stats(self, ctx):
        index = 0

        FACTION_THUMBNAILS = {
            'Asterea': 'https://i.postimg.cc/LXRbqqkt/AQWMember.png',
            'Sepulchure': 'https://i.postimg.cc/xCRFL0gW/Shadow-Scythe.png',
            'Drakath': 'https://i.postimg.cc/j2S3XGFC/t-B4-RRq9-1.png'
        }

        try:
            async with self.bot.pool.acquire() as connection:
                factions_data = [
                    await self.fetch_faction_data(connection, 'Asterea'),
                    await self.fetch_faction_data(connection, 'Sepulchure'),
                    await self.fetch_faction_data(connection, 'Drakath')
                ]

            message = await ctx.send(embed=self.create_embed(index, factions_data, FACTION_THUMBNAILS))

            for emoji in ['⬅️', '➡️']:
                await message.add_reaction(emoji)

            def check(reaction, user):
                return user == ctx.author and str(reaction.emoji) in ['⬅️', '➡️'] and reaction.message == message

            while True:
                try:
                    reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)

                    if str(reaction.emoji) == '➡️':
                        index = (index + 1) % len(factions_data)
                    elif str(reaction.emoji) == '⬅️':
                        index = (index - 1) % len(factions_data)

                    await message.edit(embed=self.create_embed(index, factions_data, FACTION_THUMBNAILS))

                    if not isinstance(ctx.channel, discord.DMChannel):
                        await message.remove_reaction(reaction, user)

                except asyncio.TimeoutError:
                    break

        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

    async def fetch_faction_data(self, connection, faction_name):
        query = "SELECT strength, wood, stone, iron, defenselevel FROM wardata WHERE god = $1"
        async with connection.transaction():
            row = await connection.fetchrow(query, faction_name)
            if row:
                return {
                    'forces': faction_name,  # Fixed value based on faction_name
                    'forces_strength': row['strength'],
                    'wood': row['wood'],
                    'stone': row['stone'],
                    'iron': row['iron'],
                    'defense_rating': row['defenselevel']
                }
            else:
                return None

    def create_embed(self, index, factions_data, FACTION_THUMBNAILS):
        faction_data = factions_data[index]

        if faction_data:
            faction_name = f"{faction_data['forces']} Faction - {faction_data['forces']}"
            faction_thumbnail = FACTION_THUMBNAILS.get(faction_data['forces'], '')  # Get thumbnail URL from mapping
            embed = discord.Embed(title=faction_name, color=0xff0000)
            if faction_thumbnail:
                embed.set_thumbnail(url=faction_thumbnail)
            if faction_data['forces'] == "Drakath":
                embed.add_field(name="Force", value="Chaos Army", inline=False)
            if faction_data['forces'] == "Sepulchure":
                embed.add_field(name="Force", value="Shadow Legion", inline=False)
            if faction_data['forces'] == "Asterea":
                embed.add_field(name="Force", value="Army of Light", inline=False)
            embed.add_field(name="Forces Strength", value=faction_data['forces_strength'], inline=False)
            embed.add_field(name="Wood", value=faction_data['wood'], inline=False)
            embed.add_field(name="Stone", value=faction_data['stone'], inline=False)
            embed.add_field(name="Iron", value=faction_data['iron'], inline=False)
            embed.add_field(name="Defense Rating", value=faction_data['defense_rating'], inline=False)
        else:
            embed = discord.Embed(title="Faction Data Unavailable",
                                  description="No data found for the specified faction.", color=0xff0000)

        return embed

    import random

    async def attack(self, ctx, attacker, defender, morale_change):
        # Calculate damage based on attacker's strength and morale
        base_damage = attacker['strength'] // 50  # Adjust this divisor as needed
        damage = random.randint(base_damage // 2, base_damage)

        # Apply morale modifier to damage
        morale_modifier = 1 + morale_change  # Morale change is a percentage
        damage *= morale_modifier

        # Apply critical hit chance
        if random.random() < attacker['critical_chance']:
            damage *= 2  # Critical hit doubles the damage

        # Apply number strength modifier to defender's strength
        defender['strength'] -= damage

        # Check if defender's strength is depleted
        defender['strength'] = max(0, defender['strength'])
        if defender['strength'] <= 0:
            return True, damage  # Defender defeated
        return False, damage  # Defender still alive

    async def calculate_retreat(self, force, other_force):
        # Calculate the likelihood of retreat based on morale, strength, and other factors
        morale_effect = force['morale']  # Morale directly affects the likelihood of retreat
        strength_effect = other_force['strength'] - force['strength']  # Relative strength advantage/disadvantage

        if morale_effect < 0.08:  # If morale is critically low, force is likely to retreat
            retreat = random.randint(1, 10)
            if retreat >= 3:
                return True
        if strength_effect > 0.2:  # If this force has a significant strength advantage, no retreat
            return False
        if morale_effect < 0.3:  # If morale is moderately low, retreat is more likely
            retreat = random.randint(1, 10)
            if retreat <= 2:
                return True
        return False  # Otherwise, no retreat

    async def calculate_morale_change(self, ctx, force, other_force):
        # Determine the relative size of the forces
        size_difference = force['strength'] / other_force['strength']

        # Determine morale change based on size difference
        if size_difference > 2:  # If this force is more than twice the size
            morale_change = round(random.uniform(-0.20, -0.10), 2)
        elif size_difference > 1:  # If this force is 50-100% bigger
            morale_change = round(random.uniform(-0.01, -0.05), 2)
        elif size_difference > 0.5:  # If this force is 0-50% bigger
            morale_change = round(random.uniform(-0.01, -0.10), 2)
        else:  # If forces are evenly matched or other force is bigger
            morale_change = 0  # No change in morale

        # Apply morale change to force's morale
        force['morale'] += morale_change
        force['morale'] = max(min(force['morale'], 1.0), 0.0)  # Ensure morale stays within [0, 1] range
    async def battle_round(self, ctx, force1, force2, round_num):
        # Round strength and morale to whole numbers
        force1_strength = round(force1['strength'])
        force2_strength = round(force2['strength'])
        force1_morale = round(force1['morale'])
        force2_morale = round(force2['morale'])

        # Force 1 attacks
        force1_attack = await self.attack(ctx, force1, force2, force1_morale)
        if force1_attack[0]:
            return force1['name'], round_num, force1_attack[1]
        await asyncio.sleep(1)

        # Force 2 attacks
        force2_attack = await self.attack(ctx, force2, force1, force2_morale)
        if force2_attack[0]:
            return force2['name'], round_num, force2_attack[1]
        await asyncio.sleep(1)

        return None, round_num, force1_attack[1] + force2_attack[1]

    @is_gm()
    @commands.command()
    async def battletest(self, ctx, force1_name: str, force2_name: str):
        try:
            """Simulate a battle between two forces."""
            force1 = {'name': force1_name, 'strength': random.randint(100000, 120000), 'min_damage': 10, 'max_damage': 60,
                      'critical_chance': 0.2, 'morale': random.uniform(1, 1)}
            force2 = {'name': force2_name, 'strength': random.randint(100000, 110000), 'min_damage': 10, 'max_damage': 50,
                      'critical_chance': 0.2, 'morale': random.uniform(1, 1)}

            embed = discord.Embed(title="Battle Begins", color=discord.Color.red())
            embed.add_field(name=force1['name'],
                            value=f"Strength: {force1['strength']}\nMorale: {int(force1['morale'] * 100)}%", inline=True)
            embed.add_field(name=force2['name'],
                            value=f"Strength: {force2['strength']}\nMorale: {int(force2['morale'] * 100)}%", inline=True)
            embed.set_footer(text="Round 1")
            embed.add_field(name="Damage Dealt This Turn", value="None", inline=False)

            msg = await ctx.send(embed=embed)
            round_num = 1

            while force1['strength'] > 0 and force2['strength'] > 0:
                winner, round_num, damage = await self.battle_round(ctx, force1, force2, round_num)
                if winner:
                    embed = discord.Embed(title="Battle Over", color=discord.Color.green())
                    embed.add_field(name="Winner", value=winner, inline=False)
                    embed.add_field(name="Round", value=round_num, inline=False)
                    embed.add_field(name=f"{force1_name} Remaining Forces:", value=f"Strength: {force1['strength']}",
                                    inline=False)
                    embed.add_field(name=f"{force2_name} Remaining Forces:", value=f"Strength: {force2['strength']}",
                                    inline=False)
                    await msg.edit(embed=embed)
                    return

                if round_num > 3:
                    if await self.calculate_retreat(force1, force2):
                        embed = discord.Embed(title="Force Retreated", color=discord.Color.red())
                        embed.add_field(name="Retreating Force", value=force1_name, inline=False)
                        embed.add_field(name="Round", value=round_num, inline=False)
                        embed.add_field(name=f"{force1_name} Remaining Forces:", value=f"{force1['strength']}",
                                        inline=False)
                        embed.add_field(name=f"{force2_name} Remaining Forces:", value=f"{force2['strength']}",
                                        inline=False)
                        await msg.edit(embed=embed)
                        return
                    if await self.calculate_retreat(force2, force1):
                        embed = discord.Embed(title="Force Retreated", color=discord.Color.red())
                        embed.add_field(name="Retreating Force", value=force2_name, inline=False)
                        embed.add_field(name="Round", value=round_num, inline=False)
                        embed.add_field(name=f"{force1_name} Remaining Forces:", value=f"{force1['strength']}",
                                        inline=False)
                        embed.add_field(name=f"{force2_name} Remaining Forces:", value=f"{force2['strength']}",
                                        inline=False)
                        await msg.edit(embed=embed)
                        return

                # Calculate morale change for each force
                await self.calculate_morale_change(ctx, force1, force2)
                await self.calculate_morale_change(ctx, force2, force1)

                # Update embed for next round
                embed.set_footer(text=f"Round {round_num + 1}")
                embed.set_field_at(0, name=force1['name'],
                                   value=f"Strength: {force1['strength']}\nMorale: {int(force1['morale'] * 100)}%",
                                   inline=True)
                embed.set_field_at(1, name=force2['name'],
                                   value=f"Strength: {force2['strength']}\nMorale: {int(force2['morale'] * 100)}%",
                                   inline=True)
                embed.set_field_at(2, name="Damage Dealt This Turn", value=damage, inline=False)
                await msg.edit(embed=embed)

                round_num += 1
        except Exception as e:
            await ctx.send(e)


async def setup(bot):
    await bot.add_cog(WarMap(bot))
