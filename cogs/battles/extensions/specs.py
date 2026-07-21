"""
Class-specialization effect resolution for modern battles.

Combatants carry a `spec_effects` dict (attached by the factory from
`Specializations.get_user_spec_effects`). Creation-time effects
(lifesteal_pct, reflect_pct, pet_stat_pct) are folded into base stats by the
factory; this module resolves the runtime hooks.

Every method is a safe no-op for combatants without specs, so battle types
can call the hooks unconditionally. Design doc: docs/class_specializations.md
"""
import random
from decimal import Decimal


class SpecExtension:
    @staticmethod
    def effects_of(combatant):
        if combatant is None or getattr(combatant, "is_pet", False):
            return {}
        return getattr(combatant, "spec_effects", None) or {}

    @staticmethod
    def _pct(fx):
        return Decimal(str(fx["value"])) / Decimal("100")

    @staticmethod
    def _format_pct(value):
        value = Decimal(str(value))
        if value == value.to_integral_value():
            return str(int(value))
        return f"{value:.1f}"

    @staticmethod
    def _same_user(left, right):
        left_user = getattr(left, "user", left)
        right_user = getattr(right, "user", right)
        left_id = getattr(left_user, "id", None)
        right_id = getattr(right_user, "id", None)
        return left_id is not None and left_id == right_id

    def _linked_owner_for_pet(self, pet, team):
        if not getattr(pet, "is_pet", False) or team is None:
            return None
        owner = getattr(pet, "owner", None)
        for member in getattr(team, "combatants", []):
            if member is pet or getattr(member, "is_pet", False):
                continue
            if owner is member or self._same_user(member, owner):
                return member
        return None

    def _linked_pets_for_owner(self, owner, team):
        if owner is None or team is None:
            return []
        pets = []
        for member in getattr(team, "combatants", []):
            if not getattr(member, "is_pet", False):
                continue
            pet_owner = getattr(member, "owner", None)
            if pet_owner is owner or self._same_user(owner, pet_owner):
                pets.append(member)
        return pets

    @staticmethod
    def _heal_then_shield(target, amount):
        amount = Decimal(str(amount or 0))
        if target is None or amount <= 0 or not getattr(target, "is_alive", lambda: False)():
            return Decimal("0"), Decimal("0")
        missing = max(Decimal("0"), Decimal(str(target.max_hp)) - Decimal(str(target.hp)))
        healed = min(missing, amount)
        if healed > 0:
            target.heal(healed)
        shield = amount - healed
        if shield > 0:
            target.shield = Decimal(str(getattr(target, "shield", 0) or 0)) + shield
        return healed, shield

    def _find_soulkeeper(self, defender, defender_team):
        fx = self.effects_of(defender).get("soulkeeper_store_pct")
        if fx:
            return defender, fx
        owner = self._linked_owner_for_pet(defender, defender_team)
        if owner is not None:
            fx = self.effects_of(owner).get("soulkeeper_store_pct")
            if fx:
                return owner, fx
        return None, None

    def _bank_soulkeeper(self, defender, damage, defender_team):
        owner, fx = self._find_soulkeeper(defender, defender_team)
        if owner is None or not fx or damage <= 0:
            return []

        max_hp = Decimal(str(getattr(owner, "max_hp", 0) or 0))
        if max_hp <= 0:
            return []

        release_pct = Decimal(str(fx.get("release_pct", 20))) / Decimal("100")
        release_at = max_hp * release_pct
        if release_at <= 0:
            return []

        stored = Decimal(str(getattr(owner, "spec_soulkeeper_reservoir", 0) or 0))
        stored += Decimal(str(damage)) * self._pct(fx)
        if stored < release_at:
            owner.spec_soulkeeper_reservoir = stored
            return []

        owner.spec_soulkeeper_reservoir = Decimal("0")
        release_amount = release_at
        targets = [owner] + self._linked_pets_for_owner(owner, defender_team)
        for target in targets:
            self._heal_then_shield(target, release_amount)

        return [
            f"🕯️ **{owner.name}** releases Sacred Offering, restoring and shielding the bond!"
        ]

    def modify_outgoing_damage(self, attacker, defender, damage, *, include_overload=True):
        """Hook A — attacker-side bonuses, applied to pre-armor damage.

        May set one-hit flags on the defender (Deadeye). Returns (damage, messages).
        """
        damage = Decimal(str(damage))
        messages = []
        effects = self.effects_of(attacker)
        if not effects:
            return damage, messages

        # Overload (Arcane Surge): each spell hit ramps damage, then builds a
        # charge. The Fireball spends the charges — see consume_overload_fireball.
        fx = effects.get("arcane_ramp_pct") if include_overload else None
        if fx:
            max_stacks = int(fx.get("max_stacks", 5))
            stacks = int(getattr(attacker, "spec_arcane_stacks", 0) or 0)
            if stacks > 0:
                damage *= Decimal("1") + (
                    Decimal(str(fx["value"])) * Decimal(str(stacks)) / Decimal("100")
                )
            if stacks < max_stacks:
                stacks += 1
                attacker.spec_arcane_stacks = stacks
                if stacks == max_stacks:
                    messages.append(
                        f"⚡ **{attacker.name}** is fully Overloaded — Fireball primed!"
                    )

        fx = effects.get("unbroken_will_pct")
        unbroken_hits = int(getattr(attacker, "spec_unbroken_damage_hits", 0) or 0)
        if fx and unbroken_hits > 0:
            damage *= Decimal("1") + self._pct(fx)
            attacker.spec_unbroken_damage_hits = unbroken_hits - 1
            messages.append(f"🛡️ **{attacker.name}** fights with Unbroken Will!")

        fx = effects.get("first_strike_bonus_pct")
        if fx and not getattr(attacker, "spec_first_strike_used", False):
            attacker.spec_first_strike_used = True
            damage *= Decimal("1") + self._pct(fx)
            messages.append(f"🗡️ **{attacker.name}** strikes from the shadows — Ambush!")

        fx = effects.get("proc_bonus_damage_pct")
        if fx and random.random() < fx.get("chance", 0.20):
            damage *= Decimal("1") + self._pct(fx)
            messages.append(f"⚔️ **{attacker.name}**'s Onslaught surges!")

        if defender is not None and getattr(defender, "max_hp", 0) > 0:
            hp_ratio = Decimal(str(defender.hp)) / Decimal(str(defender.max_hp))

            fx = effects.get("high_hp_bonus_pct")
            if fx and hp_ratio >= Decimal(str(fx.get("threshold", 0.70))):
                damage *= Decimal("1") + self._pct(fx)
                messages.append(f"⚖️ **{attacker.name}** passes Judgement on the unbowed!")

            fx = effects.get("execute_bonus_pct")
            if fx and hp_ratio <= Decimal(str(fx.get("threshold", 0.25))):
                damage *= Decimal("1") + self._pct(fx)
                messages.append(f"☠️ **{attacker.name}** moves in for the Execution!")

        fx = effects.get("boss_damage_pct")
        if fx and getattr(defender, "is_boss", False):
            damage *= Decimal("1") + self._pct(fx)
            messages.append(f"🐉 **{attacker.name}**'s Slayer instincts ignite!")

        fx = effects.get("perfect_form_pct")
        if fx and defender is not None:
            value = Decimal(str(fx["value"]))
            bonus = value / Decimal("100")
            max_hp = Decimal(str(getattr(defender, "max_hp", 0) or 0))
            hp_ratio = (
                Decimal(str(getattr(defender, "hp", 0) or 0)) / max_hp
                if max_hp > 0
                else Decimal("1")
            )
            armor = Decimal(str(getattr(defender, "armor", 0) or 0))
            threshold = Decimal(str(fx.get("threshold", 0.25)))
            if hp_ratio <= threshold:
                execute_value = Decimal(str(fx.get("execute_value", value + Decimal(str(fx.get("execute_bonus", 6))))))
                damage *= Decimal("1") + execute_value / Decimal("100")
                messages.append(f"✨ **{attacker.name}** assumes Perfect Form — execution stance!")
            elif getattr(defender, "is_boss", False):
                damage *= Decimal("1") + bonus
                messages.append(f"✨ **{attacker.name}** assumes Perfect Form — boss stance!")
            elif armor > 0:
                damage += armor * bonus
                messages.append(f"✨ **{attacker.name}** assumes Perfect Form — armor-break stance!")
            else:
                damage *= Decimal("1") + (bonus / Decimal("2"))
                messages.append(f"✨ **{attacker.name}** assumes Perfect Form!")

        fx = effects.get("debuffed_bonus_pct")
        if fx and getattr(defender, "status_effects", None):
            damage *= Decimal("1") + self._pct(fx)
            messages.append(f"😈 **{attacker.name}** checks the Naughty List — extra punishment!")

        fx = effects.get("armor_ignore_chance_pct")
        if fx and defender is not None and random.random() < float(fx["value"]) / 100:
            # The engine's canonical damage path consumes this one-hit flag
            defender.ignore_armor_this_hit = True
            messages.append(f"🎯 **{attacker.name}**'s Deadeye finds a gap in the armor!")

        fx = effects.get("stacking_debuff_pct")
        if fx and defender is not None:
            stacks = int(getattr(defender, "spec_torment_stacks", 0) or 0)
            max_stacks = int(fx.get("max_stacks", 5))
            if stacks < max_stacks:
                stacks += 1
                defender.spec_torment_stacks = stacks
                defender.spec_torment_value = fx["value"]
                if stacks == 1 or stacks == max_stacks:
                    messages.append(
                        f"🕸️ **{defender.name}** is afflicted as Torment takes hold ({stacks}/{max_stacks})!"
                    )

        return damage, messages

    def consume_overload_fireball(self, attacker, damage):
        """Overload detonation — spend all Arcane charges for a burst, then reset.

        Called from the Fireball branch (which bypasses hook A). Safe no-op for
        non-Overload combatants and when no charge is banked. Returns
        (damage, messages).
        """
        damage = Decimal(str(damage))
        fx = self.effects_of(attacker).get("arcane_ramp_pct")
        if not fx:
            return damage, []
        stacks = int(getattr(attacker, "spec_arcane_stacks", 0) or 0)
        if stacks <= 0:
            return damage, []
        per_stack = Decimal(str(fx.get("detonate_per_stack", 20)))
        bonus = per_stack * Decimal(str(stacks)) / Decimal("100")
        damage *= Decimal("1") + bonus
        attacker.spec_arcane_stacks = 0
        return damage, [
            f"⚡ **{attacker.name}** unleashes an **Overloaded Fireball** — "
            f"{stacks} charge{'s' if stacks != 1 else ''} detonate for "
            f"**+{int(bonus * 100)}%**!"
        ]

    def modify_incoming_damage(self, attacker, defender, damage, defender_team=None):
        """Hook B — defender-side avoidance and mitigation. Returns (damage, messages)."""
        damage = Decimal(str(damage))
        messages = []
        effects = self.effects_of(defender)

        torment_stacks = int(getattr(defender, "spec_torment_stacks", 0) or 0)
        torment_value = Decimal(str(getattr(defender, "spec_torment_value", 0) or 0))
        if torment_stacks > 0 and torment_value > 0:
            damage *= Decimal("1") + (Decimal(str(torment_stacks)) * torment_value / Decimal("100"))

        fx = effects.get("dodge_pct")
        if fx and random.random() < float(fx["value"]) / 100:
            messages.append(f"💨 **{defender.name}** vanishes in a Smoke Step — dodged!")
            return Decimal("0"), messages

        fx = effects.get("foresight_chance_pct")
        if fx and random.random() < float(fx["value"]) / 100:
            damage /= 2
            messages.append(f"👁️ **{defender.name}** foresaw the blow — damage halved!")

        fx = effects.get("damage_taken_reduction_pct")
        if fx:
            damage *= Decimal("1") - self._pct(fx)

        # Sanctuary: the strongest ally instance protects everyone else on the
        # team (never the Lightwarden themselves; instances don't stack)
        if defender_team is not None:
            best = Decimal("0")
            for ally in getattr(defender_team, "combatants", []):
                if ally is defender or not ally.is_alive():
                    continue
                ally_fx = self.effects_of(ally).get("party_damage_reduction_pct")
                if ally_fx:
                    best = max(best, Decimal(str(ally_fx["value"])))
            if best > 0:
                damage *= Decimal("1") - best / Decimal("100")

        fx = effects.get("unbroken_will_pct")
        if (
            fx
            and not getattr(defender, "spec_unbroken_used", False)
            and getattr(defender, "max_hp", 0) > 0
        ):
            max_hp = Decimal(str(defender.max_hp))
            projected_hp = Decimal(str(defender.hp)) - damage
            projected_ratio = projected_hp / max_hp
            if projected_ratio < Decimal(str(fx.get("threshold", 0.40))):
                defender.spec_unbroken_used = True
                shield_pct = Decimal(str(fx.get("shield_value", Decimal(str(fx["value"])) + Decimal(str(fx.get("shield_bonus", 4))))))
                shield_gain = max_hp * shield_pct / Decimal("100")
                defender.shield = Decimal(str(getattr(defender, "shield", 0) or 0)) + shield_gain
                defender.spec_unbroken_damage_hits = int(fx.get("duration", 3))
                messages.append(
                    f"🛡️ **{defender.name}**'s Unbroken Will forms a "
                    f"{self._format_pct(shield_pct)}% max HP shield!"
                )

        messages.extend(self._bank_soulkeeper(defender, damage, defender_team))

        return max(Decimal("0"), damage), messages

    def battle_start_shields(self, team):
        """Hook C — Aegis: strongest instance shields the whole team once."""
        best = None
        for member in getattr(team, "combatants", []):
            fx = self.effects_of(member).get("start_shield_pct")
            if fx and (best is None or fx["value"] > best[1]["value"]):
                best = (member, fx)
        if not best:
            return []
        owner, fx = best
        for member in team.combatants:
            shield_gain = Decimal(str(member.max_hp)) * self._pct(fx)
            member.shield = Decimal(str(getattr(member, "shield", 0) or 0)) + shield_gain
        return [f"🛡️ **{owner.name}**'s Aegis blankets the party in a protective barrier!"]

    def battle_start_effects(self, team):
        """Hook C — strongest party-wide opening effects."""
        messages = list(self.battle_start_shields(team))
        best_damage = None
        for member in getattr(team, "combatants", []):
            fx = self.effects_of(member).get("party_damage_pct")
            if fx and (best_damage is None or fx["value"] > best_damage[1]["value"]):
                best_damage = (member, fx)
        if best_damage:
            owner, fx = best_damage
            multiplier = Decimal("1") + self._pct(fx)
            for member in team.combatants:
                member.damage = Decimal(str(member.damage)) * multiplier
            messages.append(f"🎺 **{owner.name}** leads a Battle Hymn — the party's damage rises!")
        return messages

    def post_damage_triggers(self, defender):
        """Hook D — legacy low-HP recovery, right after damage lands.

        (Bloodweaver's Blood Pact banks and saves inside Combatant.take_damage, so
        it works in every modern battle type without a per-type hook here.)
        """
        messages = []
        effects = self.effects_of(defender)
        if not effects or not defender.is_alive() or getattr(defender, "max_hp", 0) <= 0:
            return messages
        hp_ratio = Decimal(str(defender.hp)) / Decimal(str(defender.max_hp))

        fx = effects.get("second_wind_heal_pct")
        if (
            fx
            and not getattr(defender, "spec_second_wind_used", False)
            and hp_ratio < Decimal(str(fx.get("threshold", 0.30)))
        ):
            defender.spec_second_wind_used = True
            heal = Decimal(str(defender.max_hp)) * self._pct(fx)
            defender.heal(heal)
            messages.append(f"🌅 **{defender.name}** finds a Second Wind and recovers!")

        return messages

    def after_attack_damage(self, attacker, defender, battle):
        """Hook D2 — effects that deal visible follow-up damage after a hit lands."""
        messages = []
        effects = self.effects_of(attacker)
        if not effects or defender is None or not getattr(defender, "is_alive", lambda: False)():
            return messages

        fx = effects.get("doom_circle_pct")
        if fx:
            marker = int(id(attacker))
            bucket = getattr(defender, "spec_doom_circle_sigils", None)
            if not isinstance(bucket, dict):
                bucket = {}
                defender.spec_doom_circle_sigils = bucket

            threshold = int(fx.get("threshold", 3) or 3)
            sigils = int(bucket.get(marker, 0) or 0) + 1
            target_name = getattr(defender, "name", "the target")
            if sigils < threshold:
                bucket[marker] = sigils
                messages.append(
                    f"🔮 Doom Sigils circle **{target_name}** "
                    f"(**{sigils}/{threshold}**)."
                )
            else:
                bucket.pop(marker, None)
                if not bucket and hasattr(defender, "spec_doom_circle_sigils"):
                    delattr(defender, "spec_doom_circle_sigils")

                attacker_damage = Decimal(str(getattr(attacker, "damage", 0) or 0))
                max_hp = Decimal(str(getattr(defender, "max_hp", 0) or 0))
                hp_pct = Decimal(str(fx.get("hp_value", 0))) / Decimal("100")
                hp_damage_cap = attacker_damage * Decimal(str(fx.get("hp_damage_cap", 0.75)))
                hp_damage = min(max_hp * hp_pct, hp_damage_cap)
                bonus_damage = max(
                    Decimal("10"),
                    attacker_damage * self._pct(fx) + hp_damage,
                )
                actual = battle.apply_damage(attacker, defender, bonus_damage)
                messages.append(
                    f"🔮 **{attacker.name}**'s Doom Circle detonates on **{target_name}** "
                    f"for **{battle.format_number(actual)} HP**!"
                )

        return messages

    def turn_end_party_heal(self, combatant, team):
        """Hook E — Winterlight's Gift of Cheer at the owner's turn end."""
        fx = self.effects_of(combatant).get("party_round_heal_pct")
        if not fx or not combatant.is_alive():
            return []
        healed_any = False
        for member in getattr(team, "combatants", []):
            if member.is_alive() and member.hp < member.max_hp:
                member.heal(Decimal(str(member.max_hp)) * self._pct(fx))
                healed_any = True
        if healed_any:
            return [f"🕊️ **{combatant.name}**'s Gift of Cheer mends the party!"]
        return []
