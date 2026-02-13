import asyncio
import datetime

import discord
from discord.enums import ButtonStyle
import random as randomm
from discord.ext import commands, tasks
from discord.ui import Button, View

from classes.converters import IntGreaterThan
from utils import random
from utils.checks import has_char, is_gm, is_god
from utils.i18n import _
from utils.joins import JoinView


class HorrorRaid(commands.Cog):
    """Raids are only available in the support server. Use the support command for an invite link."""

    def __init__(self, bot):
        self.bot = bot
        self.raid = {}
        self.toggle_list = set()  # For efficient membership checking
        self.chaoslist = []
        self.joined = []
        self.raidactive = False  # Indicates if a raid is currently running
        self.active_view = None
        self.raid_preparation = False
        self.boss = None
        self.last_keyword_response = 0  # Timestamp for keyword response cooldown

        ids_section = getattr(self.bot.config, "ids", None)
        horror_ids = getattr(ids_section, "horrorraid", {}) if ids_section else {}
        if not isinstance(horror_ids, dict):
            horror_ids = {}
        self.raid_channel_ids = horror_ids.get("raid_channel_ids", [])
        if not isinstance(self.raid_channel_ids, list):
            self.raid_channel_ids = []

        self.allow_sending = discord.PermissionOverwrite(send_messages=True, read_messages=True)
        self.deny_sending = discord.PermissionOverwrite(send_messages=False, read_messages=False)
        self.read_only = discord.PermissionOverwrite(send_messages=False, read_messages=True)

        # Store eclipse taunts so they can be used on a timer
        self.eclipse_taunts = [
            "**Eclipse whispers**: I sense your fear... delicious.",
            "**Eclipse hisses**: Your chaos god cannot save you from the void.",
            "**Eclipse laughs**: Your pathetic attempts amuse me.",
            "**Eclipse roars**: I've devoured entire realms. You are nothing!",
            "**Eclipse mocks**: Drakath's followers are as fragile as glass figurines.",
            "**Eclipse threatens**: I will consume your souls one by one.",
            "**Eclipse sneers**: Your master abandoned you—now face me alone.",
            "**Eclipse taunts**: Which one of you shall I break first?",
            "**Eclipse growls**: The void hungers... and you look appetizing.",
            "**Eclipse whispers**: I can hear your hearts racing with terror. Music to my ears."
        ]
        self.taunt_task = None

    async def taunt_loop(self, channels):
        """Background loop that sends a random eclipse taunt to all raid channels every 60 seconds."""
        try:
            while self.raidactive:
                await asyncio.sleep(60)
                taunt = randomm.choice(self.eclipse_taunts)
                for channel in channels:
                    await channel.send(taunt)
        except asyncio.CancelledError:
            return

    async def convert_to_display_names(self):
        display_names = []

        for user_id in self.chaoslist:
            # Fetch the user object (if you only have user IDs in self.chaoslist)
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)

            if user:  # Ensure the user exists
                display_names.append(user.display_name)
            else:
                display_names.append(f"Unknown User ({user_id})")  # Fallback for missing users

        return display_names

    @is_gm()
    @commands.command(hidden=True, breif=("See who was in your last raid"))
    async def chaoslist(self, ctx):
        try:
            if self.chaoslist is None:
                await ctx.send("Data on your most recent raid was not found")
            else:

                display_names = await self.convert_to_display_names()
                await ctx.send(content=f"Participants: {', '.join(display_names)}")
        except Exception as e:
            await ctx.send(e)

    @is_gm()
    @commands.command(hidden=True, brief=_("Start a Drakath raid"))
    async def chaosspawn(self, ctx, boss_hp: IntGreaterThan(0)):
        """[Drakath only] Starts a raid against Eclipse the Void Conqueror."""
        try:
            if not self.raid_channel_ids:
                await ctx.send("Horror raid channels are not configured.")
                return
            # Delay factor to slow down messages for readability.
            delay_factor = 2

            # Define the channels where the raid messages will be sent.
            channels = [self.bot.get_channel(channel_id) for channel_id in self.raid_channel_ids]

            async def send_to_channels(embed=None, content=None, view=None):
                """Helper function to send a message to all raid channels."""
                for channel in channels:
                    if channel is not None:
                        await channel.send(embed=embed, content=content, view=view)

            # Eclipse's critical hit messages.
            critical_messages = [
                "**Eclipse tears through reality** and rips into {target}'s essence!",
                "**Eclipse opens a void rift** beneath {target}'s feet!",
                "**Eclipse's tendrils of darkness** pierce {target}'s defenses!",
                "**Eclipse unleashes primordial horror** against {target}!",
                "**Eclipse consumes {target}'s life force** in a terrifying display!",
                "**Eclipse reveals its true form** to {target}, causing psychic damage!"
            ]

            # Join raid button with horror styling.
            view = JoinView(
                Button(style=ButtonStyle.danger, label="Sacrifice yourself to the raid!"),
                message=_("You've pledged your soul to the raid. There's no turning back now."),
                timeout=60 * 15,  # Join period lasts 15 minutes.
            )

            # Initial announcement with a horror-themed description.
            em = discord.Embed(
                title="𝔗𝔥𝔢 𝔙𝔬𝔦𝔡 𝔄𝔴𝔞𝔨𝔢𝔫𝔰",
                description=f"""
*The air grows cold. Reality warps and twists before your eyes.*

In Drakath's unholy name, unleash the storm,
Disciples of chaos, in darkness swarm.
The Void hungers, it calls, it screams,
Your nightmares manifest beyond your darkest dreams.

**Eclipse the Void Conqueror** has awakened with **{boss_hp} HP** 
and will breach our realm in **15 Minutes**

*Do you dare to defy the inevitable?*
""",
                color=0x9400D3,
            )
            em.set_image(url="https://i.imgur.com/YoszTlc.png")

            # Send the initial raid message and join button.
            await send_to_channels(embed=em, view=view)

            # --- Countdown Sequence ---
            await send_to_channels(content="**The void looms... 15 minutes remain until Eclipse descends!**")
            await asyncio.sleep(300)  # 5 minutes (15 -> 10 minutes remain)

            await send_to_channels(content="**The void stirs... Only 10 minutes remain before Eclipse descends!**")
            await asyncio.sleep(300)  # 5 minutes (10 -> 5 minutes remain)

            await send_to_channels(content="**The abyss roars with anticipation... 5 minutes remain until your doom!**")
            await asyncio.sleep(120)  # 2 minutes (5 -> 3 minutes remain)

            await send_to_channels(content="**Darkness gathers... 3 minutes remain before Eclipse awakens fully!**")
            await asyncio.sleep(60)   # 1 minute (3 -> 2 minutes remain)

            await send_to_channels(content="**The air grows colder... 2 minutes remain until the void consumes you!**")
            await asyncio.sleep(60)   # 1 minute (2 -> 1 minute remain)

            await send_to_channels(content="**Time is running thin... 1 minute remains before Eclipse tears through reality!**")
            await asyncio.sleep(30)   # 30 seconds (1 minute -> 30 seconds remain)

            await send_to_channels(content="**The void pulses with malignant energy... 30 seconds remain until your final reckoning!**")
            await asyncio.sleep(20)   # 20 seconds (30 -> 10 seconds remain)

            await send_to_channels(content="**Terror peaks... Only 10 seconds remain until the nightmare begins!**")
            await asyncio.sleep(10)   # Final 10 seconds before starting the raid
            # --- End of Countdown Sequence ---

            view.stop()

            # Activate raid listening.
            self.raidactive = True

            # Start the periodic taunt task.
            self.taunt_task = self.bot.loop.create_task(self.taunt_loop(channels))

            # Store the original boss health for accurate health bar computation.
            original_boss_hp = boss_hp

            # Raid begins.
            em = discord.Embed(
                title="𝕿𝖍𝖊 𝖁𝖔𝖎𝖉 𝕭𝖗𝖊𝖆𝖈𝖍",
                description="**Eclipse tears through reality! The raid has begun!**\n*Gathering the souls who dare challenge the void...*",
                color=0x9400D3,
            )
            em.set_image(url="https://i.imgur.com/lDqNHua.png")
            await send_to_channels(embed=em)

            HowMany = 0

            # Process participants: verify that only Drakath's followers join.
            async with self.bot.pool.acquire() as conn:
                raid = {}
                for u in view.joined:
                    if not (profile := await conn.fetchrow('SELECT * FROM profile WHERE "user"=$1;', u.id)) or profile["god"] != "Drakath":
                        await send_to_channels(
                            content=f"**Eclipse laughs**: {u.mention}, you are unworthy! The void rejects your offering."
                        )
                        continue
                    raid[u] = 250
                    HowMany += 1

            await send_to_channels(content=f"**{HowMany} souls have been claimed by the void!**")

            if HowMany == 0:
                em = discord.Embed(
                    title="The Void Retreats... For Now",
                    description="**Eclipse's laughter echoes**: Not even Drakath's followers dare face me? I shall return when your fear subsides...",
                    color=0x9400D3,
                )
                await send_to_channels(embed=em)
                self.raidactive = False
                if self.taunt_task:
                    self.taunt_task.cancel()
                return

            self.chaoslist = [u.id for u in raid.keys()]

            # Pre-battle taunt.
            pre_battle_taunt = discord.Embed(
                title="Eclipse Emerges",
                description=f"**Eclipse's voice booms**: {HowMany} insignificant mortals? Is this all Drakath sends? I will savor your terror as I consume you one by one.",
                color=0x9400D3,
            )
            pre_battle_taunt.set_image(url="https://i.imgur.com/YS4A6R7.png")
            await send_to_channels(embed=pre_battle_taunt)
            await asyncio.sleep(5 * delay_factor)

            start = datetime.datetime.utcnow()

            # Main battle loop.
            while boss_hp > 0 and len(raid) > 0 and datetime.datetime.utcnow() < start + datetime.timedelta(minutes=45):
                target = randomm.choice(list(raid.keys()))

                # Eclipse attacks a random player.
                is_critical = randomm.random() < 0.3  # 30% chance of a critical hit.
                dmg = randomm.randint(150, 350) if is_critical else randomm.randint(100, 300)
                raid[target] -= dmg

                if is_critical:
                    crit_message = randomm.choice(critical_messages).format(target=target)
                    em = discord.Embed(
                        title="𝕮𝖗𝖎𝖙𝖎𝖈𝖆𝖑 𝕳𝖎𝖙!",
                        description=f"{crit_message}",
                        colour=0xFF0000,
                    )
                    em.add_field(name="Devastating Damage", value=f"**{dmg}**")
                    em.set_thumbnail(url="https://i.imgur.com/YS4A6R7.png")
                elif raid[target] > 0:
                    em = discord.Embed(
                        title="Eclipse Strikes!",
                        description=f"{target} battles the void! **{raid[target]} HP** remains!",
                        colour=0x9400D3,
                    )
                    em.add_field(name="Damage", value=dmg)
                    em.set_thumbnail(url="https://i.imgur.com/YS4A6R7.png")
                else:
                    em = discord.Embed(
                        title="Soul Devoured!",
                        description=f"Eclipse consumes {target}'s essence! They are lost to the void!",
                        colour=0xFF0000,
                    )
                    em.add_field(name="Fatal Damage", value=dmg)
                    em.set_thumbnail(url="https://i.imgur.com/YS4A6R7.png")

                em.set_author(name=str(target), icon_url=target.display_avatar.url)
                await send_to_channels(embed=em)

                if raid[target] <= 0:
                    del raid[target]
                    if len(raid) == 0:
                        break
                    await asyncio.sleep(2 * delay_factor)
                    await send_to_channels(
                        content=f"**Eclipse savors**: One down... who's next? I can taste your fear, {randomm.choice(list(raid.keys())).mention}."
                    )

                # Random events.
                # Chaos Restore – follower health recovery.
                if randomm.randint(1, 5) == 1:
                    await asyncio.sleep(3 * delay_factor)
                    target = randomm.choice(list(raid.keys()))
                    heal_amount = randomm.randint(100, 150)
                    raid[target] += heal_amount
                    em = discord.Embed(
                        title="𝕮𝖍𝖆𝖔𝖘 𝕽𝖊𝖘𝖙𝖔𝖗𝖊!",
                        description=f"*Drakath's chaotic energy courses through {target}!* They recover to **{raid[target]} HP**!",
                        colour=0xFFB900,
                    )
                    em.set_author(name=str(target), icon_url=target.display_avatar.url)
                    em.set_thumbnail(url="https://i.imgur.com/md5dWFk.png")
                    await send_to_channels(embed=em)

                    healing_prompts = [
                        "**Eclipse bellows**: {target}, your healing is a dying gasp against the eternal void!",
                        "**Eclipse roars**: Every drop of your mending blood mocks your existence, {target}—the abyss awaits.",
                        "**Eclipse snarls**: {target}, your feeble recovery is the last lament of a doomed soul, soon to be swallowed by darkness!",
                        "**Eclipse jeers**: Your pitiful attempts to heal shatter like fragile glass before the relentless void, {target}!",
                        "**Eclipse mocks**: {target}, your recovery is but a futile spark destined to be devoured by endless night!",
                        "**Eclipse rages**: The light of your healing falters, {target}; soon, the void will extinguish your feeble hope forever!"
                    ]
                    await asyncio.sleep(2 * delay_factor)
                    await send_to_channels(content=randomm.choice(healing_prompts).format(target=target.mention))

                # Void Pulse – an AoE attack.
                if randomm.randint(1, 5) == 1:
                    await asyncio.sleep(3 * delay_factor)
                    warning_em = discord.Embed(
                        title="𝕰𝖈𝖑𝖎𝖕𝖘𝖊 𝕮𝖍𝖆𝖗𝖌𝖊𝖘 𝖆 𝕿𝖊𝖗𝖗𝖎𝖋𝖞𝖎𝖓𝖌 𝕬𝖙𝖙𝖆𝖈𝖐!",
                        description="*The void pulses with malevolent energy...*\n\n**Eclipse draws power from the darkness between stars!**",
                        colour=0xFF0000,
                    )
                    warning_em.set_thumbnail(url="https://i.imgur.com/lDqNHua.png")
                    await send_to_channels(embed=warning_em)

                    await asyncio.sleep(3 * delay_factor)

                    if len(raid) >= 3:
                        targets = randomm.sample(list(raid.keys()), 3)
                    else:
                        targets = list(raid.keys())

                    pulse_damage = randomm.randint(90, 130)
                    dead_targets = []
                    for tgt in targets:
                        raid[tgt] -= pulse_damage
                        if raid[tgt] <= 0:
                            dead_targets.append(tgt)
                    for tgt in dead_targets:
                        if tgt in raid:
                            del raid[tgt]
                    if dead_targets:
                        em = discord.Embed(
                            title="𝕰𝖝𝖙𝖎𝖓𝖈𝖙𝖎𝖔𝖓 𝕰𝖛𝖊𝖓𝖙!",
                            description=f"*Eclipse unleashes a devastating pulse!* {', '.join(str(u) for u in targets)} are struck!\n\n**{', '.join(str(u) for u in dead_targets)} {'have' if len(dead_targets) > 1 else 'has'} been obliterated!**",
                            colour=0xFF0000,
                        )
                    else:
                        em = discord.Embed(
                            title="𝕰𝖝𝖙𝖎𝖓𝖈𝖙𝖎𝖔𝖓 𝕰𝖛𝖊𝖓𝖙!",
                            description=f"*Eclipse unleashes a devastating pulse!* {', '.join(str(u) for u in targets)} take **{pulse_damage}** damage!",
                            colour=0xFF0000,
                        )
                    em.set_thumbnail(url="https://i.imgur.com/lDqNHua.png")
                    await send_to_channels(embed=em)

                    if len(raid) == 0:
                        break

                # Chaos followers attack Eclipse.
                await asyncio.sleep(3 * delay_factor)
                dmg_to_take = 0
                critical_attackers = []
                for attacker in raid:
                    if randomm.random() < 0.15:
                        damage = randomm.randint(75, 150)
                        critical_attackers.append(attacker)
                    else:
                        damage = randomm.randint(20, 40)
                    dmg_to_take += damage

                boss_hp -= dmg_to_take

                # Update the health bar based on original boss HP.
                if boss_hp < 0:
                    boss_hp = 0
                hp_percentage = boss_hp / original_boss_hp
                hp_bar = "█" * int(hp_percentage * 10) + "░" * (10 - int(hp_percentage * 10))

                if boss_hp > 0:
                    em = discord.Embed(
                        title="Eclipse Under Siege!",
                        description="*The void trembles under the combined assault...*",
                        colour=0x9400D3,
                    )
                    em.add_field(name="Combined Damage", value=f"**{dmg_to_take}**")
                    em.add_field(name="Eclipse HP", value=f"{boss_hp} |{hp_bar}|")
                    if hp_percentage < 0.3:
                        em.add_field(name="Eclipse's Rage", value="*Eclipse's form distorts with fury as it weakens!*", inline=False)
                else:
                    em = discord.Embed(
                        title="Eclipse Crumbles!",
                        description="**The void entity is faltering!**",
                        colour=0xFF0000,
                    )
                em.set_thumbnail(url="https://i.imgur.com/kf3zcLs.png")
                await send_to_channels(embed=em)

                if boss_hp > 0:
                    await asyncio.sleep(2 * delay_factor)
                    if dmg_to_take > 300:
                        messages_over_300 = [
                            "**Eclipse howls in pain**: IMPOSSIBLE! You will suffer for this!",
                            "**Eclipse screams in agony**: Your assault defies mortal limits—prepare for endless torment!",
                            "**Eclipse bellows**: Such devastating force! The void trembles at your challenge.",
                            "**Eclipse roars in despair**: Your might is overwhelming... yet it only deepens your suffering!",
                            "**Eclipse shrieks**: That damage is an affront to the cosmos—your fate is sealed!"
                        ]
                        await send_to_channels(content=randomm.choice(messages_over_300))
                    elif dmg_to_take > 150:
                        messages_over_150 = [
                            "**Eclipse hisses**: Your resistance is... unexpected.",
                            "**Eclipse growls**: You have strength, but it will not save you.",
                            "**Eclipse threatens**: I will make you regret that!",
                            "**Eclipse snarls**: Your feeble assault only fuels my wrath.",
                            "**Eclipse murmurs**: Such valor is futile; the void will consume you.",
                            "**Eclipse whispers**: Your efforts are noted... and doomed.",
                            "**Eclipse taunts**: Every blow you strike only intensifies your inevitable end!"
                        ]
                        await send_to_channels(content=randomm.choice(messages_over_150))
                    else:
                        messages_else = [
                            "**Eclipse laughs**: Is that all?",
                            "**Eclipse mocks**: Pathetic. I've been hurt worse by cosmic dust.",
                            "**Eclipse taunts**: Drakath's power grows weaker with each generation.",
                            "**Eclipse cackles**: Your feeble strikes barely ruffle the void.",
                            "**Eclipse snickers**: Even the slightest resistance amuses me.",
                            "**Eclipse ridicules**: Your puny attacks are nothing but whispers in the void.",
                            "**Eclipse jeers**: I expected more, mortal. Your efforts are laughable.",
                            "**Eclipse chortles**: You barely make a dent; the void remains unyielding.",
                            "**Eclipse snarls**: Insignificant damage! The abyss grows stronger at your expense."
                        ]
                        await send_to_channels(content=randomm.choice(messages_else))
                await asyncio.sleep(2 * delay_factor)

            # End-of-raid outcomes.
            if boss_hp > 1 and len(raid) > 0:
                em = discord.Embed(
                    title="𝕿𝖍𝖊 𝕯𝖆𝖗𝖐𝖓𝖊𝖘𝖘 𝕽𝖊𝖎𝖌𝖓𝖘",
                    description="*The void consumes all light, all hope...*\n\nDrakath's followers stand defeated before Eclipse's overwhelming might.",
                    color=0x9400D3,
                )
                em.set_image(url="https://i.imgur.com/s5tvHMd.png")
                final_message = discord.Embed(
                    title="Eclipse Ascends",
                    description="**Eclipse's voice booms**: Your god has abandoned you. Your chaos is nothing compared to the void's entropy. I will return... stronger... hungrier... And next time, not even Drakath will save you.",
                    color=0x9400D3
                )
                await send_to_channels(embed=em)
                await asyncio.sleep(3 * delay_factor)
                await send_to_channels(embed=final_message)

            elif len(raid) == 0:
                em = discord.Embed(
                    title="𝕿𝖔𝖙𝖆𝖑 𝕰𝖝𝖙𝖎𝖓𝖈𝖙𝖎𝖔𝖓",
                    description="*The last screams fade into the endless void...*\n\nAll of Drakath's followers have fallen; their souls now fuel Eclipse's growing power.",
                    color=0x9400D3,
                )
                em.set_image(url="https://i.imgur.com/UpWW3fF.png")
                final_taunt = discord.Embed(
                    title="Eclipse Feasts",
                    description="**Eclipse's satisfaction is palpable**: Such delicious souls... Tell your god I thank him for the offering. Perhaps next time, more worthy vessels will be sent.",
                    color=0x9400D3
                )
                await send_to_channels(embed=em)
                await asyncio.sleep(3 * delay_factor)
                await send_to_channels(embed=final_taunt)
            else:
                # Players win!
                winner = randomm.choice(list(raid.keys()))
                survivors = list(raid.keys())
                try:
                    async with self.bot.pool.acquire() as conn:
                        luck_query = await conn.fetchval('SELECT luck FROM profile WHERE "user" = $1;', winner.id)
                    luck_query_float = float(luck_query)
                    gods = {
                        "Elysia": {"boundary_low": 0.9, "boundary_high": 1.1},
                        "Sepulchure": {"boundary_low": 0.75, "boundary_high": 1.5},
                        "Drakath": {"boundary_low": 0.3, "boundary_high": 2.0},
                    }
                    selected_god = "Drakath"
                    god_data = gods.get(selected_god)
                    if not god_data:
                        raise ValueError(f"God {selected_god} not found.")
                    boundary_low = god_data["boundary_low"]
                    boundary_high = god_data["boundary_high"]
                    normalized_luck = (luck_query_float - boundary_low) / (boundary_high - boundary_low)
                    normalized_luck = max(0.0, min(1.0, normalized_luck))
                    weightdivine = 0.20 + (0.20 * normalized_luck)
                    rounded_weightdivine = round(weightdivine, 3)
                    options = ['legendary', 'fortune', 'divine']
                    weights = [0.40, 0.40, rounded_weightdivine]
                    crate = randomm.choices(options, weights=weights)[0]
                    try:
                        async with self.bot.pool.acquire() as conn:

                            await conn.execute(f'UPDATE profile SET "crates_{crate}" = "crates_{crate}" + 1 WHERE "user" = $1;', winner.id)
                            await self.bot.log_transaction(
                                ctx,
                                from_=1,
                                to=winner.id,
                                subject="Chaos Raid Crate",
                                data={"Rarity": crate, "Amount": 1},
                                conn=conn,
                            )
                    except Exception as e:
                        print(f"An error occurred: {e}")
                        crate = "legendary"  # Fallback if database update fails.

                    victory_em = discord.Embed(
                        title="𝕿𝖍𝖊 𝕷𝖎𝖌𝖍𝖙 𝕰𝖒𝖊𝖗𝖌𝖊𝖘",
                        description=f"*The void shudders as Eclipse's power fades...*\n\n**{len(survivors)} followers of Drakath** have banished Eclipse back to the void!",
                        color=0xFFB900,
                    )
                    victory_em.set_image(url="https://i.imgur.com/s5tvHMd.png")
                    survivors_list = ", ".join([s.mention for s in survivors])
                    victory_em.add_field(name="Survivors", value=survivors_list, inline=False)
                    prize_em = discord.Embed(
                        title="𝕯𝖗𝖆𝖐𝖆𝖙𝖍'𝖘 𝕾𝖊𝖑𝖊𝖈𝖙𝖎𝖔𝖓",
                        description=f"From the ruins of Eclipse, a {crate.capitalize()} crate materializes—drawn to {winner.mention}'s chaotic energy!\n\n*Drakath's laughter echoes across the battlefield*",
                        color=0xFFB900,
                    )
                    prize_em.set_thumbnail(url="https://i.imgur.com/3pg9Msj.png")
                    defeat_em = discord.Embed(
                        title="Eclipse Fades",
                        description="**Eclipse's voice weakens**: This... is not the end... I will return... and your souls... will be... *mine*...",
                        color=0x9400D3
                    )
                    await send_to_channels(embed=victory_em)
                    await asyncio.sleep(3 * delay_factor)
                    await send_to_channels(embed=prize_em)
                    await asyncio.sleep(3 * delay_factor)
                    await send_to_channels(embed=defeat_em)
                except Exception as e:
                    em = discord.Embed(
                        title="𝕿𝖍𝖊 𝕷𝖎𝖌𝖍𝖙 𝕰𝖒𝖊𝖗𝖌𝖊𝖘",
                        description=f"Drakath's forces have triumphed over Eclipse!\n{winner.mention} emerges as a true champion of anarchy!",
                        color=0xFFB900,
                    )
                    em.set_thumbnail(url="https://i.imgur.com/3pg9Msj.png")
                    em.set_image(url="https://i.imgur.com/s5tvHMd.png")
                    await send_to_channels(embed=em)

            # End of raid: disable keyword listening and cancel taunt loop.
            self.raidactive = False
            if self.taunt_task:
                self.taunt_task.cancel()

        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n" + traceback.format_exc()
            await ctx.send(error_message)
            print(error_message)

    @commands.Cog.listener()
    async def on_message(self, message):
        """Listen for keywords during an active raid and have Eclipse respond with context-sensitive taunts."""
        if not self.raidactive:
            return
        if message.channel.id not in self.raid_channel_ids:
            return
        if message.author.bot:
            return

        keyword_responses = {
            "omg": [
                "Oh, {user}, your 'omg' only pleases the void. Embrace the inevitable!",
                "Is that an 'omg', {user}? Your shock is but a prelude to your doom.",
                "Your 'omg' echoes pitifully, {user}. The abyss awaits your fall."
            ],
            "wtf": [
                "WTF indeed, {user}. Your confusion deepens your descent into darkness.",
                "I hear your 'wtf', {user}—it resounds like the wail of a doomed soul.",
                "Such bafflement, {user}! Your 'wtf' is music to the void."
            ],
            "lol": [
                "LOL, {user}? Your laughter is as futile as it is feeble.",
                "Ha! {user} laughs, but the void finds your mirth delightfully pathetic.",
                "Your 'lol' stings, {user}. It is but the whisper of your impending demise."
            ],
            "no": [
                "No, {user}? Denial only delays the inevitable, and the void will not be denied.",
                "Your 'no' is as empty as your hopes, {user}. Surrender to darkness.",
                "Refuse all you want, {user}. The void cares not for your protests."
            ],
            "ouch": [
                "Ouch, {user}? That pain is merely the first taste of despair.",
                "Every 'ouch' you utter, {user}, draws you closer to oblivion.",
                "Your cry of 'ouch' fuels the darkness, {user}—it is the sound of your downfall."
            ],
            "ugh": [
                "Ugh, {user}, your disgust is a flavor I savor in the abyss.",
                "Let that 'ugh' resound, {user}. It only heightens your impending ruin.",
                "Your exasperation is noted, {user}—and it only serves to feed the void."
            ],
            "fail": [
                "Fail already, {user}? The abyss welcomes your inadequacy.",
                "Your failure is inevitable, {user}. How deliciously predictable.",
                "Embrace your failure, {user}; it is the first step into eternal darkness."
            ],
            "damn": [
                "Damn, {user}. Even your curses cannot stave off the coming storm.",
                "Your 'damn' is like a dying echo, {user}. The void mocks your defiance.",
                "Every damn you utter brings you one step closer to your demise, {user}."
            ],
            "stupid": [
                "Stupid, {user}? Your foolishness is the void’s sweetest delight.",
                "How delightfully stupid, {user}. Your ignorance seals your fate.",
                "The void feasts on your 'stupid', {user}. Savor your impending end."
            ],
            "suck": [
                "Suck all you want, {user}; it only deepens the void’s hunger for you.",
                "Your complaints that you 'suck' confirm your inevitable doom, {user}.",
                "Every time you say you suck, {user}, the abyss grows ever more ravenous."
            ],
            "yes": [
                "Yes, {user}? Your eager agreement only hastens your fall into oblivion.",
                "Affirmative, {user}? Your compliance is noted, yet it seals your fate.",
                "Your 'yes' is a whisper in the void, {user}—a prelude to your doom."
            ],
            "yeah": [
                "Yeah, {user}? Even your casual nod is futile against the void.",
                "Your 'yeah' is as empty as your soul, {user}. The abyss awaits.",
                "Simply 'yeah'? Your indifference deepens your despair, {user}."
            ],
            "yep": [
                "Yep, {user}? That simple word echoes with your impending demise.",
                "A mere 'yep', {user}—and the void laughs at your simplicity.",
                "Your 'yep' is the sound of a falling soul, {user}."
            ],
            "sure": [
                "Sure, {user}? Your naive certainty will be your undoing.",
                "You think it's sure, {user}? The void offers no guarantees, only despair.",
                "Your 'sure' is as brittle as your hope, {user}."
            ],
            "okay": [
                "Okay, {user}? Your acceptance is the first step into eternal darkness.",
                "So you say 'okay', {user}? It tastes like surrender to the void.",
                "Your 'okay' seals your fate, {user}—there is no escape."
            ],
            "ok": [
                "Ok, {user}? That brevity is but a whisper before the storm of oblivion.",
                "A simple 'ok', {user}—it will not save you from the void.",
                "Your 'ok' is insignificant, {user}; soon, all will be lost in darkness."
            ],
            "brb": [
                "BRB, {user}? The void waits for no one; your absence is but a momentary pause in your doom.",
                "You say 'brb', {user}, but the void never rests.",
                "Even if you return, {user}, the darkness will have claimed you."
            ],
            "gtg": [
                "GTG, {user}? You cannot outrun the void. Your departure only hastens your end.",
                "Leaving so soon, {user}? The abyss will follow you, even in your absence.",
                "Your 'gtg' is futile, {user}; the void consumes all who attempt escape."
            ],
            "haha": [
                "Haha, {user}? Your laughter is as hollow as your soul.",
                "Laugh all you want, {user}, but the void finds your mirth deliciously tragic.",
                "Your 'haha' is the sound of a dying star, {user}—flickering before oblivion."
            ],
            "rofl": [
                "ROFL, {user}? Your amusement is insignificant in the grand scheme of eternal despair.",
                "Rolling on the floor, {user}? The void will soon have you flattened by your own futility.",
                "Your 'rofl' is a prelude to ruin, {user}."
            ],
            "lmao": [
                "LMAO, {user}? Even your mocking laughter cannot stave off the void's hunger.",
                "Your 'lmao' only deepens the irony of your inevitable demise, {user}.",
                "Laugh if you must, {user}; it only echoes louder in the abyss."
            ],
            "fml": [
                "FML, {user}? Fate has already marked you for oblivion.",
                "Your lament, {user}, only sweetens the void's feast.",
                "Every 'fml' is another nail in the coffin of your existence, {user}."
            ],
            "hi": [
                "Hi, {user}? Such a trivial greeting before facing eternal darkness.",
                "Greetings, {user}? The void offers no solace in your naive hello.",
                "Your 'hi' is but a fleeting sound, soon to be silenced by the abyss."
            ],
            "hello": [
                "Hello, {user}? The void hears your greeting and laughs at your insignificance.",
                "Your 'hello' is a futile attempt at connection in a realm of despair, {user}.",
                "Even as you say hello, {user}, the darkness looms ever closer."
            ],
            "bye": [
                "Bye, {user}? There is no escape from the void, not in life nor in death.",
                "Your farewell, {user}, only hastens your descent into oblivion.",
                "Goodbye is the final word, {user}; soon, all will be consumed by darkness."
            ],
            "idk": [
                "IDK, {user}? Ignorance is bliss until the void shatters your delusions.",
                "Not knowing seals your fate, {user}. The abyss awaits your enlightenment.",
                "Your 'idk' is a whisper of uncertainty—soon drowned out by despair, {user}."
            ]
        }

        message_content = message.content.lower()
        matched_responses = []
        for kw, responses in keyword_responses.items():
            if kw in message_content:
                matched_responses.extend(responses)
        if matched_responses:
            now = datetime.datetime.utcnow().timestamp()
            if now - self.last_keyword_response < 10:
                return
            self.last_keyword_response = now
            response = randomm.choice(matched_responses).format(user=message.author.mention)
            await message.channel.send(response)


async def setup(bot):
    designated_shard_id = 0  # Choose shard 0 as the primary.
    if designated_shard_id in bot.shard_ids:
        await bot.add_cog(HorrorRaid(bot))
        print(f"Raid loaded on shard {designated_shard_id}")
