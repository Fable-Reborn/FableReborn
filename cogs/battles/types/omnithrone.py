"""Campaign-only Tier-12 Omnithrone sealing encounter.

Lunaris Omnithrone is not a conventional kill target.  This module keeps the
special encounter isolated from ordinary PvE: the player survives escalating
pressure while the Three Oaths complete a seal.  An equipped pet contributes
to the seal, while Elysia, Sepulchure, and Drakath act as scripted support
rather than low-damage combatants.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import discord

from .pve import PvEBattle


OMNITHRONE_PROGRESS_SCHEMA = """
CREATE TABLE IF NOT EXISTS omnithrone_progress (
    user_id BIGINT PRIMARY KEY,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    clear_count INTEGER NOT NULL DEFAULT 0 CHECK (clear_count >= 0),
    best_phase SMALLINT NOT NULL DEFAULT 1 CHECK (best_phase BETWEEN 1 AND 3),
    best_seal SMALLINT NOT NULL DEFAULT 0 CHECK (best_seal BETWEEN 0 AND 100),
    last_phase SMALLINT NOT NULL DEFAULT 1 CHECK (last_phase BETWEEN 1 AND 3),
    last_seal SMALLINT NOT NULL DEFAULT 0 CHECK (last_seal BETWEEN 0 AND 100),
    last_outcome TEXT,
    first_cleared_at TIMESTAMPTZ,
    last_cleared_at TIMESTAMPTZ,
    last_weekly_clear_key TEXT,
    weekly_clear_count INTEGER NOT NULL DEFAULT 0 CHECK (weekly_clear_count >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


async def ensure_omnithrone_schema(conn) -> None:
    """Create the additive persistence table used by the sealing encounter."""

    await conn.execute(OMNITHRONE_PROGRESS_SCHEMA)


def omnithrone_week_key(now: datetime.datetime | None = None) -> str:
    """Return a stable ISO-week key in UTC for weekly clear state."""

    current = now or datetime.datetime.now(datetime.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=datetime.timezone.utc)
    current = current.astimezone(datetime.timezone.utc)
    iso_year, iso_week, _ = current.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


@dataclass(frozen=True)
class SealRoundResult:
    round_number: int
    phase: int
    phase_name: str
    seal_gain: int
    seal_percent: int
    pet_bonus: int
    complete: bool


@dataclass
class OmnithroneSealState:
    """Pure, deterministic phase and seal progression for one attempt."""

    PHASE_NAMES = {
        1: "The First Roar",
        2: "The Three Oaths",
        3: "Seal the Omnithrone",
    }
    MAX_ROUNDS = 10
    PHASE_TWO_GAIN = 12
    PHASE_THREE_GAIN = 18
    LIVING_PET_BONUS = 4

    round_number: int = 0
    seal_percent: int = 0
    highest_phase: int = 1

    @classmethod
    def phase_for_round(cls, round_number: int) -> int:
        if int(round_number) <= 3:
            return 1
        if int(round_number) <= 7:
            return 2
        return 3

    @property
    def phase(self) -> int:
        next_or_current_round = max(1, self.round_number)
        return self.phase_for_round(next_or_current_round)

    @property
    def phase_name(self) -> str:
        return self.PHASE_NAMES[self.phase]

    @property
    def complete(self) -> bool:
        return self.seal_percent >= 100

    def advance_round(
        self,
        *,
        mortal_survived: bool,
        has_living_pet: bool,
    ) -> SealRoundResult:
        """Advance one survival round and, if possible, build the seal."""

        if self.complete or self.round_number >= self.MAX_ROUNDS:
            raise RuntimeError("The Omnithrone attempt has already reached a terminal round")

        self.round_number += 1
        phase = self.phase_for_round(self.round_number)
        self.highest_phase = max(self.highest_phase, phase)

        base_gain = 0
        if mortal_survived:
            if phase == 2:
                base_gain = self.PHASE_TWO_GAIN
            elif phase == 3:
                base_gain = self.PHASE_THREE_GAIN

        pet_bonus = (
            self.LIVING_PET_BONUS
            if mortal_survived and has_living_pet and phase >= 2
            else 0
        )
        gain = base_gain + pet_bonus
        old_seal = self.seal_percent
        self.seal_percent = min(100, self.seal_percent + gain)
        applied_gain = self.seal_percent - old_seal

        return SealRoundResult(
            round_number=self.round_number,
            phase=phase,
            phase_name=self.PHASE_NAMES[phase],
            seal_gain=applied_gain,
            seal_percent=self.seal_percent,
            pet_bonus=min(pet_bonus, applied_gain),
            complete=self.complete,
        )


class OmnithroneProgressStore:
    """Atomic persistence for attempts, best progress, and clear history."""

    def __init__(self, pool):
        self.pool = pool

    async def record_attempt_started(self, user_id: int) -> int:
        async with self.pool.acquire() as conn:
            return int(
                await conn.fetchval(
                    """
                    INSERT INTO omnithrone_progress (user_id, attempts, updated_at)
                    VALUES ($1, 1, NOW())
                    ON CONFLICT (user_id) DO UPDATE
                    SET attempts = omnithrone_progress.attempts + 1,
                        updated_at = NOW()
                    RETURNING attempts
                    """,
                    int(user_id),
                )
            )

    async def record_result(
        self,
        user_id: int,
        *,
        success: bool,
        phase: int,
        seal_percent: int,
        outcome: str,
        now: datetime.datetime | None = None,
    ) -> dict[str, Any]:
        current = now or datetime.datetime.now(datetime.timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=datetime.timezone.utc)
        current = current.astimezone(datetime.timezone.utc)
        week_key = omnithrone_week_key(current)

        normalized_phase = max(1, min(3, int(phase)))
        normalized_seal = max(0, min(100, int(seal_percent)))
        normalized_outcome = str(outcome).strip().lower() or "failed"

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT first_cleared_at, last_weekly_clear_key, weekly_clear_count
                    FROM omnithrone_progress
                    WHERE user_id = $1
                    FOR UPDATE
                    """,
                    int(user_id),
                )
                if row is None:
                    await conn.execute(
                        """
                        INSERT INTO omnithrone_progress (user_id, attempts)
                        VALUES ($1, 1)
                        ON CONFLICT (user_id) DO NOTHING
                        """,
                        int(user_id),
                    )
                    row = await conn.fetchrow(
                        """
                        SELECT first_cleared_at, last_weekly_clear_key, weekly_clear_count
                        FROM omnithrone_progress
                        WHERE user_id = $1
                        FOR UPDATE
                        """,
                        int(user_id),
                    )

                first_clear = bool(success and row["first_cleared_at"] is None)
                first_weekly_clear = bool(
                    success and row["last_weekly_clear_key"] != week_key
                )
                previous_weekly_count = int(row["weekly_clear_count"] or 0)
                weekly_clear_count = previous_weekly_count
                if success:
                    weekly_clear_count = (
                        1 if first_weekly_clear else previous_weekly_count + 1
                    )

                await conn.execute(
                    """
                    UPDATE omnithrone_progress
                    SET best_phase = GREATEST(best_phase, $2),
                        best_seal = GREATEST(best_seal, $3),
                        last_phase = $2,
                        last_seal = $3,
                        last_outcome = $4,
                        clear_count = clear_count + CASE WHEN $5 THEN 1 ELSE 0 END,
                        first_cleared_at = CASE
                            WHEN $5 THEN COALESCE(first_cleared_at, $6)
                            ELSE first_cleared_at
                        END,
                        last_cleared_at = CASE WHEN $5 THEN $6 ELSE last_cleared_at END,
                        last_weekly_clear_key = CASE
                            WHEN $5 THEN $7 ELSE last_weekly_clear_key
                        END,
                        weekly_clear_count = CASE
                            WHEN $5 THEN $8 ELSE weekly_clear_count
                        END,
                        updated_at = NOW()
                    WHERE user_id = $1
                    """,
                    int(user_id),
                    normalized_phase,
                    normalized_seal,
                    normalized_outcome,
                    bool(success),
                    current,
                    week_key,
                    weekly_clear_count,
                )

        return {
            "first_clear": first_clear,
            "first_weekly_clear": first_weekly_clear,
            "weekly_key": week_key,
            "weekly_clear_count": weekly_clear_count,
        }


class OmnithroneSealBattle(PvEBattle):
    """Tier-12 survival battle whose only victory condition is a completed seal."""

    PRESSURE_BY_PHASE = {
        1: Decimal("0.12"),
        2: Decimal("0.15"),
        3: Decimal("0.21"),
    }
    ELYSIA_HEAL_PERCENT = Decimal("0.06")
    MAX_ARMOR_MITIGATION = Decimal("0.35")

    def __init__(self, ctx, teams, **kwargs):
        kwargs["monster_level"] = self.GOD_OF_GODS_TIER
        kwargs["allow_pets"] = True
        super().__init__(ctx, teams, **kwargs)
        self.seal_state = OmnithroneSealState()
        self.progress_store = OmnithroneProgressStore(ctx.bot.pool)
        self.attempt_number: int | None = None
        self.omnithrone_success = False
        self._result_recorded = False
        self.config["allow_pets"] = True
        self.config["tripping"] = False

    def _mortal_is_alive(self) -> bool:
        return any(
            combatant.is_alive()
            for combatant in self.player_team.combatants
            if not getattr(combatant, "is_pet", False)
            and not getattr(combatant, "is_summoned", False)
        )

    def _has_living_pet(self) -> bool:
        return any(
            combatant.is_alive() and getattr(combatant, "is_pet", False)
            for combatant in self.player_team.combatants
            if not getattr(combatant, "is_summoned", False)
        )

    @classmethod
    def calculate_pressure_damage(cls, combatant, phase: int) -> Decimal:
        """Deal proportional pressure while allowing armor to matter safely."""

        max_hp = max(Decimal("1"), Decimal(str(combatant.max_hp)))
        armor = max(Decimal("0"), Decimal(str(combatant.armor)))
        armor_ratio = armor / (max_hp + armor)
        mitigation = min(cls.MAX_ARMOR_MITIGATION, armor_ratio)
        pressure = cls.PRESSURE_BY_PHASE[int(phase)]
        return max(Decimal("1"), max_hp * pressure * (Decimal("1") - mitigation))

    @staticmethod
    def _seal_bar(seal_percent: int) -> str:
        filled = max(0, min(10, int(seal_percent) // 10))
        return "▰" * filled + "▱" * (10 - filled)

    async def start_battle(self):
        self.started = True
        self.start_time = datetime.datetime.utcnow()
        await self.save_battle_to_database()

        self.attempt_number = await self.progress_store.record_attempt_started(
            self.ctx.author.id
        )
        await self.add_to_log(
            "The objective is to seal Lunaris Omnithrone. The God of Gods cannot be killed."
        )
        await self.add_to_log(
            "Elysia shelters the oath-bearer while Sepulchure and Drakath prepare the seal."
        )
        if self._has_living_pet():
            await self.add_to_log("Your bonded pet anchors the seal and will accelerate its progress.")
        else:
            await self.add_to_log("You enter without a bonded pet; the full ten-round rite is required.")

        await self._handle_godofgods_adaptive_element()
        embed = await self.create_battle_embed()
        self.battle_message = await self.publish_battle_message(embed=embed)

        payload = {
            "user_id": int(self.ctx.author.id),
            "attempt": self.attempt_number,
            "battle_id": self.battle_id,
        }
        self.ctx.bot.dispatch("omnithrone_seal_started", self.ctx, payload)
        return True

    async def process_turn(self):
        if await self.is_battle_over():
            return False

        next_round = self.seal_state.round_number + 1
        phase = self.seal_state.phase_for_round(next_round)
        phase_name = self.seal_state.PHASE_NAMES[phase]
        pressure_lines = [f"Round {next_round}: {phase_name}."]

        for combatant in self.player_team.combatants:
            if not combatant.is_alive() or getattr(combatant, "is_summoned", False):
                continue
            damage = self.calculate_pressure_damage(combatant, phase)
            combatant.take_damage(damage)
            pressure_lines.append(
                f"Lunaris's throne-pressure deals **{self.format_number(damage)} HP** "
                f"to {combatant.name}."
            )

        mortal_survived = self._mortal_is_alive()
        has_living_pet = self._has_living_pet()
        round_result = self.seal_state.advance_round(
            mortal_survived=mortal_survived,
            has_living_pet=has_living_pet,
        )

        if mortal_survived:
            for combatant in self.player_team.combatants:
                if not combatant.is_alive() or getattr(combatant, "is_summoned", False):
                    continue
                healing = Decimal(str(combatant.max_hp)) * self.ELYSIA_HEAL_PERCENT
                combatant.heal(healing)
            pressure_lines.append("Elysia's aegis restores 6% of each survivor's maximum HP.")

            if phase == 1:
                pressure_lines.append(
                    "Elysia holds the First Roar. Sepulchure and Drakath search for a fracture."
                )
            elif phase == 2:
                pressure_lines.append(
                    "Sepulchure tears open the throne's ward while Drakath pins the fracture in place."
                )
            else:
                pressure_lines.append(
                    "The Three Oaths converge. Lunaris remains alive, but the veil begins to close."
                )

            if round_result.seal_gain:
                bonus_text = (
                    f" including +{round_result.pet_bonus}% from your bonded pet"
                    if round_result.pet_bonus
                    else ""
                )
                pressure_lines.append(
                    f"Seal progress: **+{round_result.seal_gain}%**{bonus_text} "
                    f"(**{round_result.seal_percent}% total**)."
                )
        else:
            pressure_lines.append(
                "The oath-bearer falls. A pet cannot finish the rite without its mortal anchor."
            )

        for line in pressure_lines:
            await self.add_to_log(line)
        self.current_turn += 1
        await self.update_display()
        return not await self.is_battle_over()

    async def create_battle_embed(self):
        phase = self.seal_state.phase
        phase_name = self.seal_state.PHASE_NAMES[phase]
        embed = discord.Embed(
            title="Omnithrone Sanctum: Seal the Final Throne",
            description=(
                "**Objective:** survive and complete the seal. Lunaris is not a kill target.\n"
                f"**Phase {phase}/3 — {phase_name}**\n"
                f"**Round:** {self.seal_state.round_number}/{self.seal_state.MAX_ROUNDS}\n"
                f"**Seal:** {self._seal_bar(self.seal_state.seal_percent)} "
                f"{self.seal_state.seal_percent}%"
            ),
            color=discord.Color.gold(),
        )

        for combatant in self.player_team.combatants:
            if getattr(combatant, "is_summoned", False):
                continue
            current_hp = max(Decimal("0"), Decimal(str(combatant.hp)))
            max_hp = max(Decimal("1"), Decimal(str(combatant.max_hp)))
            role = "Bonded Pet" if getattr(combatant, "is_pet", False) else "Oath-Bearer"
            hp_bar = self.create_hp_bar(
                float(current_hp),
                float(max_hp),
                combatant=combatant,
            )
            embed.add_field(
                name=f"{role}: {combatant.name}",
                value=(
                    f"HP: {self.format_number(current_hp)}/{self.format_number(max_hp)}\n"
                    f"{hp_bar}"
                ),
                inline=False,
            )

        boss_name = (
            self.monster_team.combatants[0].name
            if self.monster_team.combatants
            else "Lunaris Omnithrone"
        )
        embed.add_field(
            name=f"{boss_name} — UNKILLABLE",
            value="The Three Oaths are sealing it beyond the veil; damage cannot kill it.",
            inline=False,
        )
        embed.add_field(
            name="Scripted Support",
            value=(
                "Elysia: protection and healing\n"
                "Sepulchure: breaks the throne's ward\n"
                "Drakath: stabilizes the fracture"
            ),
            inline=False,
        )
        embed.add_field(
            name="Battle Log",
            value=self.format_battle_log_field(),
            inline=False,
        )
        embed.set_footer(text=f"Battle ID: {self.battle_id} • No XP, eggs, or ordinary drops")
        return embed

    async def is_battle_over(self):
        if self.finished or self.seal_state.complete:
            return True
        if not self._mortal_is_alive():
            return True
        if self.seal_state.round_number >= self.seal_state.MAX_ROUNDS:
            return True
        return await self.is_timed_out()

    async def end_battle(self):
        if self._result_recorded:
            return self.player_team if self.omnithrone_success else self.monster_team

        self.finished = True
        timed_out = await self.is_timed_out()
        self.omnithrone_success = bool(
            self.seal_state.complete and self._mortal_is_alive() and not timed_out
        )
        if self.omnithrone_success:
            outcome = "sealed"
        elif timed_out:
            outcome = "timeout"
        elif not self._mortal_is_alive():
            outcome = "defeated"
        else:
            outcome = "seal_failed"

        persistence = await self.progress_store.record_result(
            self.ctx.author.id,
            success=self.omnithrone_success,
            phase=self.seal_state.highest_phase,
            seal_percent=self.seal_state.seal_percent,
            outcome=outcome,
        )
        self._result_recorded = True

        payload = {
            "user_id": int(self.ctx.author.id),
            "success": self.omnithrone_success,
            "outcome": outcome,
            "phase": int(self.seal_state.highest_phase),
            "seal_percent": int(self.seal_state.seal_percent),
            "round": int(self.seal_state.round_number),
            "battle_id": self.battle_id,
            **persistence,
        }

        if self.omnithrone_success:
            await self.send_with_retry(
                content=(
                    "**The Omnithrone is sealed.** Lunaris was not slain; the Three Oaths "
                    "forced it beyond the veil. No ordinary PvE rewards are awarded."
                )
            )
            self.ctx.bot.dispatch("omnithrone_seal_completed", self.ctx, payload)
        else:
            await self.send_with_retry(
                content=(
                    f"The sealing rite failed at **Phase {payload['phase']}** with "
                    f"**{payload['seal_percent']}%** seal progress. Lunaris remains unbound."
                )
            )

        self.ctx.bot.dispatch("omnithrone_seal_result", self.ctx, payload)
        await self.save_battle_to_database()
        return self.player_team if self.omnithrone_success else self.monster_team

