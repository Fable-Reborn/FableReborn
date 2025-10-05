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
import discord
from discord.ext import commands
import random
import asyncio

class Slots(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.emojis = ['apple', 'cherries', 'doughnut', 'grapes', 'taco', 'watermelon']

    async def update_slots(self, slot_message, embed_dict, slots, rotations=3):
        for col in range(3):
            for rotation in range(rotations):
                for _ in range(3):
                    slot = random.choice(self.emojis)
                    slot = f':{slot}:'
                    slots[_][col] = slot

                slot_spin = self.slot_spin(slots)
                embed_dict['fields'][1]['name'] = slot_spin
                embed = discord.Embed.from_dict(embed_dict)
                await slot_message.edit(embed=embed)
                await asyncio.sleep(0.3)  # Adjust this sleep duration for faster or slower rotation

        # Lock in the fruits after rotations
        for col in range(3):
            for _ in range(3):
                slot = random.choice(self.emojis)
                slot = f':{slot}:'
                slots[_][col] = slot

            slot_spin = self.slot_spin(slots)
            embed_dict['fields'][1]['name'] = slot_spin
            embed = discord.Embed.from_dict(embed_dict)
            await slot_message.edit(embed=embed)
            await asyncio.sleep(0.3)  # Adjust this sleep duration for faster or slower animation

    @commands.command()
    async def slots(self, ctx):
        icon_url = 'https://i.imgur.com/8oGuoyq.png'
        jackpot = '$$$ !!! JACKPOT !!! $$$'
        jackshit = '(◕‿◕)╭∩╮ YOU GET NOTHING !!!'

        embed = discord.Embed(colour=discord.Colour.gold())
        embed.set_author(name='Slot Machine', icon_url=icon_url)
        embed.add_field(
            name=f'*{ctx.author.name} pulls the slot machine handle...*',
            value='\u200b\n**Jackpot: 0**',  # Added Jackpot: 0 line
            inline=False
        )

        slots = [['\t' for _ in range(3)] for _ in range(3)]
        slot_spin = self.slot_spin(slots)
        embed.add_field(name=slot_spin, value='\u200b')
        embed_dict = embed.to_dict()
        slot_message = await ctx.send(embed=embed)

        await self.update_slots(slot_message, embed_dict, slots)

        if (
            slots[0][0] == slots[1][1] and slots[2][2] == slots[1][1] or
            slots[0][2] == slots[1][1] and slots[2][0] == slots[1][1] or
            slots[0][0] == slots[0][1] and slots[0][1] == slots[0][2] or
            slots[1][0] == slots[1][1] and slots[1][1] == slots[1][2] or
            slots[2][0] == slots[2][1] and slots[2][1] == slots[2][2] or
            slots[0][0] == slots[1][0] and slots[1][0] == slots[2][0] or
            slots[0][1] == slots[1][1] and slots[1][1] == slots[2][1] or
            slots[0][2] == slots[1][2] and slots[1][2] == slots[2][2]
        ):
            embed.set_footer(text=jackpot)
        else:
            embed.set_footer(text=jackshit)
        await slot_message.edit(embed=embed)

    def slot_spin(self, slots):
        result = ''
        for row in range(3):
            result += '|'
            for col in range(3):
                result += f'\t{slots[row][col]}\t|'
            result += '\n'
        return result

async def setup(bot):
    await bot.add_cog(Slots(bot))
