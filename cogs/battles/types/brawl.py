import asyncio
import datetime
import random

import discord

from ..core.battle import Battle

BRAWL_ATTACKS = [
    "{attacker} swings a {weapon} at {defender}!",
    "{attacker} smashes {defender} with a {weapon}!",
    "{attacker} cracks the {weapon} across {defender}'s ribs!",
    "{attacker} lunges forward, {weapon} leading the charge!",
    "{attacker} whips the {weapon} around with bad intentions!",
    "{attacker} brings the {weapon} down like a hammer!",
    "{attacker} jabs the {weapon} straight into {defender}!",
    "{attacker} swings the {weapon} in a wide arc!",
]

BRAWL_MISSES = [
    "{attacker} whiffs a wild {weapon} swing!",
    "{attacker} slips on the floor and misses with the {weapon}!",
    "{attacker}'s {weapon} swing hits only air!",
    "{attacker} swings the {weapon} too wide and misses!",
]

BRAWL_FINISH = [
    "{defender} collapses under the blow!",
    "{defender} crashes to the floor!",
    "{defender} goes down hard!",
    "{defender} can't take another hit!",
]


class BrawlBattle(Battle):
    """Fast 1v1 bar brawl with HP bars and flavor text."""

    def __init__(self, ctx, teams, **kwargs):
        super().__init__(ctx, teams, **kwargs)
        self.team_a = self.teams[0]
        self.team_b = self.teams[1]
        self.turn_order = []
        self.current_turn = 0
        self.hit_chance = float(kwargs.get("hit_chance", 0.75))
        self.damage_variance = int(kwargs.get("damage_variance", 40))
        self.max_duration = kwargs.get("max_duration", datetime.timedelta(seconds=90))

    async def start_battle(self):
        self.started = True
        self.start_time = datetime.datetime.utcnow()

        self.turn_order = []
        for team in self.teams:
            for combatant in team.combatants:
                self.turn_order.append(combatant)

        random.shuffle(self.turn_order)

        await self.add_to_log(
            f"Bar brawl started between {self.team_a.combatants[0].display_name} "
            f"and {self.team_b.combatants[0].display_name}!"
        )

        embed = await self.create_battle_embed()
        self.battle_message = await self.ctx.send(embed=embed)
        await asyncio.sleep(1)
        return True

    async def process_turn(self):
        if await self.is_battle_over():
            return False

        turns_checked = 0
        max_turns = len(self.turn_order) * 2
        attacker = None

        while turns_checked < max_turns:
            current = self.turn_order[self.current_turn % len(self.turn_order)]
            self.current_turn += 1
            turns_checked += 1
            if current.is_alive():
                attacker = current
                break

        if attacker is None:
            return False

        alive_enemies = [c for c in self.turn_order if c.is_alive() and c != attacker]
        if not alive_enemies:
            return False
        defender = alive_enemies[0]

        hit_roll = random.random() < self.hit_chance
        if hit_roll:
            variance = random.randint(-self.damage_variance, self.damage_variance)
            raw_damage = max(1, float(attacker.damage) + variance)
            armor = float(defender.armor)
            damage = max(10, raw_damage - armor)
            defender.take_damage(damage)
            attack_line = random.choice(BRAWL_ATTACKS).format(
                attacker=attacker.display_name,
                defender=defender.display_name,
                weapon=getattr(attacker, "weapon_name", "weapon"),
            )
            message = f"{attack_line} **{self.format_number(damage)}** damage."
            if not defender.is_alive():
                message += f" {random.choice(BRAWL_FINISH).format(defender=defender.display_name)}"
        else:
            message = random.choice(BRAWL_MISSES).format(
                attacker=attacker.display_name,
                defender=defender.display_name,
                weapon=getattr(attacker, "weapon_name", "weapon"),
            )

        await self.add_to_log(message)
        await self.update_display()
        await asyncio.sleep(1)
        return True

    async def create_battle_embed(self):
        embed = discord.Embed(
            title="Bar Brawl",
            color=getattr(self.ctx.bot.config.game, "primary_colour", discord.Color.dark_orange()),
        )

        for team in [self.team_a, self.team_b]:
            for combatant in team.combatants:
                current_hp = max(0, float(combatant.hp))
                max_hp = float(combatant.max_hp)
                hp_bar = self.create_hp_bar(current_hp, max_hp)
                weapon = getattr(combatant, "weapon_name", "weapon")
                field_value = (
                    f"Weapon: **{weapon}**\n"
                    f"Armor: **{int(float(combatant.armor))}**\n"
                    f"HP: {current_hp:.0f}/{max_hp:.0f}\n{hp_bar}"
                )
                embed.add_field(name=combatant.display_name, value=field_value, inline=False)

        log_text = "\n\n".join([f"**Action #{i}**\n{msg}" for i, msg in self.log])
        embed.add_field(name="Battle Log", value=log_text or "Brawl starting...", inline=False)
        embed.set_footer(text=f"Battle ID: {self.battle_id}")
        return embed

    async def update_display(self):
        embed = await self.create_battle_embed()
        if self.battle_message:
            await self.battle_message.edit(embed=embed)
        else:
            self.battle_message = await self.ctx.send(embed=embed)

    async def end_battle(self):
        self.finished = True

        alive_a = [c for c in self.team_a.combatants if c.is_alive()]
        alive_b = [c for c in self.team_b.combatants if c.is_alive()]

        if alive_a and not alive_b:
            winner = self.team_a.combatants[0].user
            loser = self.team_b.combatants[0].user
        elif alive_b and not alive_a:
            winner = self.team_b.combatants[0].user
            loser = self.team_a.combatants[0].user
        else:
            # Timeout or tie: decide by remaining HP
            a_hp = sum(float(c.hp) for c in self.team_a.combatants)
            b_hp = sum(float(c.hp) for c in self.team_b.combatants)
            if a_hp == b_hp:
                winner = random.choice([self.team_a.combatants[0].user, self.team_b.combatants[0].user])
            else:
                winner = self.team_a.combatants[0].user if a_hp > b_hp else self.team_b.combatants[0].user
            loser = self.team_b.combatants[0].user if winner == self.team_a.combatants[0].user else self.team_a.combatants[0].user

        self.winner = winner
        return winner, loser

    async def is_battle_over(self):
        if self.finished or await self.is_timed_out():
            return True
        if self.team_a.is_defeated() or self.team_b.is_defeated():
            return True
        return False
