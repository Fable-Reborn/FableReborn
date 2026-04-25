import asyncio
import datetime
import random
from decimal import Decimal

import discord

from ..core.battle import Battle
from .raid import RaidBattle


class CityWarBattle(Battle):
    """City-war battle flow with fortification and guard phases."""

    def __init__(self, ctx, teams, **kwargs):
        super().__init__(ctx, teams, **kwargs)
        self.city = kwargs.get("city", "Unknown")
        self.attacking_guild_name = kwargs.get("attacking_guild_name", "Attackers")
        self.defending_guild_name = kwargs.get("defending_guild_name", "Defenders")
        self.turn_delay = float(kwargs.get("turn_delay", 2.0))
        self.attacker_team = self.teams[0]
        self.defender_team = self.teams[1]
        self.team_a = self.attacker_team
        self.team_b = self.defender_team
        self.current_turn = 0
        self.turn_order = []
        self.guard_phase_started = False
        self.had_structures = any(
            getattr(combatant, "city_role", "") == "structure"
            for combatant in self.defender_team.combatants
        )
        self.round_number = 0
        self.result = {
            "attackers_won": False,
            "attackers_remaining": 0,
            "structures_remaining": 0,
            "guards_remaining": 0,
        }
        self.config["allow_pets"] = kwargs.get("allow_pets", True)
        self.config["pets_continue_battle"] = True

    def serialize_battle_data(self):
        data = super().serialize_battle_data()
        data.update(
            {
                "city": self.city,
                "attacking_guild_name": self.attacking_guild_name,
                "defending_guild_name": self.defending_guild_name,
                "round_number": self.round_number,
            }
        )
        return data

    def _get_alive_structures(self):
        return [
            combatant
            for combatant in self.defender_team.get_alive_combatants()
            if getattr(combatant, "city_role", "") == "structure"
        ]

    def _get_alive_city_defenders(self):
        return [
            combatant
            for combatant in self.defender_team.get_alive_combatants()
            if getattr(combatant, "city_role", "") != "structure"
        ]

    def _get_phase_name(self):
        return "Fortifications" if self._get_alive_structures() else "Defenders"

    def _pick_structure_target(self):
        structures = self._get_alive_structures()
        if not structures:
            return None
        return sorted(structures, key=lambda combatant: float(combatant.hp))[-1]

    def _pick_primary_defender_target(self):
        defenders = self._get_alive_city_defenders()
        if not defenders:
            return None
        return sorted(
            defenders,
            key=lambda combatant: (
                float(combatant.damage),
                float(combatant.armor),
                float(combatant.hp),
            ),
        )[-1]

    def _pick_primary_attacker_target(self):
        attackers = self.attacker_team.get_alive_combatants()
        if not attackers:
            return None
        if len({float(combatant.hp) for combatant in attackers}) == 1:
            return sorted(attackers, key=lambda combatant: float(combatant.damage))[-1]
        return sorted(attackers, key=lambda combatant: float(combatant.hp))[0]

    def _sum_damage(self, combatants):
        total = Decimal("0")
        for combatant in combatants:
            if combatant.is_alive():
                total += Decimal(str(combatant.damage))
        return total

    def _get_structure_assault_modifier(self):
        modifier = Decimal("1.0")
        for structure in self._get_alive_structures():
            structure_name = str(getattr(structure, "city_structure_name", "")).lower()
            if structure_name == "outer wall":
                return Decimal("0.80")
            if structure_name == "inner wall":
                modifier = min(modifier, Decimal("0.90"))
        return modifier

    def _calculate_structure_retaliation(self, structures, target):
        base_damage = self._sum_damage(structures)
        hp_pressure = Decimal(str(getattr(target, "max_hp", 0) or 0)) * Decimal("0.03")
        armor_reduction = Decimal(str(getattr(target, "armor", 0) or 0)) * Decimal("0.25")
        return max(Decimal("1"), base_damage + hp_pressure - armor_reduction)

    async def _start_guard_phase(self):
        if self.guard_phase_started:
            return

        self.guard_phase_started = True
        self.current_turn = 0
        self.turn_order = (
            list(self.attacker_team.get_alive_combatants())
            + list(self._get_alive_city_defenders())
        )
        random.shuffle(self.turn_order)
        self.turn_order = self.prioritize_turn_order(self.turn_order)

        if self.had_structures:
            await self.add_to_log(
                f"The fortifications of {self.city} fall. "
                f"{self.defending_guild_name}'s guards move in to meet the attackers."
            )
        else:
            await self.add_to_log(
                f"The defenders of {self.city} rush forward to meet the attackers."
            )

    async def start_battle(self):
        self.started = True
        self.start_time = datetime.datetime.utcnow()
        await self.save_battle_to_database()

        opening_message = (
            f"City War: {self.attacking_guild_name} begins the assault on "
            f"{self.city} against {self.defending_guild_name}."
        )
        await self.add_to_log(opening_message)
        embed = await self.create_battle_embed()
        self.battle_message = await self.publish_battle_message(embed=embed)
        return True

    async def process_turn(self):
        if await self.is_battle_over():
            return False

        self.round_number += 1
        if self._get_alive_structures():
            await self._process_structure_round()
            await self.update_display()
            await asyncio.sleep(self.turn_delay)
            return True

        await self._start_guard_phase()
        return await RaidBattle.process_turn(self)

    async def _process_structure_round(self):
        attackers = self.attacker_team.get_alive_combatants()
        structures = self._get_alive_structures()
        target = self._pick_structure_target()
        if not attackers or not structures or target is None:
            return

        outgoing_damage = max(
            Decimal("1"),
            self._sum_damage(attackers) * self._get_structure_assault_modifier(),
        )
        actual_damage = self.apply_damage(None, target, outgoing_damage)
        target_hp = max(Decimal("0"), target.hp)
        if target.is_alive():
            await self.add_to_log(
                f"{self.attacking_guild_name} hits {target.name} in {self.city} for "
                f"**{self.format_number(actual_damage)} HP**. "
                f"({self.format_number(target_hp)} HP left)"
            )
        else:
            await self.add_to_log(
                f"{self.attacking_guild_name} destroys {target.name} in {self.city}."
            )

        if not self.attacker_team.get_alive_combatants():
            return

        attacker_target = self._pick_primary_attacker_target()
        if attacker_target is None:
            return

        retaliation = self._calculate_structure_retaliation(
            structures,
            attacker_target,
        )
        actual_damage = self.apply_damage(None, attacker_target, retaliation)
        target_hp = max(Decimal("0"), attacker_target.hp)
        if attacker_target.is_alive():
            await self.add_to_log(
                f"{attacker_target.name} is hit by the fortifications in {self.city} for "
                f"**{self.format_number(actual_damage)} HP**. "
                f"({self.format_number(target_hp)} HP left)"
            )
        else:
            await self.add_to_log(
                f"{attacker_target.name} is defeated by the fortifications in {self.city}."
            )

    async def _process_guard_round(self):
        return await RaidBattle.process_turn(self)

    async def create_battle_embed(self):
        embed = discord.Embed(
            title=f"City War: {self.city}",
            colour=self.ctx.bot.config.game.primary_colour,
            description=(
                f"Phase: **{self._get_phase_name()}**\n"
                f"Attackers: **{self.attacking_guild_name}**\n"
                f"Defenders: **{self.defending_guild_name}**"
            ),
        )

        for team_name, team in (
            ("Attackers", self.attacker_team),
            ("Defenders", self.defender_team),
        ):
            lines = []
            for combatant in team.combatants:
                current_hp = max(0, float(combatant.hp))
                max_hp = max(1.0, float(combatant.max_hp))
                hp_bar_length = 10 if self.config.get("emoji_hp_bars", True) else 20
                hp_bar = self.create_hp_bar(
                    current_hp,
                    max_hp,
                    length=hp_bar_length,
                    combatant=combatant,
                )
                role = getattr(combatant, "city_role", "")
                if combatant.is_pet:
                    role_text = "pet"
                elif role == "structure":
                    role_text = "structure"
                elif role == "guard":
                    role_text = "guard"
                else:
                    role_text = "fighter"
                status = "alive" if combatant.is_alive() else "defeated"
                lines.append(
                    f"**{combatant.name}** ({role_text})\n"
                    f"HP: {current_hp:.1f}/{max_hp:.1f} [{status}]\n{hp_bar}"
                )
            embed.add_field(
                name=team_name,
                value="\n\n".join(lines) if lines else "None",
                inline=False,
            )

        log_text = self.format_battle_log_field()
        embed.add_field(name="Battle Log", value=log_text, inline=False)
        embed.set_footer(text=f"Battle ID: {self.battle_id}")
        return embed

    async def update_display(self):
        embed = await self.create_battle_embed()
        await self.publish_battle_message(embed=embed)

    async def end_battle(self):
        self.finished = True

        attackers_remaining = len(self.attacker_team.get_alive_combatants())
        structures_remaining = len(self._get_alive_structures())
        guards_remaining = len(self._get_alive_city_defenders())
        attackers_won = (
            attackers_remaining > 0
            and structures_remaining == 0
            and guards_remaining == 0
        )

        self.result = {
            "attackers_won": attackers_won,
            "attackers_remaining": attackers_remaining,
            "structures_remaining": structures_remaining,
            "guards_remaining": guards_remaining,
        }
        self.winner = "Attackers" if attackers_won else "Defenders"
        await self.save_battle_to_database()
        return self.result

    async def is_battle_over(self):
        return (
            not self.attacker_team.get_alive_combatants()
            or (
                not self._get_alive_structures()
                and not self._get_alive_city_defenders()
            )
            or await self.is_timed_out()
            or self.finished
        )
