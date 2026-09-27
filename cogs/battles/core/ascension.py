"""Trial ascension kits shared by every mantle-enabled battle mode.

All timers count the affected combatant's own turns, never global log actions.
Secondary damage cannot trigger another ascension attack.
"""
from decimal import Decimal
import random

from classes.ascension import get_ascension_mantle


class AscensionCombat:
    def format_ascension_resource_status(self, combatant):
        lines = []
        ward = getattr(combatant, "ascension_ward", 0)
        radiance = getattr(combatant, "ascension_radiance", 0)
        if ward > 0 or radiance > 0:
            lines.append(f"👑 Ward: {self.format_number(ward)} · Radiance: {self.format_number(radiance)}")
        marks = getattr(combatant, "ascension_doom", {})
        if marks:
            lines.append("☠️ Doom: " + ", ".join(f"{mark['stacks']}/5" for mark in marks.values()))
        mantle = self._get_active_ascension_mantle(combatant)
        if mantle and mantle.key == "cyclebreaker":
            turn = getattr(combatant, "ascension_turn", 0)
            phase = "Surge next" if turn % 2 == 0 else "Recovery next"
            echo = getattr(combatant, "ascension_echo", None)
            echo_state = "Echo alive" if echo is not None and echo.is_alive() else "Echo lost"
            lines.append(f"🌀 {phase} · {echo_state}")
        return "\n".join(lines)

    def _get_active_ascension_mantle(self, combatant):
        if (combatant is None or getattr(combatant, "is_pet", False)
                or getattr(combatant, "is_summoned", False)
                or not getattr(combatant, "ascension_enabled", True)):
            return None
        return get_ascension_mantle(getattr(combatant, "ascension_mantle", None))

    def _refresh_radiant_wards(self, team, ratio):
        for ally in team.combatants:
            if not ally.is_alive() or getattr(ally, "is_summoned", False):
                continue
            # Shared cap: multiple Elysia ascendants refresh, never stack wards.
            ally.ascension_radiance = min(
                ally.max_hp * Decimal("0.10"),
                getattr(ally, "ascension_radiance", Decimal("0"))
                + getattr(ally, "ascension_absorbed", Decimal("0")) * Decimal("0.50"),
            )
            ally.ascension_absorbed = Decimal("0")
            ally.ascension_ward = max(
                getattr(ally, "ascension_ward", Decimal("0")), ally.max_hp * ratio
            )
            ally.ascension_ward_turns = 3

    async def trigger_ascension_openings(self):
        from .combatant import Combatant

        messages = []
        for team in self.teams:
            for combatant in list(team.combatants):
                combatant.battle = self
                mantle = self._get_active_ascension_mantle(combatant)
                if (not combatant.is_alive() or mantle is None
                        or getattr(combatant, "ascension_opening_used", False)):
                    continue
                combatant.ascension_opening_used = True
                if mantle.key == "thronekeeper":
                    self._refresh_radiant_wards(team, Decimal("0.15"))
                    messages.append(
                        f"👑 **Radiant Covenant:** {combatant.name} grants the party a 15% HP ward. "
                        "Absorbed damage becomes Radiance; a smaller ward renews every three turns."
                    )
                elif mantle.key == "cyclebreaker":
                    echo = Combatant(
                        user=f"Paradox Echo of {combatant.name}",
                        hp=combatant.max_hp * Decimal("0.25"),
                        max_hp=combatant.max_hp * Decimal("0.25"),
                        damage=0, armor=combatant.armor * Decimal("0.50"),
                        element=combatant.element, is_summoned=True,
                        is_ascension_echo=True, ascension_owner=combatant,
                    )
                    echo.battle = self
                    self.register_summoned_combatant(echo, team=team, summoner=combatant)
                    team.combatants.append(echo)
                    combatant.ascension_echo = echo
                    messages.append(
                        f"🌀 **Paradox Echo:** {combatant.name}'s targetable echo joins the battle. "
                        "Chaos Surge is ready for their first turn, followed by a recovery turn."
                    )
                else:
                    messages.append(
                        f"☠️ **Doom:** {combatant.name}'s attacks build Doom. "
                        "At three stacks, enemies below 25% HP become vulnerable to Reap."
                    )
        return messages

    def consume_ascension_action_lock(self, combatant):
        # Kept as a compatibility hook; the old opening silence is retired.
        return None

    async def begin_ascension_turn(self, combatant):
        """Advance personal timers and resolve Doom before this actor can act."""
        combatant.ascension_turn = getattr(combatant, "ascension_turn", 0) + 1
        for message in self._drain_ascension_messages(combatant):
            await self.add_to_log(message)

        # Echoes have no independent action, so their debuff timers follow their
        # owner's turn. Poisoning an echo can still destroy the owner's lifeline.
        echo = getattr(combatant, "ascension_echo", None)
        if echo is not None and echo.is_alive():
            await self.begin_ascension_turn(echo)

        marks = getattr(combatant, "ascension_doom", {})
        for source, mark in list(marks.items()):
            mantle = self._get_active_ascension_mantle(source)
            if not source.is_alive() or mantle is None or mantle.key != "grave_sovereign":
                marks.pop(source, None)
                continue
            if not combatant.is_alive():
                break
            damage = self.apply_damage(source, combatant, mark["power"] * mark["stacks"])
            await self.add_to_log(
                f"☠️ **Doom ({mark['stacks']}):** {combatant.name} loses "
                f"**{self.format_number(damage)} HP**."
            )
            if not combatant.is_alive():
                source.ascension_doom_pending_carry = (combatant, mark["stacks"] // 2)
            mark["turns"] -= 1
            if mark["turns"] <= 0 or not combatant.is_alive():
                marks.pop(source, None)
        for message in self._drain_ascension_messages(combatant):
            await self.add_to_log(message)
        if not combatant.is_alive():
            guardian_message = self.maybe_trigger_guardian_angel(combatant)
            if guardian_message:
                await self.add_to_log(guardian_message)
            elif (self.config.get("class_buffs", True) and self.config.get("cheat_death", True)
                  and not combatant.is_pet and not combatant.has_cheated_death):
                if random.randint(1, 100) <= combatant.death_cheat_chance:
                    combatant.hp = self.get_cheat_death_recovery_hp(combatant)
                    combatant.has_cheated_death = True
                    await self.add_to_log(f"{combatant.name} cheats death against Doom!")
            if not combatant.is_alive():
                if combatant.is_pet:
                    for message in self.process_pet_death_effects(combatant):
                        await self.add_to_log(message)
                return False

        ward_turns = max(0, getattr(combatant, "ascension_ward_turns", 0) - 1)
        combatant.ascension_ward_turns = ward_turns
        if ward_turns == 0:
            combatant.release_ascension_radiance()
        mantle = self._get_active_ascension_mantle(combatant)
        if mantle and mantle.key == "thronekeeper" and combatant.ascension_turn % 3 == 0:
            team = self.get_team_for_combatant(combatant)
            if team:
                self._refresh_radiant_wards(team, Decimal("0.08"))
                await self.add_to_log(f"👑 **Radiant Covenant:** {combatant.name} renews the party's 8% HP wards.")
        if mantle and mantle.key == "cyclebreaker":
            combatant.ascension_surge = combatant.ascension_turn % 2 == 1
            phase = "Chaos Surge: +30% attack damage this turn" if combatant.ascension_surge else "Recovery: no surge bonus; Chaos Surge returns next turn"
            await self.add_to_log(f"🌀 **{combatant.name}:** {phase}.")
        return True

    async def resolve_ascension_attack(self, attacker, target, attack_damage):
        """Once per successful action, after the primary attack (including fireballs)."""
        if attacker is None or target is None:
            return None
        turn = getattr(attacker, "ascension_turn", 0)
        if getattr(attacker, "ascension_last_proc_turn", -1) == turn:
            return None
        attacker.ascension_last_proc_turn = turn
        messages = self._drain_ascension_messages(attacker, target)
        if not attacker.is_alive():
            return "\n".join(messages) or None
        attack_damage = max(Decimal("0"), Decimal(str(attack_damage)))
        radiance = getattr(attacker, "ascension_radiance", Decimal("0"))
        if target.is_alive() and radiance > 0 and attack_damage > 0:
            attacker.ascension_radiance = Decimal("0")
            dealt = self.apply_damage(attacker, target, radiance)
            messages.append(f"✨ **Radiance:** {attacker.name} retaliates for **{self.format_number(dealt)} HP**.")

        mantle = self._get_active_ascension_mantle(attacker)
        if mantle and mantle.key == "cyclebreaker" and attack_damage > 0:
            # Scale echoes from the resolved hit, avoiding a second armor subtraction.
            if target.is_alive() and getattr(attacker, "ascension_surge", False):
                dealt = self.apply_damage(attacker, target, attack_damage * Decimal("0.30"))
                messages.append(f"🌀 **Chaos Surge:** **{self.format_number(dealt)} HP** bonus damage.")
            echo = getattr(attacker, "ascension_echo", None)
            if target.is_alive() and echo is not None and echo.is_alive():
                dealt = self.apply_damage(attacker, target, attack_damage * Decimal("0.20"))
                messages.append(f"🌀 **Paradox Echo:** mirrors the strike for **{self.format_number(dealt)} HP**.")
        elif mantle and mantle.key == "grave_sovereign" and attack_damage > 0:
            # Resolve this on the next attack, after the previous victim's pet/class
            # death saves have run. A revived target must not grant kill rewards.
            pending = getattr(attacker, "ascension_doom_pending_carry", None)
            if pending is not None:
                previous_target, carried_stacks = pending
                if not previous_target.is_alive():
                    attacker.ascension_doom_carry = max(
                        getattr(attacker, "ascension_doom_carry", 0), carried_stacks
                    )
                attacker.ascension_doom_pending_carry = None
            marks = getattr(target, "ascension_doom", None)
            if marks is None:
                marks = target.ascension_doom = {}
            mark = marks.get(attacker)
            if not target.is_alive():
                if mark:
                    attacker.ascension_doom_pending_carry = (target, mark["stacks"] // 2)
                    marks.pop(attacker, None)
            else:
                carry = getattr(attacker, "ascension_doom_carry", 0)
                attacker.ascension_doom_carry = 0
                stacks = min(5, (mark["stacks"] if mark else 0) + 1 + carry)
                power = min(max(Decimal("0"), attacker.damage) * Decimal("0.06"), target.max_hp * Decimal("0.015"))
                marks[attacker] = {"stacks": stacks, "power": power, "turns": 3}
                messages.append(f"☠️ **Doom:** {target.name} bears **{stacks}/5** stacks.")
                if stacks >= 3 and target.hp <= target.max_hp * Decimal("0.25"):
                    marks.pop(attacker)
                    burst = min(power * stacks * 4, target.max_hp * Decimal("0.10"))
                    dealt = self.apply_damage(attacker, target, burst)
                    messages.append(f"☠️ **Reap:** {attacker.name} consumes Doom for **{self.format_number(dealt)} HP**.")
                    if not target.is_alive():
                        attacker.ascension_doom_pending_carry = (target, stacks // 2)
        messages.extend(self._drain_ascension_messages(attacker, target))
        return "\n".join(messages) or None

    def try_ascension_death_save(self, target):
        """Synchronous lethal-hit hook: also covers reflection, DoTs and splash."""
        mantle = self._get_active_ascension_mantle(target)
        echo = getattr(target, "ascension_echo", None)
        if (mantle is None or mantle.key != "cyclebreaker" or target.is_alive()
                or getattr(target, "ascension_survival_used", False)
                or echo is None or not echo.is_alive()):
            return False
        target.ascension_survival_used = True
        echo.hp = Decimal("0")
        target.hp = target.max_hp * Decimal("0.30")
        target.pending_ascension_messages = [
            f"🌀 **I Reject This Timeline:** {target.name} sacrifices their Paradox Echo "
            f"and returns with **{self.format_number(target.hp)} HP**. The echo is gone for this battle."
        ]
        return True

    @staticmethod
    def _drain_ascension_messages(*combatants):
        messages = []
        for combatant in combatants:
            messages.extend(getattr(combatant, "pending_ascension_messages", []))
            combatant.pending_ascension_messages = []
        return messages

    async def maybe_trigger_cyclebreaker(self, target, attacker):
        self.try_ascension_death_save(target)
        return "\n".join(self._drain_ascension_messages(target)) or None
