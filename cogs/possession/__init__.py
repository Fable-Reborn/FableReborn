"""GM Possession: a Game Master secretly drives a raid boss in real time.

The GM receives each turn's options in DMs, voiced by the vessel's underling,
and anything they type there is spoken aloud by the vessel. Their identity is
revealed when the possession ends.
"""

import asyncio
import random
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands
from discord.http import handle_message_parameters

from utils import misc as rpgtools
from utils.checks import is_gm

from .engine import (
    ABILITIES,
    DREAD_MAX,
    MAX_RAIDERS,
    MAX_ROUNDS,
    MIN_RAIDERS,
    PLAYER_ACTIONS,
    Encounter,
    Raider,
    split_gold,
)
from .lore import (
    ABILITY_RULES,
    DOMINATE_OUTCOMES,
    PLAYER_ACTION_FLAVOR,
    VESSELS,
    line,
    render,
)

JOIN_SECONDS = 300
ROUND_SECONDS = 35
RESULT_PAUSE_SECONDS = 4
RELAY_COOLDOWN_SECONDS = 2.0
RELAY_MAX_CHARS = 400
CRATE_TYPES = ("common", "uncommon", "rare", "magic", "legendary", "mystery", "fortune", "divine")
NO_MENTIONS = discord.AllowedMentions.none()


def meter(current, total, width=14):
    filled = min(width, max(0, round(width * current / max(1, total))))
    return "█" * filled + "░" * (width - filled)


def upper_first(text):
    return text[:1].upper() + text[1:]


def clip(text, limit=1024):
    return text if len(text) <= limit else text[: limit - 1] + "…"


class PossessionJoinView(discord.ui.View):
    def __init__(self, session):
        super().__init__(timeout=JOIN_SECONDS + 30)
        self.session = session
        self.joined = []
        self.closed = False
        self._lock = asyncio.Lock()

    @discord.ui.button(label="Stand against it", emoji="⚔️", style=discord.ButtonStyle.danger)
    async def join(self, interaction, button):
        if interaction.user.id == self.session.gm.id:
            return await interaction.response.send_message(
                "You cannot fight yourself. *Your underling looks confused.*", ephemeral=True
            )
        has_profile = await self.session.cog.bot.pool.fetchval(
            'SELECT 1 FROM profile WHERE "user" = $1', interaction.user.id
        )
        if not has_profile:
            return await interaction.response.send_message("You need a character to join.", ephemeral=True)
        async with self._lock:
            if self.closed:
                rejection = "The vessel has already turned its gaze upon those gathered."
            elif any(member.id == interaction.user.id for member in self.joined):
                rejection = "You already stand against it."
            elif len(self.joined) >= MAX_RAIDERS:
                rejection = f"The line is full ({MAX_RAIDERS} raiders)."
            else:
                rejection = None
                self.joined.append(interaction.user)
        if rejection:
            return await interaction.response.send_message(rejection, ephemeral=True)
        await interaction.response.send_message(
            "You step forward. The vessel's head turns toward you, slowly.", ephemeral=True
        )

    async def close(self, message):
        async with self._lock:
            self.closed = True
        self.stop()
        for child in self.children:
            child.disabled = True
        try:
            await message.edit(view=self)
        except discord.HTTPException:
            pass


class RaiderActionButton(discord.ui.Button):
    def __init__(self, action):
        label, emoji, _confirm = PLAYER_ACTION_FLAVOR[action]
        style = {
            "strike": discord.ButtonStyle.danger,
            "guard": discord.ButtonStyle.secondary,
            "mend": discord.ButtonStyle.success,
            "rite": discord.ButtonStyle.primary,
        }[action]
        super().__init__(label=label, emoji=emoji, style=style)
        self.action = action

    async def callback(self, interaction):
        session = self.view.session
        raider = session.encounter.raiders.get(interaction.user.id)
        if raider is None:
            return await interaction.response.send_message("You are not part of this fight.", ephemeral=True)
        if not raider.alive:
            return await interaction.response.send_message("The dead cannot act. Watch, and remember.", ephemeral=True)
        if self.view.is_finished():
            return await interaction.response.send_message("Too late. The turn has already ended.", ephemeral=True)
        session.raider_choices[interaction.user.id] = self.action
        await interaction.response.send_message(PLAYER_ACTION_FLAVOR[self.action][2], ephemeral=True)
        session.check_turn_ready()


class RaiderActionView(discord.ui.View):
    def __init__(self, session):
        super().__init__(timeout=ROUND_SECONDS + 15)
        self.session = session
        for action in PLAYER_ACTIONS:
            self.add_item(RaiderActionButton(action))


class TargetSelect(discord.ui.Select):
    def __init__(self, session):
        options = [
            discord.SelectOption(
                label=session.name(raider.user_id)[:100],
                value=str(raider.user_id),
                description=f"{raider.hp:,.0f}/{raider.max_hp:,.0f} HP · last: "
                            f"{session.encounter.last_actions.get(raider.user_id, 'unknown')}",
            )
            for raider in sorted(session.encounter.living(), key=lambda r: r.hp)
        ][:25]
        super().__init__(placeholder="Choose whom to afflict…", options=options, row=0)

    async def callback(self, interaction):
        self.view.target_id = int(self.values[0])
        await interaction.response.send_message(
            f"*{self.view.session.underling['name']} nods.* **{self.view.session.name(self.view.target_id)}**. Now choose the power.",
            ephemeral=True,
        )


class AbilityButton(discord.ui.Button):
    def __init__(self, session, ability, row):
        name, emoji, _narration = session.vessel["abilities"][ability]
        ready = session.encounter.ability_ready(ability)
        super().__init__(
            label=name,
            emoji=emoji,
            style=discord.ButtonStyle.danger if ability == "cataclysm" else discord.ButtonStyle.secondary,
            disabled=not ready,
            row=row,
        )
        self.ability = ability

    async def callback(self, interaction):
        view = self.view
        session = view.session
        if view.is_finished():
            return await interaction.response.send_message("The moment has passed.", ephemeral=True)
        target_id = None
        if ABILITIES[self.ability]["target"]:
            target_id = view.target_id
            if target_id is None or not session.encounter.raiders[target_id].alive:
                target_id = session.encounter.weakest().user_id
        session.gm_choice = (self.ability, target_id)
        view.stop()
        for child in view.children:
            child.disabled = True
        name = session.vessel["abilities"][self.ability][0]
        aimed = f" upon **{session.name(target_id)}**" if target_id else ""
        await interaction.response.edit_message(view=view)
        await interaction.followup.send(
            f"*{session.underling['name']}:* It will be done, {session.underling['master']}. **{name}**{aimed}."
        )
        session.check_turn_ready()


class PossessorPanel(discord.ui.View):
    def __init__(self, session):
        super().__init__(timeout=ROUND_SECONDS + 15)
        self.session = session
        self.target_id = None
        self.add_item(TargetSelect(session))
        for index, ability in enumerate(ABILITIES):
            self.add_item(AbilityButton(session, ability, row=1 + index // 3))

    async def interaction_check(self, interaction):
        return interaction.user.id == self.session.gm.id


class PossessionSession:
    def __init__(self, cog, gm, channel, vessel_key, gold, crate, hp_per_raider):
        self.cog = cog
        self.bot = cog.bot
        self.gm = gm
        self.channel = channel
        self.vessel_key = vessel_key
        self.vessel = VESSELS[vessel_key]
        self.underling = self.vessel["underling"]
        self.gold = gold
        self.crate = crate
        self.hp_per_raider = hp_per_raider
        self.dm = None
        self.encounter = None
        self.names = {}
        self.raider_choices = {}
        self.gm_choice = None
        self.turn_ready = asyncio.Event()
        self.recent_deaths = []
        self.last_relay = 0.0
        self.task = None

    # ---- helpers -------------------------------------------------------
    def name(self, user_id):
        return self.names.get(user_id, "someone")

    def ability_label(self, ability):
        name, emoji, _narration = self.vessel["abilities"][ability]
        return f"{emoji} **{name}**"

    def fields(self):
        enc = self.encounter
        living = enc.living()
        strongest = max(living, key=lambda r: r.damage, default=None)
        weakest = enc.weakest()
        return {
            "round": enc.round_no,
            "max_rounds": enc.max_rounds,
            "weakest": f"**{self.name(weakest.user_id)}**" if weakest else "no one",
            "strongest": f"**{self.name(strongest.user_id)}**" if strongest else "no one",
            "rite": enc.rite,
            "goal": enc.rite_goal,
            "dread": enc.vessel.dread,
            "vessel_pct": round(100 * enc.vessel.hp / enc.vessel.max_hp),
            "living": len(living),
        }

    def check_turn_ready(self):
        if self.encounter is None or self.gm_choice is None:
            return
        if all(r.user_id in self.raider_choices for r in self.encounter.living()):
            self.turn_ready.set()

    async def say_to_gm(self, content=None, **kwargs):
        if self.dm is None:
            return None
        try:
            return await self.dm.send(content, **kwargs)
        except discord.HTTPException:
            return None

    # ---- embeds --------------------------------------------------------
    def status_fields(self, embed):
        enc = self.encounter
        vessel = enc.vessel
        embed.add_field(
            name="Vessel",
            value=f"`{meter(vessel.hp, vessel.max_hp)}` {vessel.hp:,.0f}/{vessel.max_hp:,.0f}",
            inline=False,
        )
        embed.add_field(
            name="🕯️ Severance",
            value=f"`{meter(enc.rite, enc.rite_goal)}` {enc.rite}/{enc.rite_goal} · "
                  f"holds {enc.rite_capacity} voice(s) per turn · "
                  f"strikes +{enc.grip_bonus:.0%}",
            inline=False,
        )
        cataclysm = self.vessel["abilities"]["cataclysm"][0]
        ready = f" · **{cataclysm} is ready!**" if vessel.dread >= DREAD_MAX else ""
        embed.add_field(
            name="Dread",
            value=f"`{meter(vessel.dread, DREAD_MAX)}` {vessel.dread}/{DREAD_MAX}{ready}",
            inline=False,
        )

    def roster(self, with_actions=False):
        lines = []
        for raider in sorted(self.encounter.raiders.values(), key=lambda r: (not r.alive, r.hp)):
            name = self.name(raider.user_id)[:20]
            if not raider.alive:
                lines.append(f"☠️ ~~{name}~~")
                continue
            action = ""
            if with_actions and raider.user_id in self.encounter.last_actions:
                action = " " + PLAYER_ACTION_FLAVOR[self.encounter.last_actions[raider.user_id]][1]
            lines.append(f"{name}: {raider.hp:,.0f}/{raider.max_hp:,.0f}{action}")
        return clip("\n".join(lines) or "None")

    def round_embed(self, deadline):
        enc = self.encounter
        embed = discord.Embed(
            title=f"{self.vessel['emoji']} {upper_first(self.vessel['name'])}, turn {enc.round_no}/{enc.max_rounds}",
            description=(
                f"Choose your action. The turn ends <t:{int(deadline.timestamp())}:R>, "
                "or as soon as everyone has chosen. **Choose nothing and you Strike.**\n"
                "🕯️ *Finish the Severance to cast the will out. Each point loosens its grip on "
                "the vessel, so your strikes land harder. But if the vessel lands a focused blow on "
                "anyone chanting, the circle shatters and that turn's chant is lost.*"
            ),
            color=self.vessel["color"],
        )
        self.status_fields(embed)
        embed.add_field(name="Raiders", value=self.roster(), inline=False)
        embed.set_footer(
            text="⚔️ Strike: damage the vessel · 🛡️ Guard: halve harm taken · "
                 "✨ Mend: heal the most wounded · 🕯️ Rite: advance the Severance"
        )
        return embed

    def prompt_embed(self, deadline):
        enc = self.encounter
        fields = self.fields()
        parts = [line(self.underling["prompt"], **fields)]
        for fallen in self.recent_deaths:
            parts.append(line(self.underling["kill"], fallen=f"**{self.name(fallen)}**"))
        if enc.rite >= enc.rite_goal / 2:
            parts.append(line(self.underling["rite_warning"], **fields))
        if enc.vessel.hp <= enc.vessel.max_hp * 0.3:
            parts.append(line(self.underling["vessel_low"], **fields))
        if enc.ability_ready("cataclysm"):
            parts.append(line(self.underling["dread_full"], **fields))
        embed = discord.Embed(description="\n\n".join(parts), color=self.vessel["color"])
        embed.set_author(name=f"{self.underling['name']}, {self.underling['title']}")
        embed.add_field(
            name=f"Raiders (you must answer <t:{int(deadline.timestamp())}:R>)",
            value=self.roster(with_actions=True),
            inline=False,
        )
        powers = []
        for ability in ABILITIES:
            status = ""
            cooldown = enc.vessel.cooldowns.get(ability, 0)
            if cooldown:
                status = f" *(ready in {cooldown})*"
            elif not enc.ability_ready(ability):
                status = f" *(needs {DREAD_MAX} Dread)*"
            powers.append(f"{self.ability_label(ability)}: {ABILITY_RULES[ability]}{status}")
        embed.add_field(name="Your powers", value=clip("\n".join(powers)), inline=False)
        self.status_fields(embed)
        embed.set_footer(
            text=f"Pick a target, then a power. No target means the weakest. "
                 f"Anything you type here, the vessel speaks aloud. If you stay silent, "
                 f"{self.underling['name']} improvises."
        )
        return embed

    def report_embed(self, report, improvised):
        enc = self.encounter
        ability_name, emoji, narration = self.vessel["abilities"][report.ability]
        target_name = f"**{self.name(report.target_id)}**" if report.target_id else ""
        vessel_acted = report.ability in ("dominate", "ward") or bool(report.hits)
        lines = []
        if report.ability in ("dominate", "ward"):
            lines.append(f"{emoji} *{render(narration, target=target_name)}*")
        if report.dominated:
            dom = report.dominated
            outcome = DOMINATE_OUTCOMES.get(dom.get("action"), DOMINATE_OUTCOMES[None])
            amount = dom.get("amount", 0)
            lines.append(render(
                outcome,
                target=target_name,
                victim=f"**{self.name(dom.get('victim_id'))}**",
                amount=f"{amount:,.0f}" if isinstance(amount, float) else amount,
            ))
        if report.strikes:
            top_uid, top = max(report.strikes, key=lambda s: s[1])
            warded = " *(half turned aside by the ward)*" if report.ward else ""
            lines.append(
                f"⚔️ {len(report.strikes)} raider(s) strike for **{report.total_strike:,.0f}**{warded}. "
                f"Deepest cut: {self.name(top_uid)} ({top:,.0f})."
            )
        for healer, target, amount in report.mends[:5]:
            if amount > 0:
                lines.append(f"✨ {self.name(healer)} mends {self.name(target)} for **{amount:,.0f}**.")
        if len(report.mends) > 5:
            lines.append(f"✨ …and {len(report.mends) - 5} more mend(s).")
        if report.rite_gain:
            lines.append(f"🕯️ The Severance advances **+{report.rite_gain}** ({enc.rite}/{enc.rite_goal}).")
        if report.rite_unheard:
            lines.append(f"🕯️ The circle is full. {report.rite_unheard} voice(s) go unheard.")
        broken_note = None
        if report.rite_broken:
            names = ", ".join(self.name(uid) for uid in report.rite_broken)
            broken_note = (
                f"🕯️💥 **The circle shatters!** {names} was struck mid-chant. "
                f"This turn's Severance is lost ({enc.rite}/{enc.rite_goal})."
            )
        if report.guards:
            lines.append(f"🛡️ {len(report.guards)} raider(s) brace.")
        if report.hits:
            lines.append(f"\n{emoji} *{render(narration, target=target_name)}*")
            for uid, amount, guarded in report.hits[:10]:
                note = " *(guarded)*" if guarded else ""
                lines.append(f"• {self.name(uid)} takes **{amount:,.0f}**{note}")
            if len(report.hits) > 10:
                lines.append(f"• …and {len(report.hits) - 10} more.")
        if report.vessel_healed:
            lines.append(f"🩸 The vessel restores **{report.vessel_healed:,.0f}**.")
        if broken_note:
            lines.append(broken_note)
        for uid in report.deaths:
            lines.append(f"☠️ **{self.name(uid)}** has fallen.")
        if not vessel_acted and enc.outcome in ("slain", "exorcised"):
            lines.append("\n*The vessel's final command dies unspoken.*")
        title = f"{emoji} {ability_name}" if vessel_acted else "The vessel falters!"
        if improvised:
            title += f" (chosen by {self.underling['name']})"
        return discord.Embed(
            title=title, description=clip("\n".join(lines), 4000), color=self.vessel["color"]
        )

    # ---- flow ----------------------------------------------------------
    async def run(self):
        try:
            await self._run()
        except asyncio.CancelledError:
            await self._safe_send(
                self.channel,
                f"{self.vessel['emoji']} *A higher power tears the will out of {self.vessel['name']}. "
                "The vessel collapses, and the possession is broken before it could finish.*",
            )
            raise
        except Exception:
            self.bot.logger.exception("Possession event failed")
            await self._safe_send(
                self.channel,
                "⚠️ The possession unraveled because of a technical problem. No rewards were paid.",
            )
        finally:
            self.cog.session = None

    async def _safe_send(self, destination, content=None, **kwargs):
        try:
            return await destination.send(content, allowed_mentions=NO_MENTIONS, **kwargs)
        except discord.HTTPException:
            return None

    async def _run(self):
        join_ends = datetime.now(timezone.utc) + timedelta(seconds=JOIN_SECONDS)
        arrival = discord.Embed(
            title=f"{self.vessel['emoji']} {upper_first(self.vessel['name'])} has been possessed",
            description=(
                f"{self.vessel['arrival']}\n\n"
                f"The vessel moves <t:{int(join_ends.timestamp())}:R>. "
                f"{MIN_RAIDERS}–{MAX_RAIDERS} raiders."
            ),
            color=self.vessel["color"],
        )
        rewards = []
        if self.gold:
            rewards.append(f"**${self.gold:,}** split among those who stand")
        if self.crate:
            rewards.append(f"a **{self.crate.title()} Crate** for the most valiant")
        if rewards:
            arrival.add_field(name="Bounty", value=" and ".join(rewards), inline=False)
        arrival.set_footer(text="Its will is not the vessel's own. Someone is watching through its eyes.")
        join_view = PossessionJoinView(self)
        join_message = await self.channel.send(embed=arrival, view=join_view)
        await asyncio.sleep(JOIN_SECONDS)
        await join_view.close(join_message)

        raiders = await self._gather(join_view.joined)
        if len(raiders) < MIN_RAIDERS:
            await self._safe_send(
                self.channel,
                f"{self.vessel['emoji']} *{upper_first(self.vessel['name'])} surveys the few who came, "
                "finds them unworthy, and dissolves into nothing.* (Not enough raiders.)",
            )
            await self.say_to_gm(f"*{self.underling['name']}:* Too few came, {self.underling['master']}. Another time.")
            return

        self.encounter = Encounter(
            raiders,
            self.hp_per_raider,
            max_rounds=MAX_ROUNDS,
            cataclysm_variance=self.vessel["cataclysm_variance"],
        )
        await self.say_to_gm(
            f"*{self.underling['name']}:* {len(raiders)} of them, {self.underling['master']}. The vessel is yours."
        )
        while not self.encounter.outcome:
            await self._play_turn()
        await self._finish()

    async def _gather(self, members):
        raiders = []
        async with self.bot.pool.acquire() as conn:
            for member in members:
                profile = await conn.fetchrow(
                    'SELECT health, stathp, xp FROM profile WHERE "user" = $1', member.id
                )
                if not profile:
                    continue
                damage, armor = await self.bot.get_raidstats(member, conn=conn)
                level = rpgtools.xptolevel(profile["xp"])
                hp = float(
                    profile["health"] + 250 + level * 15
                    + profile["stathp"] * rpgtools.STAT_HEALTH_PER_POINT
                )
                self.names[member.id] = member.display_name
                raiders.append(Raider(member.id, member.display_name, hp, hp, float(damage), float(armor)))
        return raiders

    async def _play_turn(self):
        enc = self.encounter
        enc.start_round()
        self.raider_choices = {}
        self.gm_choice = None
        self.turn_ready.clear()
        deadline = datetime.now(timezone.utc) + timedelta(seconds=ROUND_SECONDS)

        raider_view = RaiderActionView(self)
        public = await self.channel.send(embed=self.round_embed(deadline), view=raider_view)
        panel = PossessorPanel(self)
        private = await self.say_to_gm(embed=self.prompt_embed(deadline), view=panel)
        self.recent_deaths = []

        try:
            await asyncio.wait_for(self.turn_ready.wait(), ROUND_SECONDS)
        except asyncio.TimeoutError:
            pass
        raider_view.stop()
        panel.stop()
        for view, message in ((raider_view, public), (panel, private)):
            for child in view.children:
                child.disabled = True
            if message is not None:
                try:
                    await message.edit(view=view)
                except discord.HTTPException:
                    pass

        improvised = self.gm_choice is None
        ability, target_id = self.gm_choice or enc.improvise()
        if improvised:
            await self._safe_send(self.channel, line(self.underling["improvise_public"]))
            await self.say_to_gm(f"*{self.underling['name']}:* {self.underling['improvise_private']}")
        report = enc.resolve_round(dict(self.raider_choices), ability, target_id)
        self.recent_deaths = list(report.deaths)
        await self._safe_send(self.channel, embed=self.report_embed(report, improvised))
        if not enc.outcome:
            await asyncio.sleep(RESULT_PAUSE_SECONDS)

    async def _finish(self):
        enc = self.encounter
        victorious = enc.victorious
        participants = list(enc.raiders)
        survivors = [r.user_id for r in enc.living()]
        mvp = enc.mvp()

        payouts, crate_winner = {}, None
        if victorious:
            payouts = split_gold(self.gold, participants, survivors)
            crate_winner = mvp.user_id if self.crate and mvp else None
            try:
                async with self.bot.pool.acquire() as conn:
                    async with conn.transaction():
                        for uid, amount in payouts.items():
                            await conn.execute(
                                'UPDATE profile SET "money" = "money" + $1 WHERE "user" = $2;', amount, uid
                            )
                        if crate_winner:
                            await conn.execute(
                                f'UPDATE profile SET "crates_{self.crate}" = "crates_{self.crate}" + 1 '
                                'WHERE "user" = $1;',
                                crate_winner,
                            )
            except Exception:
                self.bot.logger.exception("Possession reward transaction failed")
                payouts, crate_winner = {}, None
                await self._safe_send(
                    self.channel,
                    "⚠️ The rewards could not be paid, and no partial payout was kept. Please contact a Game Master.",
                )

        titles = {
            "slain": "The vessel is destroyed!",
            "exorcised": "The Severance is complete!",
            "wiped": "The raid has fallen.",
            "withdrawn": "The possession endures.",
        }
        embed = discord.Embed(
            title=f"{self.vessel['emoji']} {titles[enc.outcome]}",
            description=(
                f"*{self.vessel['endings'][enc.outcome]}*\n\n"
                f"As the connection breaks, the will behind the vessel is revealed: **{self.gm.mention}**."
            ),
            color=self.vessel["color"],
        )
        if mvp and mvp.valor(enc.vessel.attack) > 0:
            embed.add_field(
                name="Most Valiant",
                value=f"**{self.name(mvp.user_id)}**: {mvp.dealt:,.0f} dealt · "
                      f"{mvp.healed:,.0f} mended · {mvp.rites} rite(s)",
                inline=False,
            )
        embed.add_field(
            name="Standing",
            value=f"{len(survivors)}/{len(participants)} raiders survived {enc.round_no} turn(s).",
            inline=False,
        )
        reward_lines = []
        if payouts:
            if survivors:
                reward_lines.append(
                    f"💰 Each raider received **${min(payouts.values()):,}**; "
                    f"survivors received **${max(payouts.values()):,}**."
                )
            else:
                reward_lines.append(f"💰 Each raider received **${max(payouts.values()):,}**.")
        if crate_winner:
            reward_lines.append(f"📦 **{self.name(crate_winner)}** claims a **{self.crate.title()} Crate**.")
        if reward_lines:
            embed.add_field(name="Rewards", value="\n".join(reward_lines), inline=False)
        await self._safe_send(self.channel, embed=embed)

        farewell = self.underling["defeat"] if victorious else self.underling["victory"]
        await self.say_to_gm(f"*{self.underling['name']}:* {farewell}")
        await self._log(enc, payouts, crate_winner)

    async def _log(self, enc, payouts, crate_winner):
        crate_text = f", {self.crate} crate to {crate_winner}" if crate_winner else ""
        content = (
            f"**{self.gm}** possessed {self.vessel['name']} in <#{self.channel.id}>. "
            f"Outcome: **{enc.outcome}** after {enc.round_no} turn(s), {len(enc.raiders)} raider(s). "
            f"Paid **${sum(payouts.values()):,}** to {len(payouts)} player(s){crate_text}."
        )
        try:
            with handle_message_parameters(content=content, allowed_mentions=NO_MENTIONS) as params:
                await self.bot.http.send_message(self.bot.config.game.gm_log_channel, params=params)
        except Exception:
            self.bot.logger.exception("Could not log the possession to the GM log channel")


class Possession(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = None

    def cog_unload(self):
        if self.session and self.session.task:
            self.session.task.cancel()

    def _vessel_list(self):
        return "\n".join(
            f"{v['emoji']} `{key}`: **{upper_first(v['name'])}** ({v['god']}), "
            f"voiced to you by {v['underling']['name']}, {v['underling']['title']}"
            for key, v in VESSELS.items()
        )

    @is_gm()
    @commands.command(hidden=True, brief="Possess a vessel and fight the raiders yourself")
    async def possess(
        self,
        ctx,
        vessel: str = None,
        gold: int = 0,
        crate: str = "none",
        hp_per_raider: int = 0,
    ):
        """`<vessel>` - sepulchure, drakath or elysia
        `[gold]` - gold pool paid on victory: half to everyone, half to survivors
        `[crate]` - crate rarity for the most valiant raider, or none
        `[hp_per_raider]` - fixed vessel health per raider; 0 (default) scales it to the raid's damage

        You secretly control the boss. Your underling DMs you each turn; pick a target and a power.
        Anything you type in that DM is spoken aloud by the vessel. You are revealed at the end.

        Only Game Masters can use this command."""
        key = (vessel or "").lower()
        crate = (crate or "none").lower()
        problem = None
        if self.session:
            problem = "A vessel is already possessed. Use `$unpossess` to break it first."
        elif key not in VESSELS:
            problem = f"Choose a vessel:\n{self._vessel_list()}"
        elif gold < 0:
            problem = "The gold pool cannot be negative."
        elif crate not in CRATE_TYPES + ("none",):
            problem = f"Crate must be one of: {', '.join(CRATE_TYPES)}, or none."
        elif hp_per_raider and not 1_000 <= hp_per_raider <= 1_000_000:
            problem = "Vessel health per raider must be 0 (auto) or between 1,000 and 1,000,000."
        if problem:
            return await ctx.send(problem, allowed_mentions=NO_MENTIONS)

        session = PossessionSession(
            self, ctx.author, ctx.channel, key, gold, None if crate == "none" else crate, hp_per_raider or None
        )
        try:
            session.dm = await ctx.author.create_dm()
            greeting = discord.Embed(
                description=random.choice(session.underling["greeting"]), color=session.vessel["color"]
            )
            greeting.set_author(name=f"{session.underling['name']}, {session.underling['title']}")
            await session.dm.send(embed=greeting)
        except discord.HTTPException:
            return await ctx.send(
                "Your underling cannot reach you. Open your DMs to this bot and try again.",
                delete_after=15,
            )
        try:
            await ctx.message.delete()  # Keep the Possessor's identity hidden.
        except discord.HTTPException:
            pass
        self.session = session
        session.task = asyncio.create_task(session.run())

    @is_gm()
    @commands.command(hidden=True, brief="Forcibly end an active possession")
    async def unpossess(self, ctx):
        """Break the active possession. No rewards are paid.

        Only Game Masters can use this command."""
        if not self.session or not self.session.task:
            return await ctx.send("Nothing is possessed right now.")
        self.session.task.cancel()
        await ctx.send("The possession has been broken.")

    @commands.Cog.listener()
    async def on_message(self, message):
        """Relay the Possessor's DMs through the vessel's mouth."""
        session = self.session
        if (
            session is None
            or message.guild is not None
            or message.author.id != session.gm.id
            or session.dm is None
            or message.channel.id != session.dm.id
        ):
            return
        content = message.content.strip()
        if not content or content.startswith(self.bot.config.bot.global_prefix):
            return
        now = asyncio.get_running_loop().time()
        if now - session.last_relay < RELAY_COOLDOWN_SECONDS:
            try:
                await message.add_reaction("⏳")
            except discord.HTTPException:
                pass
            return
        session.last_relay = now
        text = discord.utils.escape_mentions(discord.utils.escape_markdown(content[:RELAY_MAX_CHARS]))
        sent = await session._safe_send(
            session.channel, f"{session.vessel['emoji']} **{session.vessel['voice']}:** *{text}*"
        )
        try:
            await message.add_reaction("🗣️" if sent else "❌")
        except discord.HTTPException:
            pass


async def setup(bot):
    await bot.add_cog(Possession(bot))
