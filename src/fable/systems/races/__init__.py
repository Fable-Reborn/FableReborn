"""
The IdleRPG Discord Bot
Copyright (C) 2018-2021 Diniboy and Gelbpunkt
Copyright (C) 2023-2024 Lunar (PrototypeX37)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
import discord

from discord.ext import commands

from fable.systems.shard_communication import user_on_cooldown as user_cooldown
from fable.utils.checks import has_char, is_nothing
from fable.utils.i18n import _, locale_doc


class Races(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @has_char()
    @user_cooldown(604800)
    @commands.command(brief=_("Pick or change your race"))
    @locale_doc
    async def race(self, ctx):
        _(
            """Pick or change your race. This can be chosen as long as you have reset points left.

            Each race has a different DMG/DEF distribution:
              - Orc: +4 defense, +0 damage
              - Dwarf: +3 defense, +1 damage
              - Human: +2 defense, +2 damage
              - Elf: +1 defense, +3 damage
              - Jikill: +0 defense, +4 damage
              - Shadeborn: +5 defense, -1 damage
              - Djinn: -1 defense, +5 damage
              

            By default, you are a human.

            After picking the race, you will be asked a personal question, the answer may affect something."""
        )
        embeds = [
            discord.Embed(
                title=_("Human"),
                description=_(
                    "Humans are a team. They work and fight hand in hand and never give"
                    " up, even when some of their friends already died. Their rage and"
                    " hate against enemies makes them attack efficient and"
                    " concentrated. Their attack and defense skills are pretty equal."
                    " +2 DEF +2 ATK"
                ),
                color=self.bot.config.game.primary_colour,
            ),
            discord.Embed(
                title=_("Dwarf"),
                description=_(
                    "Dwarves are the masters of their forge. Although they're very"
                    " small, they can deal a lot of damage with their self-crafted"
                    " equipment. Because of their reflexes, they have more defense than"
                    " attack. Want an ale?"
                    " +3 DEF +1 ATK"
                ),
                color=self.bot.config.game.primary_colour,
            ),
            discord.Embed(
                title=_("Elf"),
                description=_(
                    "Elves are the masteres of camouflage. They melt with their"
                    " enviroment to attack enemies without their knowing. Their bound"
                    " to nature made them good friends of the wild spirits which they"
                    " can call for help and protection. They have more attack than"
                    " defense."
                    " +1 DEF +3 ATK"
                ),
                color=self.bot.config.game.primary_colour,
            ),
            discord.Embed(
                title=_("Orc"),
                description=_(
                    "Orcs are a friendly race based on their rituals of calling their"
                    " ancestors to bless the rain and the deeds of their tribe. More"
                    " ugly than nice, they mostly avoid being attacked by enemies. If"
                    " they can't avoid a fight, then they have mostly no real damage,"
                    " only a bit, but a huge armour. Who cares about the damage as long"
                    " as you don't die?"
                    " +4 DEF +0 ATK"
                ),
                color=self.bot.config.game.primary_colour,
            ),
            discord.Embed(
                title=_("Jikill"),
                description=_(
                    "Jikills are dwarflike creatures with one eye in the middle of"
                    " their face, which lets them have a big and huge forehead, big"
                    " enough for their brain which can kill enemies. These sensitive"
                    " creatures are easily knocked out."
                    " +0 DEF +4 ATK"
                ),
                color=self.bot.config.game.primary_colour,
            ),
            discord.Embed(
                title=_("Djinn"),
                description=_(
                    "Djinn are ethereal beings of pure magic and energy. They possess immense"
                    " power and can unleash devastating attacks. However, their incorporeal form"
                    " makes them less capable of withstanding physical damage."
                    " +5 ATK -1 DEF"
                ),
                color=self.bot.config.game.primary_colour,
            ),
            discord.Embed(
                title=_("Shadeborn"),
                description=_(
                    " Shadeborn possess a shadowy nature that allows them to"
                    " possess inhuman defense, though their attacks might be"
                    "  slightly slower due to their ethereal nature."
                    " +5 DEF -1 ATK"
                ),
                color=self.bot.config.game.primary_colour,
            ),
        ]
        races = ["Human", "Dwarf", "Elf", "Orc", "Jikill", "Djinn", "Shadeborn"]
        questions = {
            "Human": {
                "question": _("One of my biggest regrets is..."),
                "answers": [
                    _("...that I never confessed my true love, and now she is dead."),
                    _("...that I have never been to the funeral of my parents."),
                    _("...that I betrayed my best friend."),
                ],
            },
            "Dwarf": {
                "question": _("One of my proudest creations is..."),
                "answers": [
                    _("...a perfected ale keg."),
                    _("...a magical infused glove."),
                    _("...a bone-forged axe."),
                ],
            },
            "Elf": {
                "question": _("My favourite spirit of the wild is..."),
                "answers": [
                    _("...Beringor, the bear spirit."),
                    _("...Neysa, the tiger spirit."),
                    _("...Avril, the wolf spirit."),
                    _("...Sambuca, the eagle spirit."),
                ],
            },
            "Orc": {
                "question": _("The ancestor that gives me my strength is..."),
                "answers": [
                    _("...my sister."),
                    _("...my father."),
                    _("...my grandmother."),
                    _("...my uncle."),
                ],
            },
            "Jikill": {
                "question": _("The biggest action that can outknock me, is..."),
                "answers": [
                    _("...noise"),
                    _("...spiritual pain"),
                    _("...extreme temperatures."),
                    _("...strange and powerful smells."),
                ],
            },
            "Djinn": {
                "question": _("My source of power is..."),
                "answers": [
                    _("...the boundless desert winds."),
                    _("...the eternal flames."),
                    _("...the deep ocean currents."),
                    _("...the whispers of the cosmos."),
                ],
            },
            "Shadeborn": {
                "question": _("Embrace Shadows or Ethereal?"),
                "answers": [
                    _("...Shadows"),
                    _("...Ethereal"),
                    _("...Both"),
                    _("...Suffering"),
                ],
            },
        }
        race_ = await self.bot.paginator.ChoosePaginator(
            extras=embeds, choices=races, placeholder=_("Choose a race")
        ).paginate(ctx)
        cv = questions[race_]
        answer = await self.bot.paginator.Choose(
            title=cv["question"],
            entries=cv["answers"],
            choices=cv["answers"],
            placeholder=_("Select your answer"),
            return_index=True,
        ).paginate(ctx)

        async with self.bot.pool.acquire() as conn:
            if not is_nothing(ctx):
                await conn.execute(
                    'UPDATE profile SET "reset_points"="reset_points"-$1 WHERE'
                    ' "user"=$2;',
                    1,
                    ctx.author.id,
                )
            await conn.execute(
                'UPDATE profile SET "race"=$1, "cv"=$2 WHERE "user"=$3;',
                race_,
                answer,
                ctx.author.id,
            )
        await ctx.send(_("You are now a {race}.").format(race=race_))


async def setup(bot):
    await bot.add_cog(Races(bot))
