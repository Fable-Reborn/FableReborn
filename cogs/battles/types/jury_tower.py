from __future__ import annotations

import asyncio
import datetime
from decimal import Decimal

import discord

from .tower import TowerBattle


class JuryTowerBattle(TowerBattle):
    """Battle tower variant built around judge-specific verdict mechanics."""

    def __init__(self, ctx, teams, **kwargs):
        super().__init__(ctx, teams, **kwargs)
        self.floor_data = kwargs.get("floor_data", {})
        self.floor_number = int(kwargs.get("floor_number", self.level))
        self.choice_key = kwargs.get("choice_key") or self.floor_data.get("choice", {}).get("default")
        self.choice_data = self.floor_data.get("choice", {})
        self.trial_type = self.floor_data.get("trial_type", "mercy")
        self.judge_name = self.floor_data.get("judge_name", "The Bench")
        self.judge_title = self.floor_data.get("judge_title", "Judge")
        self.floor_title = self.floor_data.get("title", f"Jury Floor {self.floor_number}")
        self.floor_color = self.floor_data.get("color", 0x8B5CF6)

        self.floor_favor_delta = 0
        self.floor_contempt_delta = 0
        self.floor_writs_delta = int(self.floor_data.get("writs_reward", 0))
        self.floor_notes: list[str] = []

        self.base_stats = {}
        self.resolve_rounds_survived = 0
        self.resolve_round_goal = int(self.choice_data.get("round_goal", 0) or 0)
        self.balance_meter = 0
        self.ambition_stacks = 0
        self.surrender_threshold = Decimal("0")
        self.truth_lair_target = self.choice_data.get("liar_target")
        self.truth_witness_target = self.choice_data.get("witness_target")
        self.truth_correct = False
        self.choice_summary = ""
        self.final_directive = None
        self.verdict_result = None

        for enemy in self.enemy_team.combatants:
            if not hasattr(enemy, "jury_key"):
                setattr(enemy, "jury_key", "boss")
            enemy.is_surrendered = False
            enemy.is_spared = False

    def _clip_text(self, text: str | None, limit: int = 180) -> str | None:
        value = str(text or "").strip()
        if not value:
            return None
        if len(value) <= limit:
            return value
        return value[: max(0, limit - 3)].rstrip() + "..."

    def _story_hook(self) -> str | None:
        for candidate in (
            self.floor_data.get("charges"),
            self.floor_data.get("testimony"),
            self.floor_data.get("judge_commentary"),
            self.floor_data.get("case_summary"),
            self.floor_data.get("intro"),
        ):
            clipped = self._clip_text(candidate, limit=170)
            if clipped:
                return clipped
        return None

    async def start_battle(self):
        self.started = True
        self.start_time = datetime.datetime.utcnow()
        await self.save_battle_to_database()
        self.update_turn_order()
        self._store_base_stats()
        self._apply_choice_effects()

        current_enemy = self.enemy_team.combatants[self.current_opponent_index]
        current_enemy_key = getattr(current_enemy, "jury_key", "boss")
        enemy_opening = (self.floor_data.get("enemy_openings") or {}).get(current_enemy_key)
        await self.add_to_log(
            f"{self.judge_name}, {self.judge_title}, watches from the dark."
        )
        if self.choice_summary:
            await self.add_to_log(self.choice_summary, force_new_action=False)
        intro_lines = [f"Prepare to face {current_enemy.name}!"]
        if enemy_opening:
            intro_lines.append(enemy_opening)
        await self.add_to_log("\n".join(intro_lines), force_new_action=True)
        self.battle_message = await self.ctx.send(embed=await self.create_battle_embed())
        await asyncio.sleep(2)
        await self.add_to_log(f"Battle against {current_enemy.name} has begun!", force_new_action=True)
        await self.update_display()
        return True

    def _store_base_stats(self):
        for combatant in self.player_team.combatants:
            self.base_stats[combatant] = {
                "damage": Decimal(str(combatant.damage)),
                "armor": Decimal(str(combatant.armor)),
                "max_hp": Decimal(str(combatant.max_hp)),
                "hp": Decimal(str(combatant.hp)),
                "luck": Decimal(str(combatant.luck)),
                "damage_reflection": Decimal(str(getattr(combatant, "damage_reflection", 0))),
            }
        for combatant in self.enemy_team.combatants:
            self.base_stats[combatant] = {
                "damage": Decimal(str(combatant.damage)),
                "armor": Decimal(str(combatant.armor)),
                "max_hp": Decimal(str(combatant.max_hp)),
                "hp": Decimal(str(combatant.hp)),
            }

    def _alive_players(self):
        return [combatant for combatant in self.player_team.combatants if combatant.is_alive()]

    def _choice_label(self) -> str:
        for option in self.choice_data.get("options", []):
            if option.get("key") == self.choice_key:
                return option.get("label", self.choice_key.title())
        return str(self.choice_key or "Default").title()

    def _current_choice_option(self) -> dict:
        for option in self.choice_data.get("options", []):
            if option.get("key") == self.choice_key:
                return option
        return {}

    def _choice_effect_text(self) -> str | None:
        option = self._current_choice_option()
        return self._clip_text(option.get("effect") or option.get("description"), limit=170)

    def _choice_quote(self) -> str | None:
        option = self._current_choice_option()
        return self._clip_text(option.get("quote"), limit=130)

    def _apply_choice_effects(self):
        label = self._choice_label()
        effect_text = self._choice_effect_text()
        summary_tail = effect_text or ""
        if self.trial_type == "mercy":
            if self.choice_key == "condemn":
                self._modify_player_damage(Decimal("1.15"))
                self.surrender_threshold = Decimal("0")
                self.choice_summary = f"Stance: **{label}**. {summary_tail or 'You hit harder, but each execution stains the climb.'}"
            else:
                self._modify_player_damage(Decimal("0.95"))
                self.surrender_threshold = Decimal("0.30")
                self.choice_summary = f"Stance: **{label}**. {summary_tail or 'Broken foes can kneel instead of dying.'}"

        elif self.trial_type == "truth":
            self.truth_correct = self.choice_key == self.truth_lair_target
            accused_name = self.floor_data.get("enemy_names", {}).get(self.choice_key, self.choice_key)
            if self.truth_correct:
                liar = self._find_enemy_by_key(self.truth_lair_target)
                if liar:
                    liar.armor *= Decimal("0.82")
                    liar.damage *= Decimal("0.92")
                self.floor_favor_delta += 1
                self.choice_summary = f"Marked: **{accused_name}**. {summary_tail or 'You may have marked the liar.'}"
            else:
                chosen = self._find_enemy_by_key(self.choice_key)
                if chosen:
                    chosen.armor *= Decimal("1.12")
                    chosen.damage *= Decimal("1.08")
                self.floor_contempt_delta += 1
                self.choice_summary = f"Marked: **{accused_name}**. {summary_tail or 'A bad mark will make this floor worse.'}"

        elif self.trial_type == "resolve":
            if self.choice_key == "rush":
                self.resolve_round_goal = max(2, self.resolve_round_goal - 1)
                self._modify_player_damage(Decimal("1.12"))
                self._modify_enemy_damage(Decimal("1.08"))
                self.choice_summary = f"Approach: **{label}**. {summary_tail or 'The fight ends faster, but every hit lands harder.'}"
            else:
                self._modify_enemy_damage(Decimal("0.90"))
                self.choice_summary = f"Approach: **{label}**. {summary_tail or 'You brace for a longer fight and soften incoming pressure.'}"

        elif self.trial_type == "sacrifice":
            if self.choice_key == "blood":
                for combatant in self._alive_players():
                    combatant.max_hp *= Decimal("0.75")
                    if combatant.hp > combatant.max_hp:
                        combatant.hp = combatant.max_hp
                self._modify_player_damage(Decimal("1.25"))
                self.choice_summary = f"Oath: **{label}**. {summary_tail or 'Less life. More force.'}"
            elif self.choice_key == "steel":
                for combatant in self._alive_players():
                    combatant.armor *= Decimal("0.65")
                    combatant.luck += Decimal("10")
                    combatant.damage_reflection = max(
                        Decimal(str(getattr(combatant, "damage_reflection", 0))),
                        Decimal("0.12"),
                    )
                self.choice_summary = f"Oath: **{label}**. {summary_tail or 'Your guard weakens, but every counterstroke matters.'}"
            else:
                pet_found = False
                for combatant in self._alive_players():
                    combatant.max_hp *= Decimal("0.94")
                    if combatant.hp > combatant.max_hp:
                        combatant.hp = combatant.max_hp
                for combatant in self.player_team.combatants:
                    if combatant.is_pet:
                        pet_found = True
                        combatant.damage *= Decimal("1.25")
                        combatant.max_hp *= Decimal("1.15")
                        combatant.hp = min(combatant.hp, combatant.max_hp)
                if not pet_found:
                    for combatant in self._alive_players():
                        combatant.armor *= Decimal("0.95")
                    self._modify_player_damage(Decimal("1.08"))
                else:
                    for combatant in self._alive_players():
                        combatant.armor *= Decimal("0.90")
                self.choice_summary = f"Oath: **{label}**. {summary_tail or 'Your companion becomes part of the climb.'}"

        elif self.trial_type == "balance":
            if self.choice_key == "blade":
                self.balance_meter = 1
                self._modify_player_damage(Decimal("1.10"))
                self.choice_summary = f"Scale: **{label}**. {summary_tail or 'You begin leaning toward aggression.'}"
            else:
                self.balance_meter = -1
                self._modify_player_armor(Decimal("1.10"))
                self.choice_summary = f"Scale: **{label}**. {summary_tail or 'You begin leaning toward restraint.'}"

        elif self.trial_type == "ambition":
            if self.choice_key == "allin":
                self._modify_player_damage(Decimal("1.05"))
                self.choice_summary = f"Hunger: **{label}**. {summary_tail or 'Every kill will feed your momentum.'}"
            else:
                self.choice_summary = f"Hunger: **{label}**. {summary_tail or 'You climb without giving in to frenzy.'}"

        elif self.trial_type == "sentence":
            self.final_directive = self.choice_key
            if self.choice_key == "power":
                self._modify_player_damage(Decimal("1.15"))
            elif self.choice_key == "mercy":
                self.surrender_threshold = Decimal("0.22")
                self._modify_enemy_damage(Decimal("0.95"))
            elif self.choice_key == "truth":
                boss = self._find_enemy_by_key("boss")
                if boss:
                    boss.armor *= Decimal("0.90")
            self.choice_summary = f"Law: **{label}**. {summary_tail or 'The last hall will judge whether you stay consistent.'}"

    def _modify_player_damage(self, multiplier: Decimal):
        for combatant in self.player_team.combatants:
            combatant.damage *= multiplier

    def _modify_player_armor(self, multiplier: Decimal):
        for combatant in self.player_team.combatants:
            combatant.armor *= multiplier

    def _modify_enemy_damage(self, multiplier: Decimal):
        for combatant in self.enemy_team.combatants:
            combatant.damage *= multiplier

    def _find_enemy_by_key(self, jury_key: str):
        for combatant in self.enemy_team.combatants:
            if getattr(combatant, "jury_key", None) == jury_key:
                return combatant
        return None

    async def handle_enemy_transition(self):
        self.current_opponent_index += 1
        current_enemy = self.enemy_team.combatants[self.current_opponent_index]
        opening = (self.floor_data.get("enemy_openings") or {}).get(getattr(current_enemy, "jury_key", "boss"))
        await self.add_to_log(f"Prepare to face {current_enemy.name}!", force_new_action=True)
        if opening:
            await self.add_to_log(opening, force_new_action=False)
        self.update_turn_order()
        await self.update_display()
        await asyncio.sleep(2)
        await self.add_to_log(f"Battle with {current_enemy.name} begins!", force_new_action=True)
        await self.update_display()
        self.pending_enemy_transition = False
        self.transition_state = 0
        return True

    async def process_turn(self):
        if self.pending_enemy_transition:
            return await self.handle_enemy_transition()

        if await self.is_battle_over():
            return False

        if not self.turn_order:
            self.update_turn_order()

        if not self.turn_order:
            return False

        acting_combatant = self.turn_order[self.current_turn % len(self.turn_order)]
        player_hp_before = sum(float(c.hp) for c in self._alive_players())
        current_enemy = self.enemy_team.combatants[self.current_opponent_index]
        enemy_hp_before = float(current_enemy.hp)
        enemy_was_alive = current_enemy.is_alive()

        result = await super().process_turn()

        if not result and not enemy_was_alive:
            return result

        if acting_combatant in self.player_team.combatants:
            await self._after_player_turn(current_enemy, enemy_hp_before, enemy_was_alive)
        else:
            await self._after_enemy_turn(current_enemy, player_hp_before)

        return result

    async def _after_player_turn(self, enemy, enemy_hp_before: float, enemy_was_alive: bool):
        if self.trial_type == "balance" and enemy.is_alive() and float(enemy.hp) < enemy_hp_before:
            self.balance_meter = min(self.balance_meter + 1, 4)

        if self.trial_type in {"mercy", "sentence"} and self.surrender_threshold > 0:
            await self._check_for_surrender(enemy)

        if self.trial_type == "truth":
            await self._check_truth_witness(enemy)

        if enemy_was_alive and not enemy.is_alive():
            await self._handle_enemy_down(enemy)

    async def _after_enemy_turn(self, enemy, player_hp_before: float):
        current_player_hp = sum(float(c.hp) for c in self._alive_players())
        if self.trial_type == "balance" and current_player_hp < player_hp_before:
            self.balance_meter = max(self.balance_meter - 1, -4)
            if self.balance_meter <= -3:
                await self._grant_team_shield(Decimal("35"), "The scale swings toward restraint. The chains shield you.")

        if self.trial_type == "resolve" and enemy.is_alive():
            self.resolve_rounds_survived += 1
            if self.choice_key == "stand":
                await self._heal_team(Decimal("14"), "You steady your breath and endure.")
            if self.resolve_round_goal and self.resolve_rounds_survived >= self.resolve_round_goal:
                for combatant in self.enemy_team.combatants:
                    combatant.hp = Decimal("0")
                self.floor_favor_delta += 2
                await self.add_to_log(
                    f"{self.judge_name} slams the black maul. You endured **{self.resolve_round_goal}** rounds. The gate yields."
                )
                await self.update_display()

        if self.trial_type == "sentence" and self.final_directive == "truth":
            boss = self._find_enemy_by_key("boss")
            if boss and boss.is_alive() and self.current_turn % 2 == 0:
                boss.armor *= Decimal("0.97")

    async def _grant_team_shield(self, amount: Decimal, message: str):
        changed = False
        for combatant in self._alive_players():
            shield = Decimal(str(getattr(combatant, "shield", 0)))
            setattr(combatant, "shield", shield + amount)
            changed = True
        if changed:
            await self.add_to_log(f"⚖️ {message}")
            await self.update_display()

    async def _heal_team(self, amount: Decimal, message: str):
        healed = False
        for combatant in self._alive_players():
            before = combatant.hp
            combatant.heal(amount)
            if combatant.hp > before:
                healed = True
        if healed:
            await self.add_to_log(f"🛡️ {message}")
            await self.update_display()

    async def _check_for_surrender(self, enemy):
        if not enemy.is_alive() or getattr(enemy, "is_surrendered", False):
            return

        threshold_value = float(enemy.max_hp) * float(self.surrender_threshold)
        if float(enemy.hp) > threshold_value:
            return

        if self.choice_key == "condemn" and self.trial_type == "mercy":
            return

        enemy.is_surrendered = True
        enemy.is_spared = True
        enemy.hp = Decimal("0")
        self.floor_favor_delta += 1
        await self.add_to_log(f"🕊️ {enemy.name} drops to a knee. You spare them.")
        if self.current_opponent_index < len(self.enemy_team.combatants) - 1:
            self.pending_enemy_transition = True
            self.transition_state = 1
        await self.update_display()

    async def _check_truth_witness(self, enemy):
        if getattr(enemy, "jury_key", None) != self.truth_witness_target:
            return
        if not enemy.is_alive() or getattr(enemy, "is_surrendered", False):
            return

        threshold_value = float(enemy.max_hp) * 0.25
        if float(enemy.hp) <= threshold_value:
            enemy.is_surrendered = True
            enemy.is_spared = True
            enemy.hp = Decimal("0")
            self.floor_favor_delta += 1
            await self.add_to_log(f"📜 {enemy.name} escapes with the truth intact.")
            if self.current_opponent_index < len(self.enemy_team.combatants) - 1:
                self.pending_enemy_transition = True
                self.transition_state = 1
            await self.update_display()

    async def _handle_enemy_down(self, enemy):
        jury_key = getattr(enemy, "jury_key", "")
        if self.trial_type == "mercy" and self.choice_key == "condemn" and not getattr(enemy, "is_spared", False):
            self.floor_contempt_delta += 1

        if self.trial_type == "truth":
            if jury_key == self.truth_lair_target and self.truth_correct:
                self.floor_favor_delta += 1
                await self.add_to_log(f"🔎 Your mark against {enemy.name} was true.")
            elif jury_key == self.truth_witness_target and not getattr(enemy, "is_spared", False):
                self.floor_contempt_delta += 2
                await self.add_to_log(f"⚠️ {enemy.name} carried the truth. Killing them stains the climb.")

        if self.trial_type == "ambition":
            self.ambition_stacks += 1
            if self.choice_key == "measured":
                self.ambition_stacks = min(self.ambition_stacks, 3)
                await self._heal_team(Decimal("20"), "Measured ambition restores your footing.")
            await self._apply_ambition_state()
            await self.add_to_log(f"👑 Hunger rises to **{self.ambition_stacks}**.")

        if self.trial_type == "sentence":
            if self.final_directive == "mercy" and getattr(enemy, "is_spared", False):
                self.floor_favor_delta += 1
            elif self.final_directive == "power":
                self.ambition_stacks += 1
                await self._apply_ambition_state()

    async def _apply_ambition_state(self):
        for combatant in self.player_team.combatants:
            base = self.base_stats.get(combatant, {})
            base_damage = Decimal(str(base.get("damage", combatant.damage)))
            base_armor = Decimal(str(base.get("armor", combatant.armor)))
            if self.choice_key == "allin" or self.final_directive == "power":
                damage_bonus = Decimal("0.16") * Decimal(self.ambition_stacks)
                armor_penalty = Decimal("0.07") * Decimal(self.ambition_stacks)
            else:
                damage_bonus = Decimal("0.10") * Decimal(self.ambition_stacks)
                armor_penalty = Decimal("0.03") * Decimal(self.ambition_stacks)
            combatant.damage = base_damage * (Decimal("1.0") + damage_bonus)
            combatant.armor = max(Decimal("1"), base_armor * (Decimal("1.0") - armor_penalty))
        await self.update_display()

    def _score_balance(self):
        if abs(self.balance_meter) <= 1:
            self.floor_favor_delta += 2
            self.floor_notes.append("The scales settled in balance.")
        else:
            self.floor_contempt_delta += 1
            self.floor_notes.append("The scales tipped too far.")

    def _score_ambition(self):
        if self.choice_key == "allin":
            bonus = 12 + (self.ambition_stacks * 4)
            self.floor_writs_delta += bonus
            if self.ambition_stacks >= 4:
                self.floor_contempt_delta += 2
                self.floor_notes.append("The judges admired your force, not your restraint.")
        else:
            if self.ambition_stacks <= 2:
                self.floor_favor_delta += 2
                self.floor_notes.append("You climbed without losing discipline.")
            else:
                self.floor_contempt_delta += 1

    def _score_sentence(self):
        if self.final_directive == "mercy":
            self.floor_favor_delta += 1
        elif self.final_directive == "truth":
            if self.truth_correct or self.floor_favor_delta >= self.floor_contempt_delta:
                self.floor_favor_delta += 1
        elif self.final_directive == "power":
            self.floor_writs_delta += 24
            if self.ambition_stacks >= 3:
                self.floor_contempt_delta += 1

    async def end_battle(self):
        result = await super().end_battle()
        if result and result.name == "Player":
            if self.trial_type == "balance":
                self._score_balance()
            elif self.trial_type == "ambition":
                self._score_ambition()
            elif self.trial_type == "sentence":
                self._score_sentence()
            elif self.trial_type == "resolve" and self.resolve_round_goal and self.resolve_rounds_survived < self.resolve_round_goal:
                self.floor_contempt_delta += 1
                self.floor_notes.append("You won quickly, but the hall wanted endurance.")

        self.verdict_result = {
            "favor": self.floor_favor_delta,
            "contempt": self.floor_contempt_delta,
            "writs": self.floor_writs_delta,
            "notes": list(self.floor_notes),
            "choice": self.choice_key,
        }
        return result

    async def create_battle_embed(self):
        current_enemy = self.enemy_team.combatants[self.current_opponent_index]
        element_emoji_map = {}
        if hasattr(self.ctx.bot.cogs["Battles"], "emoji_to_element"):
            element_emoji_map = self.ctx.bot.cogs["Battles"].emoji_to_element

        embed = discord.Embed(
            title=f"Jury Tower: Floor {self.floor_number} - {self.ctx.author.display_name} vs {current_enemy.name}",
            description=f"**{self.judge_name}, {self.judge_title}**",
            color=self.floor_color,
        )

        for combatant in self.player_team.combatants:
            current_hp = max(0, float(combatant.hp))
            max_hp = max(1.0, float(combatant.max_hp))
            hp_bar = self.create_hp_bar(current_hp, max_hp, combatant=combatant)
            field_value = f"HP: {current_hp:.1f}/{max_hp:.1f}\n{hp_bar}"
            element_emoji = "❌"
            for emoji, element in element_emoji_map.items():
                if element == combatant.element:
                    element_emoji = emoji
                    break
            if combatant.is_pet:
                field_name = f"{combatant.name} {element_emoji}"
            else:
                field_name = f"**[TEAM A]** \n{combatant.display_name} {element_emoji}"
            if getattr(combatant, "damage_reflection", 0) > 0:
                reflection_percent = float(combatant.damage_reflection) * 100
                field_value += f"\nDamage Reflection: {reflection_percent:.1f}%"
            shield = Decimal(str(getattr(combatant, "shield", 0)))
            if shield > 0:
                field_value += f"\nShield: {float(shield):.1f}"
            embed.add_field(name=field_name, value=field_value, inline=False)

        enemy_hp = max(0, float(current_enemy.hp))
        enemy_max_hp = max(1.0, float(current_enemy.max_hp))
        enemy_bar = self.create_hp_bar(enemy_hp, enemy_max_hp, combatant=current_enemy)
        enemy_value = f"HP: {enemy_hp:.1f}/{enemy_max_hp:.1f}\n{enemy_bar}"
        enemy_emoji = "❌"
        for emoji, element in element_emoji_map.items():
            if element == current_enemy.element:
                enemy_emoji = emoji
                break
        if getattr(current_enemy, "is_spared", False):
            enemy_value += "\nSpared"
        embed.add_field(name=f"**[TEAM B]** \n{current_enemy.name} {enemy_emoji}", value=enemy_value, inline=False)

        state_lines = [f"Stance: **{self._choice_label()}**"]
        choice_effect = self._choice_effect_text()
        if choice_effect:
            state_lines.append(choice_effect)
        if self.trial_type == "resolve" and self.resolve_round_goal:
            state_lines.append(
                f"Resolve: **{self.resolve_rounds_survived}/{self.resolve_round_goal}** enemy turns survived"
            )
        if self.trial_type == "balance":
            state_lines.append(f"Scale Meter: **{self.balance_meter:+d}**")
        if self.trial_type == "ambition" or self.final_directive == "power":
            state_lines.append(f"Hunger: **{self.ambition_stacks}**")
        if self.trial_type == "truth":
            accused = self.floor_data.get("enemy_names", {}).get(self.choice_key, self.choice_key)
            state_lines.append(f"Marked: **{accused}**")
        embed.add_field(name="Battle State", value="\n".join(state_lines), inline=False)

        recent_log = list(self.log)[-4:]
        log_text = "\n\n".join([f"**Action #{index}**\n{message}" for index, message in recent_log])
        embed.add_field(name="Battle Log", value=log_text or "Battle starting...", inline=False)
        embed.set_footer(text=f"Battle ID: {self.battle_id}")
        return embed
