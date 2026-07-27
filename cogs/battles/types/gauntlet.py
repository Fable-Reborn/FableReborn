# battles/types/gauntlet.py
from .team_battle import TeamBattle


class GauntletBattle(TeamBattle):
    """Defense Gauntlet: an attacking party against a stored defence snapshot.

    This is deliberately a simultaneous fight rather than a tower-style stage
    ladder. The defender and their pet stand together the way a real PvP party
    does, so support skills that key off a *living* owner - Life Spring,
    Guardian Angel, the pet owner guard - can actually fire. Fighting them one
    after another made the whole defensive pet kit dead weight and let a pet
    heal an owner who was already down.
    """

    SETTINGS_SECTION = "gauntlet"

    # Settings this battle reads from the BattleSettings cog, with the fallback
    # used when that cog is unavailable.
    SETTING_DEFAULTS = (
        ("allow_pets", True),
        ("class_buffs", True),
        ("element_effects", True),
        ("luck_effects", True),
        ("reflection_damage", True),
        ("cheat_death", True),
        ("tripping", True),
        ("status_effects", False),
        ("fireball_chance", 0.3),
    )

    def __init__(self, ctx, teams, **kwargs):
        self.attacker_name = kwargs.pop("attacker_name", None)
        self.defender_name = kwargs.pop("defender_name", None)
        super().__init__(ctx, teams, **kwargs)
        self.battle_timed_out = False

        # The attacking party is always team 0, the stored defence is team 1
        self.player_team = self.teams[0]
        self.enemy_team = self.teams[1]

        settings_cog = self.ctx.bot.get_cog("BattleSettings")
        if settings_cog:
            for key, default in self.SETTING_DEFAULTS:
                self.config[key] = settings_cog.get_setting(
                    self.SETTINGS_SECTION, key, default=default
                )

    def format_battle_start_message(self, team_a_members, team_b_members):
        return f"Defense Gauntlet: {team_a_members} attacks {team_b_members}!"

    async def create_battle_embed(self):
        embed = await super().create_battle_embed()
        if self.attacker_name and self.defender_name:
            embed.title = f"Defense Gauntlet: {self.attacker_name} vs {self.defender_name}"
        return embed

    async def end_battle(self):
        """Resolve the gauntlet.

        Returns the winning `Team`, or None when neither side fell inside the
        time limit. There are no PvP win counters or wagers here, so none of
        `TeamBattle`'s payout handling applies.
        """
        self.finished = True

        attacker_down = self.player_team.is_defeated()
        defender_down = self.enemy_team.is_defeated()

        await self.save_battle_to_database()

        if defender_down and not attacker_down:
            return self.player_team
        if attacker_down:
            # Includes a mutual wipe: the attacker has to survive the breach
            return self.enemy_team

        # Both sides still standing when the clock ran out - the gauntlet holds
        self.battle_timed_out = await self.is_timed_out()
        return None
