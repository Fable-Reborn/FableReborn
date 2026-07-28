# battles/types/ffa.py
"""Free-for-all battles between three or more independent sides.

TeamBattle assumes exactly two sides in four places: target selection, the
end-of-battle check, winner determination, and the base class's
get_enemy_team_for_combatant. This subclass replaces all four and leaves the
two-team path in TeamBattle untouched, since the gauntlet and couples tower
depend on it.
"""

from .team_battle import TeamBattle

TEAM_LABELS = ("A", "B", "C", "D", "E", "F")


class FreeForAllBattle(TeamBattle):
    """Last side standing wins. Everyone else loses together."""

    # Three sides cannot be coloured friend/foe, so bars go by team index and
    # emoji bars are forced on - a plain text bar would make sides identical.
    HP_BAR_FORCE_TEAM_COLORS = True

    # Must line up with Battle.HP_BAR_TEAM_COLOR_ORDER.
    TEAM_COLOR_DOTS = ("🔵", "🔴", "🟡")

    TARGETING_ALL = "all"
    TARGETING_ROTATING = "rotating"

    ENTRY_SUBJECT = "Free For All Entry"
    WIN_SUBJECT = "Free For All Win"
    REFUND_SUBJECT = "Free For All Refund"

    def __init__(self, ctx, teams, **kwargs):
        if len(teams) < 3:
            raise ValueError(
                f"Free-for-all needs at least three sides, got {len(teams)}"
            )
        super().__init__(ctx, teams, **kwargs)

        # The parent named only the first two sides.
        for index, team in enumerate(self.teams):
            team.name = (
                TEAM_LABELS[index] if index < len(TEAM_LABELS) else str(index + 1)
            )

        targeting = str(kwargs.get("targeting", self.TARGETING_ALL)).strip().lower()
        self.targeting = (
            self.TARGETING_ROTATING
            if targeting in {"rotating", "rotate", "rival"}
            else self.TARGETING_ALL
        )

        # Who actually paid the stake. When the caller supplies this we trust it
        # outright; the transaction fallback matches only on amount and a one
        # hour window, so a refunded lobby can otherwise be miscounted as paid
        # by the next battle for the same amount.
        paid = kwargs.get("paid_player_ids")
        self.paid_player_ids = set(paid) if paid is not None else None

    # ------------------------------------------------------------------
    # side bookkeeping
    # ------------------------------------------------------------------

    @property
    def round_number(self):
        """Completed passes through the turn order."""
        if not self.turn_order:
            return 0
        return self.current_turn // len(self.turn_order)

    def living_teams(self):
        return [team for team in self.teams if not team.is_defeated()]

    def team_health_ratio(self, team):
        combatants = list(getattr(team, "combatants", []))
        if not combatants:
            return 0.0
        total = 0.0
        for combatant in combatants:
            max_hp = float(getattr(combatant, "max_hp", 0) or 0)
            total += (float(combatant.hp) / max_hp) if max_hp > 0 else 0.0
        return total / len(combatants)

    def rank_teams(self):
        """Best to worst: most survivors first, then healthiest."""
        return sorted(
            self.teams,
            key=lambda team: (
                len(team.get_alive_combatants()),
                self.team_health_ratio(team),
            ),
            reverse=True,
        )

    # ------------------------------------------------------------------
    # targeting
    # ------------------------------------------------------------------

    def get_targetable_combatants(self, combatant, current_team):
        if self.targeting == self.TARGETING_ROTATING:
            rival = self.get_rival_team(current_team)
            return rival.get_alive_combatants() if rival is not None else []

        targets = []
        for team in self.teams:
            if team is current_team:
                continue
            targets.extend(team.get_alive_combatants())
        return targets

    def get_rival_team(self, current_team):
        """Rotating mode: each side faces one designated rival per round.

        Stops a true free-for-all collapsing into two sides ganging up on
        whoever is weakest, and removes the kingmaker problem - a dying side
        can only ever spend its last hits on the rival it was assigned.
        """
        if current_team is None:
            return None
        try:
            start = self.teams.index(current_team)
        except ValueError:
            return None

        count = len(self.teams)
        offset = self.round_number % (count - 1)
        for step in range(count - 1):
            candidate = self.teams[(start + 1 + offset + step) % count]
            if candidate is not current_team and not candidate.is_defeated():
                return candidate
        return None

    def get_enemy_team_for_combatant(self, combatant):
        """Override the base class, which returns the first team that is not
        yours - with three sides that silently picks a side that may already be
        dead, and it feeds pet skills, mantles and element counters.
        """
        current_team = self.get_team_for_combatant(combatant)
        if current_team is None:
            return None

        rivals = [
            team
            for team in self.teams
            if team is not current_team and not team.is_defeated()
        ]
        if not rivals:
            return None
        return max(rivals, key=lambda team: len(team.get_alive_combatants()))

    # ------------------------------------------------------------------
    # display
    # ------------------------------------------------------------------

    def format_battle_start_message(self, team_a_members, team_b_members):
        sides = [
            f"Team {team.name} ({', '.join(c.name for c in team.combatants)})"
            for team in self.teams
        ]
        return "Free-for-all: " + " vs ".join(sides) + " - last side standing wins!"

    def format_standings(self):
        parts = []
        for index, team in enumerate(self.teams):
            dot = self.TEAM_COLOR_DOTS[index % len(self.TEAM_COLOR_DOTS)]
            alive = len(team.get_alive_combatants())
            total = len(team.combatants)
            if alive:
                parts.append(f"{dot} **{team.name}** {alive}/{total}")
            else:
                parts.append(f"{dot} ~~{team.name}~~ out")
        return " · ".join(parts)

    async def create_battle_embed(self):
        embed = await super().create_battle_embed()
        embed.title = "Free-For-All"
        embed.insert_field_at(
            0, name="Sides", value=self.format_standings(), inline=False
        )
        return embed

    # ------------------------------------------------------------------
    # resolution
    # ------------------------------------------------------------------

    async def is_battle_over(self):
        if self.finished or await self.is_timed_out():
            return True
        return len(self.living_teams()) < 2

    def player_ids_for(self, team):
        return [
            combatant.user.id
            for combatant in getattr(team, "combatants", [])
            if hasattr(getattr(combatant, "user", None), "id")
            and not combatant.is_pet
        ]

    def all_player_ids(self):
        ids = []
        for team in self.teams:
            ids.extend(self.player_ids_for(team))
        return ids

    async def _has_paid_entry(self, conn, user_id):
        if self.paid_player_ids is not None:
            return user_id in self.paid_player_ids
        return await conn.fetchval(
            'SELECT EXISTS(SELECT 1 FROM transaction WHERE "from"=$1 AND "subject"=$2'
            ' AND "data"::json->>$3 = $4 AND "timestamp" > NOW() - INTERVAL \'1 hour\');',
            user_id,
            self.ENTRY_SUBJECT,
            "Gold",
            str(self.money),
        )

    async def refund_entry_fees(self):
        if self.money <= 0:
            return
        async with self.ctx.bot.pool.acquire() as conn:
            for player_id in self.all_player_ids():
                if not await self._has_paid_entry(conn, player_id):
                    continue
                await conn.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    self.money,
                    player_id,
                )
                await self.ctx.bot.log_transaction(
                    self.ctx,
                    from_=0,
                    to=player_id,
                    subject=self.REFUND_SUBJECT,
                    data={"Gold": self.money},
                    conn=conn,
                )

    async def award_pot(self, winner_ids, loser_ids):
        """Winners get their own stake back plus an even cut of the losers'."""
        if self.money <= 0 or not winner_ids:
            return
        async with self.ctx.bot.pool.acquire() as conn:
            verified = 0
            for loser_id in loser_ids:
                if await self._has_paid_entry(conn, loser_id):
                    verified += 1
            if verified <= 0:
                return

            share = self.money + (self.money * verified) / len(winner_ids)
            for winner_id in winner_ids:
                await conn.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    share,
                    winner_id,
                )
                await self.ctx.bot.log_transaction(
                    self.ctx,
                    from_=0,
                    to=winner_id,
                    subject=self.WIN_SUBJECT,
                    data={"Gold": share},
                    conn=conn,
                )

    async def end_battle(self):
        """Returns (winning_team_name, [losing_team_names]) or None on a timeout
        that left more than one side alive."""
        self.finished = True

        if await self.is_timed_out() and len(self.living_teams()) > 1:
            await self.refund_entry_fees()
            return None

        ranked = self.rank_teams()
        winning_team, losing_teams = ranked[0], ranked[1:]

        winner_ids = self.player_ids_for(winning_team)
        loser_ids = []
        for team in losing_teams:
            loser_ids.extend(self.player_ids_for(team))

        if winner_ids:
            async with self.ctx.bot.pool.acquire() as conn:
                for winner_id in winner_ids:
                    await conn.execute(
                        'UPDATE profile SET "pvpwins"="pvpwins"+1 WHERE "user"=$1;',
                        winner_id,
                    )

        await self.award_pot(winner_ids, loser_ids)

        return winning_team.name, [team.name for team in losing_teams]
