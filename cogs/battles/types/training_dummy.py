import asyncio
import datetime

import discord

from .pve import PvEBattle


TRAINING_DUMMY_DURATION = datetime.timedelta(minutes=5)


class TrainingDummyControlView(discord.ui.View):
    """Owner-only control attached to a live training battle."""

    def __init__(self, battle: "TrainingDummyBattle"):
        super().__init__(timeout=TRAINING_DUMMY_DURATION.total_seconds())
        self.battle = battle
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if int(interaction.user.id) == int(self.battle.ctx.author.id):
            return True
        await interaction.response.send_message(
            "Only the player who started this training battle can cancel it.",
            ephemeral=True,
        )
        return False

    def disable(self, label: str = "Battle Ended") -> None:
        self.cancel_battle.disabled = True
        self.cancel_battle.label = label[:80]

    async def on_timeout(self) -> None:
        self.disable("Time Limit Reached")
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

    @discord.ui.button(
        label="Cancel Test Battle",
        emoji="⏹️",
        style=discord.ButtonStyle.danger,
    )
    async def cancel_battle(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        if self.battle.finished or self.battle.cancelled:
            self.disable()
            return await interaction.response.edit_message(view=self)

        self.battle.cancelled = True
        self.battle.finished = True
        self.battle.cancel_event.set()
        self.disable("Cancelling...")
        await interaction.response.edit_message(view=self)
        self.stop()


class TrainingDummyBattle(PvEBattle):
    """A five-minute PvE sandbox that deliberately grants no progression."""

    def __init__(self, ctx, teams, *, pets_enabled: bool, **kwargs):
        kwargs["allow_pets"] = bool(pets_enabled)
        kwargs["class_buffs"] = True
        kwargs["max_duration"] = TRAINING_DUMMY_DURATION
        super().__init__(ctx, teams, **kwargs)
        self.pets_enabled = bool(pets_enabled)
        self.cancelled = False
        self.forced_timeout = False
        self.cancel_event = asyncio.Event()
        self.control_view = TrainingDummyControlView(self)
        self._training_ended = False
        self._training_result = None

        # PvEBattle loads server PvE settings after Battle.__init__. Force the
        # training-specific switches back to the choices made for this session.
        self.config["allow_pets"] = self.pets_enabled
        self.config["class_buffs"] = True
        self.config["pets_continue_battle"] = self.pets_enabled

    async def start_battle(self):
        started = await super().start_battle()
        if self.battle_message is not None:
            self.control_view.message = self.battle_message
            await self.edit_with_retry(self.battle_message, view=self.control_view)
        return started

    async def create_battle_embed(self):
        embed = await super().create_battle_embed()
        dummy = self.monster_team.combatants[0]
        embed.title = f"Training Dummy: {self.ctx.author.display_name}'s Test Battle"
        embed.insert_field_at(
            0,
            name="Test Configuration",
            value=(
                f"Dummy: **HP {self.format_number(dummy.max_hp)} · "
                f"ATK {self.format_number(dummy.damage)} · "
                f"DEF {self.format_number(dummy.armor)}**\n"
                f"Pets: **{'Enabled' if self.pets_enabled else 'Disabled'}** · "
                "Class abilities: **Enabled** · Rewards: **None**"
            ),
            inline=False,
        )
        embed.set_footer(
            text=f"5-minute test limit · No rewards · Battle ID: {self.battle_id}"
        )
        return embed

    async def end_battle(self):
        """Finalize the display without invoking any PvE reward code."""
        if self._training_ended:
            return self._training_result
        self._training_ended = True
        self.finished = True

        player_defeated = all(
            not combatant.is_alive() for combatant in self.player_team.combatants
        )
        dummy_defeated = all(
            not combatant.is_alive() for combatant in self.monster_team.combatants
        )

        if self.cancelled:
            outcome = "Cancelled by player"
            log_message = "⏹️ The training battle was cancelled."
            button_label = "Battle Cancelled"
            winner = None
        elif self.forced_timeout or await self.is_timed_out():
            outcome = "Five-minute limit reached"
            log_message = "⏱️ The five-minute training limit was reached."
            button_label = "Time Limit Reached"
            winner = None
        elif dummy_defeated:
            outcome = "Dummy defeated"
            log_message = "✅ The training dummy was defeated."
            button_label = "Test Complete"
            winner = self.player_team
        elif player_defeated:
            outcome = "Player side defeated"
            log_message = "💀 The player side was defeated by the training dummy."
            button_label = "Test Complete"
            winner = self.monster_team
        else:
            outcome = "Test ended"
            log_message = "The training battle ended."
            button_label = "Test Complete"
            winner = None

        self._training_result = winner
        self.winner = getattr(winner, "name", None)
        await self.add_to_log(log_message)
        self.control_view.disable(button_label)
        self.control_view.stop()
        await self.update_display()
        if self.battle_message is not None:
            await self.edit_with_retry(
                self.battle_message,
                view=self.control_view,
            )
        await self.save_battle_to_database()
        await self.send_with_retry(
            content=(
                f"Training battle complete: **{outcome}**. "
                "No XP, mastery, pet XP, items, currency, wins, or quest progress "
                "were awarded."
            )
        )
        return winner
