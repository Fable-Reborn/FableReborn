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
import asyncio
import inspect
import math

from collections import defaultdict
from datetime import timedelta

import discord

from asyncpg import UniqueViolationError
from discord.ext import commands
from discord.ext.commands.core import Command
from discord.http import handle_message_parameters
from discord.interactions import Interaction
from discord.ui import Button, View, button

from classes.bot import Bot
from classes.classes import ALL_CLASSES_TYPES
from classes.context import Context
from utils.checks import has_open_help_request, is_supporter
from utils.i18n import _, locale_doc


def chunks(iterable, size):
    """Yield successive n-sized chunks from an iterable."""
    for i in range(0, len(iterable), size):
        yield iterable[i : i + size]


class CogMenu(View):
    def __init__(
        self,
        *,
        title: str,
        description: str,
        bot: Bot,
        color: int,
        footer: str,
        per_page: int = 5,
    ) -> None:
        self.title = title
        self.description = description
        self.bot = bot
        self.color = color
        self.footer = footer
        self.per_page = per_page
        self.page = 1
        self.message: discord.Message | None = None
        self.allowed_user: discord.User | None = None

        super().__init__(timeout=60.0)

    @property
    def pages(self) -> int:
        return math.ceil(len(self.description) / self.per_page)

    def embed(self, desc: str) -> discord.Embed:
        e = discord.Embed(
            title=self.title, color=self.color, description="\n".join(desc)
        )
        e.set_author(
            name=self.bot.user,
            icon_url=self.bot.user.display_avatar.url,
        )
        e.set_footer(
            text=f"{self.footer} | Page {self.page}/{self.pages}",
            icon_url=self.bot.user.display_avatar.url,
        )
        return e

    def should_process(self) -> bool:
        return len(self.description) > self.per_page

    def cleanup(self) -> None:
        asyncio.create_task(self.message.delete())

    async def on_timeout(self) -> None:
        self.cleanup()

    async def start(self, ctx: Context) -> None:
        self.allowed_user = ctx.author
        e = self.embed(self.description[0 : self.per_page])

        if self.should_process():
            self.message = await ctx.send(embed=e, view=self)
        else:
            self.message = await ctx.send(embed=e)

    async def update(self) -> None:
        start = (self.page - 1) * self.per_page
        end = self.page * self.per_page
        items = self.description[start:end]
        e = self.embed(items)
        await self.message.edit(embed=e)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.allowed_user.id == interaction.user.id:
            return True
        else:
            asyncio.create_task(
                interaction.response.send_message(
                    _("This command was not initiated by you."), ephemeral=True
                )
            )
            return False

    @button(
        label="Previous",
        style=discord.ButtonStyle.blurple,
        emoji="\N{BLACK LEFT-POINTING TRIANGLE}\ufe0f",
    )
    async def on_previous_page(self, interaction: Interaction, button: Button) -> None:
        if self.page != 1:
            self.page -= 1
            await self.update()

    @button(
        label="Stop",
        style=discord.ButtonStyle.red,
        emoji="\N{BLACK SQUARE FOR STOP}\ufe0f",
    )
    async def on_stop(self, interaction: Interaction, button: Button) -> None:
        self.cleanup()
        self.stop()

    @button(
        label="Next",
        style=discord.ButtonStyle.blurple,
        emoji="\N{BLACK RIGHT-POINTING TRIANGLE}\ufe0f",
    )
    async def on_next_page(self, interaction: Interaction, button: Button) -> None:
        if len(self.description) >= (self.page * self.per_page):
            self.page += 1
            await self.update()


class SubcommandMenu(View):
    def __init__(
        self,
        *,
        cmds: list[commands.Command],
        title: str,
        description: str,
        bot: Bot,
        color: int,
        per_page: int = 5,
    ) -> None:
        self.cmds = cmds
        self.title = title
        self.description = description
        self.bot = bot
        self.color = color
        self.per_page = per_page
        self.page = 1
        self.group_emoji = "💠"
        self.command_emoji = "🔷"

        self.message: discord.Message | None = None
        self.ctx: commands.Context | None = None

        super().__init__(timeout=60.0)

    @property
    def pages(self) -> int:
        return math.ceil(len(self.cmds) / self.per_page)

    def embed(self, cmds: list[commands.Command]) -> discord.Embed:
        e = discord.Embed(
            title=self.title, color=self.color, description=self.description
        )
        e.set_author(
            name=self.bot.user,
            icon_url=self.bot.user.display_avatar.url,
        )
        e.add_field(
            name=_("Subcommands"),
            value="\n".join(
                [
                    f"{self.group_emoji if isinstance(c, commands.Group) else self.command_emoji}"
                    f" `{self.ctx.clean_prefix}{c.qualified_name}` - {_(c.brief)}"
                    for c in cmds
                ]
            ),
        )
        if self.should_process():
            e.set_footer(
                icon_url=self.bot.user.display_avatar.url,
                text=_(
                    "Click on the buttons to see more subcommands. | Page"
                    " {start}/{end}"
                ).format(start=self.page, end=self.pages),
            )
        return e

    def should_process(self) -> bool:
        return len(self.cmds) > self.per_page

    def cleanup(self) -> None:
        asyncio.create_task(self.message.delete())

    async def on_timeout(self) -> None:
        self.cleanup()

    async def start(self, ctx: Context) -> None:
        self.ctx = ctx
        e = self.embed(self.cmds[0 : self.per_page])

        if self.should_process():
            self.message = await ctx.send(embed=e, view=self)
        else:
            self.message = await ctx.send(embed=e)

    async def update(self) -> None:
        start = (self.page - 1) * self.per_page
        end = self.page * self.per_page
        items = self.cmds[start:end]
        e = self.embed(items)
        await self.message.edit(embed=e)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.ctx.author.id == interaction.user.id:
            return True
        else:
            asyncio.create_task(
                interaction.response.send_message(
                    _("This command was not initiated by you."), ephemeral=True
                )
            )
            return False

    @button(
        label="Previous",
        style=discord.ButtonStyle.blurple,
        emoji="\N{BLACK LEFT-POINTING TRIANGLE}\ufe0f",
    )
    async def on_previous_page(self, interaction: Interaction, button: Button) -> None:
        if self.page != 1:
            self.page -= 1
            await self.update()

    @button(
        label="Stop",
        style=discord.ButtonStyle.red,
        emoji="\N{BLACK SQUARE FOR STOP}\ufe0f",
    )
    async def on_stop(self, interaction: Interaction, button: Button) -> None:
        self.cleanup()
        self.stop()

    @button(
        label="Next",
        style=discord.ButtonStyle.blurple,
        emoji="\N{BLACK RIGHT-POINTING TRIANGLE}\ufe0f",
    )
    async def on_next_page(self, interaction: Interaction, button: Button) -> None:
        if len(self.cmds) >= (self.page * self.per_page):
            self.page += 1
            await self.update()


class GuidebookSectionSelect(discord.ui.Select):
    def __init__(self, guide_view: "GuidebookView"):
        self.guide_view = guide_view
        options = []
        for idx, section in enumerate(self.guide_view.sections):
            options.append(
                discord.SelectOption(
                    label=section["label"][:100],
                    value=str(idx),
                    description=section["summary"][:100],
                    emoji=section["emoji"],
                    default=idx == self.guide_view.section_index,
                )
            )
        super().__init__(
            placeholder="Select a guide section",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    def set_current(self, section_index: int) -> None:
        for idx, option in enumerate(self.options):
            option.default = idx == section_index

    async def callback(self, interaction: Interaction):
        self.guide_view.section_index = int(self.values[0])
        self.guide_view.page_index = 0
        await self.guide_view.refresh(interaction=interaction)


class GuidebookView(View):
    def __init__(self, *, ctx: Context, sections: list[dict], color: int):
        super().__init__(timeout=600)
        self.ctx = ctx
        self.sections = sections
        self.color = color
        self.section_index = 0
        self.page_index = 0
        self.message: discord.Message | None = None

        self.section_select = GuidebookSectionSelect(self)
        self.add_item(self.section_select)
        self._sync_controls()

    def _current_section(self) -> dict:
        return self.sections[self.section_index]

    def _current_pages(self) -> list[dict]:
        return self._current_section()["pages"]

    def _build_embed(self) -> discord.Embed:
        section = self._current_section()
        pages = self._current_pages()
        page = pages[self.page_index]
        embed = discord.Embed(
            title=f"{section['emoji']} {section['label']} • {page['title']}",
            description=page.get("description", ""),
            color=self.color,
        )
        for field in page.get("fields", []):
            if field.get("name") and field.get("value"):
                embed.add_field(
                    name=field["name"],
                    value=field["value"],
                    inline=field.get("inline", False),
                )

        embed.set_footer(
            text=(
                f"Section {self.section_index + 1}/{len(self.sections)} • "
                f"Page {self.page_index + 1}/{len(pages)} • "
                "Use the dropdown to jump sections"
            )
        )
        return embed

    def _sync_controls(self) -> None:
        self.section_select.set_current(self.section_index)
        page_count = len(self._current_pages())
        self.prev_page_button.disabled = self.page_index <= 0
        self.next_page_button.disabled = self.page_index >= page_count - 1
        self.prev_section_button.disabled = self.section_index <= 0
        self.next_section_button.disabled = self.section_index >= len(self.sections) - 1

    async def start(self):
        self._sync_controls()
        self.message = await self.ctx.send(embed=self._build_embed(), view=self)

    async def refresh(self, interaction: Interaction | None = None):
        self._sync_controls()
        embed = self._build_embed()
        if interaction:
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed, view=self)
            else:
                await interaction.response.edit_message(embed=embed, view=self)
            return
        if self.message:
            await self.message.edit(embed=embed, view=self)

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id == self.ctx.author.id:
            return True
        await interaction.response.send_message(
            "This guidebook session belongs to another user.",
            ephemeral=True,
        )
        return False

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass

    @button(label="Prev Page", style=discord.ButtonStyle.blurple, row=1)
    async def prev_page_button(self, interaction: Interaction, button: Button):
        if self.page_index > 0:
            self.page_index -= 1
        await self.refresh(interaction=interaction)

    @button(label="Next Page", style=discord.ButtonStyle.blurple, row=1)
    async def next_page_button(self, interaction: Interaction, button: Button):
        if self.page_index < len(self._current_pages()) - 1:
            self.page_index += 1
        await self.refresh(interaction=interaction)

    @button(label="Prev Section", style=discord.ButtonStyle.secondary, row=2)
    async def prev_section_button(self, interaction: Interaction, button: Button):
        if self.section_index > 0:
            self.section_index -= 1
            self.page_index = 0
        await self.refresh(interaction=interaction)

    @button(label="Next Section", style=discord.ButtonStyle.secondary, row=2)
    async def next_section_button(self, interaction: Interaction, button: Button):
        if self.section_index < len(self.sections) - 1:
            self.section_index += 1
            self.page_index = 0
        await self.refresh(interaction=interaction)

    @button(label="Close", style=discord.ButtonStyle.red, row=2)
    async def close_button(self, interaction: Interaction, button: Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def _humanize_class_line(name: str) -> str:
        out = []
        for idx, char in enumerate(name):
            if idx > 0 and char.isupper() and not name[idx - 1].isupper():
                out.append(" ")
            out.append(char)
        return "".join(out)

    def _walk_command_tree(self, command: commands.Command):
        yield command
        if isinstance(command, commands.Group):
            for subcommand in sorted(command.commands, key=lambda cmd: cmd.name):
                yield from self._walk_command_tree(subcommand)

    @staticmethod
    def _extract_command_doc_parts(command: commands.Command) -> tuple[str, str]:
        raw_doc = inspect.getdoc(command.callback) or command.help or ""
        if not raw_doc:
            return ("No detailed help text is available for this command.", "")

        paragraphs = []
        current = []
        for raw_line in raw_doc.splitlines():
            line = raw_line.strip()
            if not line:
                if current:
                    paragraphs.append(" ".join(current).strip())
                    current = []
                continue
            current.append(line)
        if current:
            paragraphs.append(" ".join(current).strip())

        if not paragraphs:
            return ("No detailed help text is available for this command.", "")

        argument_notes = ""
        summary_parts = []
        for paragraph in paragraphs:
            normalized = paragraph.strip()
            if not normalized:
                continue
            if normalized.startswith(("`<", "`[", "<", "[")):
                if not argument_notes:
                    argument_notes = normalized
                continue
            summary_parts.append(normalized)

        if not summary_parts:
            summary_parts = paragraphs[:]

        summary = " ".join(summary_parts[:2]).strip()
        summary = summary.replace("`", "'")
        if len(summary) > 360:
            summary = f"{summary[:357]}..."

        if argument_notes:
            argument_notes = argument_notes.replace("`", "'")
            if len(argument_notes) > 140:
                argument_notes = f"{argument_notes[:137]}..."

        return summary, argument_notes

    def _collect_public_command_metadata(self, prefix: str) -> tuple[dict[str, list[dict]], list[str]]:
        commands_by_cog = defaultdict(list)
        seen = set()

        for root_command in sorted(self.bot.commands, key=lambda cmd: cmd.qualified_name):
            for command in self._walk_command_tree(root_command):
                if command.hidden:
                    continue

                qualified = command.qualified_name
                if qualified in seen:
                    continue
                seen.add(qualified)

                usage = f"{prefix}{qualified} {command.signature}".strip()
                if len(usage) > 90:
                    usage = f"{usage[:87]}..."

                brief = str(command.brief or "No brief description.").replace("\n", " ").strip()
                if len(brief) > 90:
                    brief = f"{brief[:87]}..."
                doc_summary, argument_notes = self._extract_command_doc_parts(command)

                cog_name = command.cog_name or "General"
                commands_by_cog[cog_name].append(
                    {
                        "command": command,
                        "qualified": qualified,
                        "usage": usage,
                        "brief": brief,
                        "doc_summary": doc_summary,
                        "argument_notes": argument_notes,
                    }
                )

        preferred_order = [
            "Profile",
            "Classes",
            "Races",
            "Adventure",
            "Battles",
            "Raid",
            "Gods",
            "Crates",
            "Store",
            "Vote",
            "Trading",
            "BuyOrders",
            "Transaction",
            "Pets",
            "Marriage",
            "Guild",
            "Alliance",
            "Tournament",
            "Ranks",
            "AmuletCrafting",
            "Scheduler",
            "Server",
            "Locale",
            "Images",
            "Miscellaneous",
            "Help",
        ]

        ordered_cogs = [name for name in preferred_order if name in commands_by_cog]
        ordered_cogs.extend(
            sorted(
                [name for name in commands_by_cog.keys() if name not in ordered_cogs],
                key=lambda value: value.lower(),
            )
        )

        return commands_by_cog, ordered_cogs

    def _build_command_atlas_pages(self, prefix: str) -> list[dict]:
        commands_by_cog, ordered_cogs = self._collect_public_command_metadata(prefix)

        pages = []
        for cog_name in ordered_cogs:
            lines = sorted(
                [
                    f"• `{entry['usage']}` - {entry['brief']}"
                    for entry in commands_by_cog[cog_name]
                ],
                key=lambda line: line.lower(),
            )
            total_chunks = math.ceil(len(lines) / 4) if lines else 1
            for page_idx, line_chunk in enumerate(chunks(lines, 4), start=1):
                pages.append(
                    {
                        "title": f"{cog_name} Commands ({page_idx}/{total_chunks})",
                        "description": (
                            f"Public commands from **{cog_name}**.\n"
                            f"Use `{prefix}help <command>` for full syntax and argument details."
                        ),
                        "fields": [
                            {
                                "name": "Command List",
                                "value": "\n".join(line_chunk),
                                "inline": False,
                            }
                        ],
                    }
                )

        if not pages:
            pages.append(
                {
                    "title": "Command Atlas",
                    "description": "No public commands were discovered for this build.",
                    "fields": [],
                }
            )
        return pages

    def _build_command_group_indexes(
        self, prefix: str, commands_by_cog: dict[str, list[dict]], ordered_cogs: list[str]
    ) -> list[dict]:
        category_map = {
            "Starter & Progression": {
                "description": "Character creation, leveling, baseline progression, and recurring rewards.",
                "cogs": [
                    "Profile",
                    "Races",
                    "Classes",
                    "Adventure",
                    "Gods",
                    "Crates",
                    "Store",
                    "Vote",
                    "Miscellaneous",
                    "Help",
                ],
            },
            "Combat & Challenges": {
                "description": "PvP, raids, towers, pets, quest combat, and challenge modes.",
                "cogs": [
                    "Battles",
                    "Raid",
                    "Pets",
                    "Guild",
                    "Alliance",
                    "Tournament",
                    "Quests",
                    "IceDragonChallenge",
                    "SoulforgeDefender",
                    "ElysiaTrials",
                    "HorrorRaid",
                    "Greg",
                    "SlaySpire",
                ],
            },
            "Economy & Social": {
                "description": "Trading, buy orders, marriage/family, rankings, gifting, and account utilities.",
                "cogs": [
                    "Trading",
                    "BuyOrders",
                    "Transaction",
                    "Marriage",
                    "Ranks",
                    "GiftForward",
                    "Scheduler",
                    "Server",
                    "Locale",
                    "ProfileCustomization",
                    "Images",
                    "Patreon",
                    "PatreonCore",
                    "PremiumShop",
                ],
            },
            "Games & Side Modes": {
                "description": "Casino, board/card games, party games, and other side activities.",
                "cogs": [
                    "Gambling",
                    "DragonSlots",
                    "Russian",
                    "RRBeta",
                    "ShotgunRoulette",
                    "Poker",
                    "Chess",
                    "Battleships",
                    "Trivia",
                    "Maths",
                    "Werewolf",
                    "SinglePlayerWerewolf",
                    "NewWerewolf",
                    "HungerGames",
                    "CAH",
                    "MurderHouse",
                    "Lotto",
                ],
            },
            "Events & Special Systems": {
                "description": "Seasonal content, special events, and late-game or experimental systems.",
                "cogs": [
                    "Halloween",
                    "Wintersday",
                    "LunarNewYear",
                    "Easter",
                    "Eastermanager",
                    "Valentine",
                    "PlagueEvent",
                    "GlobalEvents",
                    "Warmap",
                    "Achievements",
                    "Soulforge",
                    "SoulforgeExtension",
                    "ProcessSplice",
                    "MonsterManager",
                    "FableAssistant",
                    "Custom",
                    "Alt",
                    "Story",
                ],
            },
        }

        def _format_cog_entry(cog_name: str) -> str:
            entries = commands_by_cog.get(cog_name, [])
            if not entries:
                return ""
            sample_commands = ", ".join(
                f"`{prefix}{entry['qualified']}`" for entry in entries[:4]
            )
            extra_count = len(entries) - min(len(entries), 4)
            if extra_count > 0:
                sample_commands = f"{sample_commands}, +{extra_count} more"
            return (
                f"• **{cog_name}** ({len(entries)} commands)\n"
                f"  Examples: {sample_commands}"
            )

        pages = []
        used = set()
        for category_name, config in category_map.items():
            category_entries = []
            for cog_name in config["cogs"]:
                line = _format_cog_entry(cog_name)
                if line:
                    category_entries.append(line)
                    used.add(cog_name)
            if not category_entries:
                continue
            for page_idx, line_chunk in enumerate(chunks(category_entries, 6), start=1):
                total_chunks = math.ceil(len(category_entries) / 6)
                pages.append(
                    {
                        "title": f"{category_name} ({page_idx}/{total_chunks})",
                        "description": config["description"],
                        "fields": [
                            {
                                "name": "Indexed Command Groups",
                                "value": "\n".join(line_chunk),
                                "inline": False,
                            }
                        ],
                    }
                )

        uncategorized = [name for name in ordered_cogs if name not in used]
        if uncategorized:
            uncategorized_entries = []
            for cog_name in uncategorized:
                line = _format_cog_entry(cog_name)
                if line:
                    uncategorized_entries.append(line)
            for page_idx, line_chunk in enumerate(chunks(uncategorized_entries, 6), start=1):
                total_chunks = math.ceil(len(uncategorized_entries) / 6)
                pages.append(
                    {
                        "title": f"Additional Command Groups ({page_idx}/{total_chunks})",
                        "description": (
                            "Public command groups discovered from the bot that did not fit one of the main handbook buckets."
                        ),
                        "fields": [
                            {
                                "name": "Indexed Command Groups",
                                "value": "\n".join(line_chunk),
                                "inline": False,
                            }
                        ],
                    }
                )

        if not pages:
            pages.append(
                {
                    "title": "Command Group Index",
                    "description": "No public command groups were discovered for this build.",
                    "fields": [],
                }
            )
        return pages

    def _build_command_writeup_pages(
        self, prefix: str, commands_by_cog: dict[str, list[dict]], ordered_cogs: list[str]
    ) -> list[dict]:
        pages = []

        for cog_name in ordered_cogs:
            entries = sorted(
                commands_by_cog.get(cog_name, []),
                key=lambda entry: entry["qualified"].lower(),
            )
            if not entries:
                continue

            total_chunks = math.ceil(len(entries) / 2)
            for page_idx, chunk_entries in enumerate(chunks(entries, 2), start=1):
                fields = []
                for entry in chunk_entries:
                    lines = [
                        f"Usage: `{entry['usage']}`",
                        entry["doc_summary"],
                    ]
                    if entry.get("argument_notes"):
                        lines.append(f"Args: {entry['argument_notes']}")
                    value = "\n".join(lines)
                    if len(value) > 1000:
                        value = f"{value[:997]}..."
                    fields.append(
                        {
                            "name": entry["qualified"],
                            "value": value,
                            "inline": False,
                        }
                    )

                pages.append(
                    {
                        "title": f"{cog_name} Writeups ({page_idx}/{total_chunks})",
                        "description": (
                            f"Doc-based handbook notes for public commands in **{cog_name}**. "
                            f"These summaries are derived from the command help text and docstrings."
                        ),
                        "fields": fields,
                    }
                )

        if not pages:
            pages.append(
                {
                    "title": "Command Writeups",
                    "description": "No public command documentation was discovered for this build.",
                    "fields": [],
                }
            )

        return pages

    @staticmethod
    def _find_command_entry(
        commands_by_cog: dict[str, list[dict]], qualified_name: str
    ) -> dict | None:
        for entries in commands_by_cog.values():
            for entry in entries:
                if entry["qualified"] == qualified_name:
                    return entry
        return None

    def _build_doc_digest_page(
        self,
        *,
        title: str,
        description: str,
        prefix: str,
        commands_by_cog: dict[str, list[dict]],
        qualified_names: list[str],
    ) -> dict | None:
        fields = []
        for qualified_name in qualified_names:
            entry = self._find_command_entry(commands_by_cog, qualified_name)
            if not entry:
                continue

            lines = [f"Usage: `{entry['usage']}`", entry["doc_summary"]]
            if entry.get("argument_notes"):
                lines.append(f"Args: {entry['argument_notes']}")
            value = "\n".join(lines)
            if len(value) > 900:
                value = f"{value[:897]}..."
            fields.append(
                {
                    "name": qualified_name,
                    "value": value,
                    "inline": False,
                }
            )

        if not fields:
            return None

        return {
            "title": title,
            "description": description,
            "fields": fields,
        }

    def _extend_sections_with_doc_digests(
        self, sections: list[dict], prefix: str, commands_by_cog: dict[str, list[dict]]
    ) -> None:
        section_page_map = {
            "Getting Started": [
                {
                    "title": "Doc Notes: Character Setup",
                    "description": "These summaries come from the commands' own help text, so the booklet matches the real bot behavior.",
                    "commands": ["create", "profile", "race", "class"],
                },
            ],
            "Progression Loop": [
                {
                    "title": "Doc Notes: Leveling Through Adventures",
                    "description": "The progression loop below is derived from the actual docs for your main early-game commands.",
                    "commands": ["adventures", "adventure", "status", "xp", "economy", "exchange"],
                },
                {
                    "title": "Doc Notes: Gear Improvement",
                    "description": "These are the commands that convert successful runs into permanent account growth.",
                    "commands": ["inventory", "items", "equip", "merge", "upgrade"],
                },
            ],
            "Combat Systems": [
                {
                    "title": "Doc Notes: PvP and Raid Battles",
                    "description": "These are the public combat commands players hit once they move beyond the basic adventure loop.",
                    "commands": [
                        "raidbattle",
                        "raidbattle2v1",
                        "raidbattle2v2",
                        "raidstats",
                    ],
                },
                {
                    "title": "Doc Notes: Raid Power Growth",
                    "description": "Raid stat progression has its own upgrade path, so the handbook now uses the exact command docs.",
                    "commands": [
                        "increase",
                        "increase damage",
                        "increase health",
                        "increase defense",
                        "joinraid",
                        "rspref",
                        "raid",
                    ],
                },
            ],
            "Classes": [
                {
                    "title": "Doc Notes: Class Progression",
                    "description": "These summaries explain class setup and evolution using the commands' own help text.",
                    "commands": ["class", "myclass", "evolve", "tree"],
                },
            ],
            "Gods & Favor": [
                {
                    "title": "Doc Notes: God Progression",
                    "description": "The god system has long-term consequences, so these notes come directly from the command docs.",
                    "commands": ["follow", "unfollow", "pray", "sacrifice", "favor", "followers"],
                },
            ],
            "Economy & Trading": [
                {
                    "title": "Doc Notes: Money, Loot, and Market Flow",
                    "description": "This is the account economy loop as described by the real command help text.",
                    "commands": ["economy", "items", "exchange", "sell", "shop", "offer", "merch"],
                },
            ],
            "Group Play": [
                {
                    "title": "Doc Notes: Guild Setup and Membership",
                    "description": "These commands explain how players form guilds, inspect them, and manage member access.",
                    "commands": [
                        "guild",
                        "guild info",
                        "guild members",
                        "guild create",
                        "guild invite",
                        "guild leave",
                        "guild kick",
                    ],
                },
                {
                    "title": "Doc Notes: Guild Progression and Funding",
                    "description": "This is the real doc-backed workflow for guild banking, events, and guild adventures.",
                    "commands": [
                        "guild invest",
                        "guild pay",
                        "guild distribute",
                        "guild upgrade",
                        "guild adventure",
                        "guild status",
                        "guild timers",
                        "guild event",
                        "guild claim",
                    ],
                },
                {
                    "title": "Doc Notes: Alliance and City War",
                    "description": "Alliance docs are spread across city ownership, defenses, guards, and attack preparation.",
                    "commands": [
                        "cities",
                        "alliance",
                        "alliance cityhelp",
                        "alliance cityhelp attack",
                        "alliance cityhelp defend",
                        "alliance build",
                        "alliance build building",
                        "alliance build defense",
                        "alliance buildings",
                        "alliance defenses",
                        "alliance guards",
                        "alliance guards add",
                        "alliance guards pet",
                        "alliance guards pet set",
                        "alliance occupy",
                        "alliance attack",
                        "alliance timers",
                    ],
                },
                {
                    "title": "Doc Notes: Shared Objectives and Quest Flow",
                    "description": "These are the repeatable co-op command paths players use for quests and alliance-scale objectives.",
                    "commands": [
                        "quests",
                        "quests greg",
                        "quests accept",
                        "quests turnin",
                        "quests abandon",
                    ],
                },
            ],
            "Race & Identity": [
                {
                    "title": "Doc Notes: Identity and Profile Control",
                    "description": "These commands shape how your character is configured and displayed.",
                    "commands": ["race", "profilepref", "rename", "color", "badges", "public", "private"],
                },
            ],
            "Daily, Vote, Crates, Boosters": [
                {
                    "title": "Doc Notes: Recurring Rewards",
                    "description": "These summaries come from the commands players should hit on a regular schedule.",
                    "commands": ["daily", "vote", "crates", "open", "store", "boosters", "activate"],
                },
            ],
            "Pets & Eggs": [
                {
                    "title": "Doc Notes: Pet Overview and Battle Readiness",
                    "description": "These docstrings cover the commands that introduce pets, eggs, and battle participation.",
                    "commands": [
                        "pets",
                        "pets help",
                        "pets eggs",
                        "pets status",
                        "pets equip",
                        "pets unequip",
                        "pets rename",
                        "pets alias",
                    ],
                },
                {
                    "title": "Doc Notes: Care, Trust, and Daily Growth",
                    "description": "This page uses the actual help text for feeding, bonding, and training loops.",
                    "commands": [
                        "pets all",
                        "pets feed",
                        "pets pet",
                        "pets play",
                        "pets treat",
                        "pets train",
                        "pets feedhelp",
                    ],
                },
                {
                    "title": "Doc Notes: Skills, Trading, and Daycare",
                    "description": "The pet system expands into build planning, trading, and boarding once you have multiple pets.",
                    "commands": [
                        "pets skills",
                        "pets learn",
                        "pets skillinfo",
                        "pets skilllist",
                        "pets trade",
                        "pets sell",
                        "pets release",
                        "pets daycare",
                        "pets daycare help",
                        "pets daycare browse",
                        "pets daycare board",
                        "pets daycare collect",
                        "pets daycare ledger",
                    ],
                },
            ],
            "Advanced Systems": [
                {
                    "title": "Doc Notes: Amulet Crafting",
                    "description": "These doc-backed notes cover the full amulet loop from resource checks to crafting and selling.",
                    "commands": [
                        "amulet",
                        "amulet help",
                        "amulet available",
                        "amulet resources",
                        "amulet recipe",
                        "amulet craft",
                        "amulet equip",
                        "amulet unequip",
                        "amulet sell_prices",
                        "amulet sell",
                    ],
                },
                {
                    "title": "Doc Notes: Profile and Language Controls",
                    "description": "These commands are not combat power, but they do control persistent account setup and readability.",
                    "commands": [
                        "profilecustom",
                        "profilereset",
                        "language",
                        "language set",
                    ],
                },
            ],
            "Gambling & Minigames": [
                {
                    "title": "Doc Notes: Wagers and Quick Games",
                    "description": "These are the core gambling commands with real docs instead of handbook summaries.",
                    "commands": [
                        "roulette",
                        "roulette table",
                        "blackjack",
                        "flip",
                        "bet",
                        "draw",
                        "edraw",
                    ],
                },
                {
                    "title": "Doc Notes: Card Games and Side Modes",
                    "description": "Use these when you want the appendix to explain side modes from the actual command text.",
                    "commands": [
                        "pokerdraw",
                        "fivecarddraw",
                        "dos",
                        "farkle",
                        "farklehelp",
                        "8ball",
                    ],
                },
            ],
            "Battle Tower Deep Dive": [
                {
                    "title": "Doc Notes: Battle Tower Core",
                    "description": "These are the real command docs for starting, checking, and running the main tower.",
                    "commands": [
                        "battletower",
                        "battletower start",
                        "battletower progress",
                        "battletower fight",
                        "battletower toggle_dialogue",
                    ],
                },
                {
                    "title": "Doc Notes: Jury Tower",
                    "description": "Jury Tower has its own rule set, so it gets a separate doc-backed page.",
                    "commands": [
                        "jurytower",
                        "jurytower help",
                        "jurytower score",
                        "jurytower start",
                        "jurytower progress",
                        "jurytower shop",
                        "jurytower buy",
                        "jurytower fight",
                    ],
                },
            ],
            "Couples Battle Tower": [
                {
                    "title": "Doc Notes: Couples Tower Commands",
                    "description": "These summaries come from the actual duo-tower command docs.",
                    "commands": [
                        "couples_battletower",
                        "couples_battletower start",
                        "couples_battletower progress",
                        "couples_battletower dialogue",
                        "couples_battletower preview",
                        "couples_battletower begin",
                        "couples_battletower help",
                    ],
                },
            ],
            "Ice Dragon Challenge": [
                {
                    "title": "Doc Notes: Dragon Challenge Flow",
                    "description": "The Ice Dragon system now points directly at its real party, leaderboard, and reset docs.",
                    "commands": [
                        "dragonchallenge",
                        "dragonchallenge party",
                        "dragonchallenge leaderboard",
                        "dragonchallenge damageleaderboard",
                        "dragonchallenge reset",
                    ],
                },
            ],
            "PvE Pet Combat": [
                {
                    "title": "Doc Notes: PvE Routing and Location Control",
                    "description": "These commands drive encounter selection, scouting, and location defaults.",
                    "commands": [
                        "pve",
                        "scout",
                        "pvelocations",
                        "pveinfo",
                        "pvedefault",
                    ],
                },
                {
                    "title": "Doc Notes: PvE Battle Preferences and Pet Integration",
                    "description": "These docs cover the battle options that matter once pets are part of your PvE loop.",
                    "commands": [
                        "battlebars",
                        "pvesplice",
                        "pets equip",
                        "pets unequip",
                        "pets status",
                        "pets skills",
                    ],
                },
            ],
            "Egg Lifecycle": [
                {
                    "title": "Doc Notes: Egg Handling and Ownership",
                    "description": "These are the exact commands players use to inspect, move, or permanently remove eggs.",
                    "commands": [
                        "pets eggs",
                        "pets trade",
                        "pets sell",
                        "pets release",
                    ],
                },
            ],
            "Soulforge & Splice": [
                {
                    "title": "Doc Notes: Soulforge Flow",
                    "description": "Late-game Soulforge progression is doc-heavy, so this section now reflects the actual command descriptions.",
                    "commands": ["soulforge", "soulforgeguide", "soulforgecommands", "forgesoulforge", "splice", "splicestatus", "splices", "forgegodpet"],
                },
            ],
            "Rankings & Achievements": [
                {
                    "title": "Doc Notes: Leaderboards",
                    "description": "These commands expose the main public rankings across wealth, XP, PvP, tower, and dragon systems.",
                    "commands": [
                        "richest",
                        "highscore",
                        "pvpstats",
                        "battletowerlb",
                        "lovers",
                        "coupleslb",
                        "totalboard",
                        "weeklyboard",
                    ],
                },
                {
                    "title": "Doc Notes: Achievement Tracking",
                    "description": "This is the command surface for checking long-run completion progress.",
                    "commands": ["achievement"],
                },
            ],
            "Seasonal & Event Systems": [
                {
                    "title": "Doc Notes: Halloween and Wintersday",
                    "description": "These doc pages cover the seasonal commands players actually use when those events are active.",
                    "commands": [
                        "trickortreat",
                        "spookyshop",
                        "spookyshop buy",
                        "spookyshop bal",
                        "yummy",
                        "bags",
                        "calendar",
                        "calendar open",
                        "xmasshop",
                        "xmasshop buy",
                        "snowflakes",
                        "combine",
                    ],
                },
                {
                    "title": "Doc Notes: Lunar New Year and Valentine",
                    "description": "These command docs explain the bag, shop, and partner-gifting loops for seasonal events.",
                    "commands": [
                        "lunarnewyear",
                        "lunarnewyear buy",
                        "lunarnewyear bal",
                        "openlunar",
                        "lunarbagcount",
                        "valentine",
                        "chocolate",
                    ],
                },
                {
                    "title": "Doc Notes: Easter Guardian Trials",
                    "description": "Easter is its own full event system, so the handbook now includes the real subcommand docs.",
                    "commands": [
                        "easter",
                        "easter help",
                        "easter join",
                        "easter abilities",
                        "easter customize",
                        "easter collect",
                        "easter stats",
                        "easter battle",
                        "easter upgrade",
                        "easter vote",
                        "easter leaderboard",
                    ],
                },
            ],
        }

        for section in sections:
            page_specs = section_page_map.get(section.get("label"))
            if not page_specs:
                continue

            for page_spec in page_specs:
                page = self._build_doc_digest_page(
                    title=page_spec["title"],
                    description=page_spec["description"],
                    prefix=prefix,
                    commands_by_cog=commands_by_cog,
                    qualified_names=page_spec["commands"],
                )
                if page:
                    section.setdefault("pages", []).append(page)

    def _build_next_steps_section(self, prefix: str, profile_row) -> dict:
        if not profile_row:
            return {
                "label": "Your Next Steps",
                "summary": "Personalized first actions for players without a character yet.",
                "emoji": "🧭",
                "pages": [
                    {
                        "title": "No Character Detected",
                        "description": "Start here to unlock all gameplay systems.",
                        "fields": [
                            {
                                "name": "Immediate Actions",
                                "value": (
                                    f"1. `{prefix}create`\n"
                                    f"2. `{prefix}profile`\n"
                                    f"3. `{prefix}adventures`\n"
                                    f"4. `{prefix}adventure 1`"
                                ),
                                "inline": False,
                            },
                            {
                                "name": "After First Adventure",
                                "value": (
                                    f"• `{prefix}status` to track progress\n"
                                    f"• `{prefix}inventory` / `{prefix}items`\n"
                                    f"• `{prefix}exchange` to convert loot"
                                ),
                                "inline": False,
                            },
                        ],
                    }
                ],
            }

        race = profile_row.get("race") or "Human"
        god = profile_row.get("god") or "None"
        money = int(profile_row.get("money") or 0)
        dragoncoins = int(profile_row.get("dragoncoins") or 0)
        reset_points = int(profile_row.get("reset_points") or 0)
        class_names = profile_row.get("class") or []
        class_preview = ", ".join([str(c) for c in class_names if c]) or "No class selected"

        focus_lines = []
        if class_names and len(class_names) >= 2 and class_names[1] and class_names[1] != "No Class":
            focus_lines.append("• You have both class slots active. Prioritize evolve + class synergy.")
        else:
            focus_lines.append("• Push to level 12 if needed, then unlock your second class slot.")

        if not profile_row.get("god"):
            focus_lines.append(f"• Pick a god with `{prefix}follow` once you are ready for favor/luck systems.")
        else:
            focus_lines.append(f"• Maintain favor flow using `{prefix}pray` and `{prefix}sacrifice`.")

        if money < 100000:
            focus_lines.append("• Build money safely via adventure loop before heavy upgrades.")
        else:
            focus_lines.append("• You can start investing into upgrades, boosts, and trade opportunities.")

        return {
            "label": "Your Next Steps",
            "summary": "Profile-aware action plan from your current account state.",
            "emoji": "🧭",
            "pages": [
                {
                    "title": "Current Snapshot",
                    "description": "Live overview from your profile data.",
                    "fields": [
                        {
                            "name": "State",
                            "value": (
                                f"• Race: **{race}**\n"
                                f"• God: **{god}**\n"
                                f"• Classes: **{class_preview}**\n"
                                f"• Money: **${money:,}**\n"
                                f"• Dragon Coins: **{dragoncoins:,}**\n"
                                f"• Reset Points: **{reset_points}**"
                            ),
                            "inline": False,
                        },
                        {
                            "name": "Priority Recommendations",
                            "value": "\n".join(focus_lines),
                            "inline": False,
                        },
                    ],
                },
                {
                    "title": "Suggested 20-Minute Session",
                    "description": "A short, high-value routine from your current stage.",
                    "fields": [
                        {
                            "name": "Run Order",
                            "value": (
                                f"1. `{prefix}daily` and `{prefix}vote`\n"
                                f"2. `{prefix}adventures` then `{prefix}adventure <best_level>`\n"
                                f"3. `{prefix}status` while queueing upgrades\n"
                                f"4. `{prefix}exchange` + `{prefix}equip` updates\n"
                                f"5. Optional growth: `{prefix}battle`, `{prefix}battletower fight`, `{prefix}trade`"
                            ),
                            "inline": False,
                        }
                    ],
                },
            ],
        }

    def _get_pet_guide_metrics(self) -> dict:
        metrics = {
            "max_level": 100,
            "xp_curve_multiplier": 2.5,
            "skill_point_interval": 10,
            "level_stat_bonus_pct": 1.0,
            "battle_daily_xp_cap": 12000,
            "battle_xp_base": 80,
            "battle_xp_per_tier": 25,
            "trust_tiers": [
                {"threshold": 0, "name": "Distrustful", "bonus": -10, "emoji": "😠"},
                {"threshold": 21, "name": "Cautious", "bonus": 0, "emoji": "😐"},
                {"threshold": 41, "name": "Trusting", "bonus": 5, "emoji": "😊"},
                {"threshold": 61, "name": "Loyal", "bonus": 8, "emoji": "😍"},
                {"threshold": 81, "name": "Devoted", "bonus": 10, "emoji": "🥰"},
            ],
            "skill_elements": 8,
            "skill_branches_per_element": 3,
            "skills_per_branch": 5,
            "skill_unlock_levels": [1, 3, 5, 7, 10],
            "skill_cost_values": [1, 2, 3, 4, 5],
        }

        pets_cog = self.bot.get_cog("Pets")
        if not pets_cog:
            return metrics

        def _set_int(field_name: str, attr_name: str):
            value = getattr(pets_cog, attr_name, None)
            try:
                metrics[field_name] = int(value)
            except (TypeError, ValueError):
                pass

        def _set_float(field_name: str, attr_name: str):
            value = getattr(pets_cog, attr_name, None)
            try:
                metrics[field_name] = float(value)
            except (TypeError, ValueError):
                pass

        _set_int("max_level", "PET_MAX_LEVEL")
        _set_float("xp_curve_multiplier", "PET_XP_CURVE_MULTIPLIER")
        _set_int("skill_point_interval", "PET_SKILL_POINT_INTERVAL")
        _set_float("level_stat_bonus_pct", "PET_LEVEL_STAT_BONUS")
        metrics["level_stat_bonus_pct"] *= 100
        _set_int("battle_daily_xp_cap", "PET_BATTLE_DAILY_XP_CAP")
        _set_int("battle_xp_base", "PET_BATTLE_XP_BASE")
        _set_int("battle_xp_per_tier", "PET_BATTLE_XP_PER_TIER")

        trust_tiers = []
        trust_source = getattr(pets_cog, "TRUST_LEVELS", None)
        if isinstance(trust_source, dict):
            for threshold, info in trust_source.items():
                try:
                    threshold_int = int(threshold)
                except (TypeError, ValueError):
                    continue
                if not isinstance(info, dict):
                    continue
                tier_name = str(info.get("name") or f"Tier {threshold_int}")
                tier_emoji = str(info.get("emoji") or "")
                try:
                    tier_bonus = int(info.get("bonus", 0))
                except (TypeError, ValueError):
                    tier_bonus = 0
                trust_tiers.append(
                    {
                        "threshold": threshold_int,
                        "name": tier_name,
                        "bonus": tier_bonus,
                        "emoji": tier_emoji,
                    }
                )
        if trust_tiers:
            metrics["trust_tiers"] = sorted(trust_tiers, key=lambda item: item["threshold"])

        skill_tree = getattr(pets_cog, "SKILL_TREES", None)
        if isinstance(skill_tree, dict) and skill_tree:
            metrics["skill_elements"] = len(skill_tree)
            branch_counts = []
            skills_per_branch = []
            unlock_levels = set()
            cost_values = set()

            for branches in skill_tree.values():
                if not isinstance(branches, dict):
                    continue
                branch_counts.append(len(branches))
                for branch_skills in branches.values():
                    if not isinstance(branch_skills, dict):
                        continue
                    skills_per_branch.append(len(branch_skills))
                    for level_key, skill_data in branch_skills.items():
                        try:
                            unlock_levels.add(int(level_key))
                        except (TypeError, ValueError):
                            pass
                        if isinstance(skill_data, dict):
                            try:
                                cost_values.add(int(skill_data.get("cost", 0)))
                            except (TypeError, ValueError):
                                pass

            if branch_counts:
                metrics["skill_branches_per_element"] = max(branch_counts)
            if skills_per_branch:
                metrics["skills_per_branch"] = max(skills_per_branch)
            if unlock_levels:
                metrics["skill_unlock_levels"] = sorted(unlock_levels)
            if cost_values:
                metrics["skill_cost_values"] = sorted(cost_values)

        return metrics

    def _get_dragon_stage_guide_data(self) -> dict:
        guide = {
            "stages": [
                {"name": "Frostbite Wyrm", "min_level": 1, "max_level": 5},
                {"name": "Corrupted Ice Dragon", "min_level": 6, "max_level": 10},
                {"name": "Permafrost", "min_level": 11, "max_level": 15},
                {"name": "Absolute Zero", "min_level": 16, "max_level": 20},
                {"name": "Void Tyrant", "min_level": 21, "max_level": 25},
                {"name": "Eternal Frost", "min_level": 26, "max_level": 30},
            ],
            "defeats_per_level": 40,
            "weekly_reset_days": 7,
            "dragon_coin_chance_percent": 10,
            "dragon_coin_min": 2,
            "dragon_coin_max": 5,
        }

        battles_cog = self.bot.get_cog("Battles")
        if not battles_cog:
            return guide

        for field_name, attr_name in [
            ("dragon_coin_chance_percent", "DRAGON_COIN_DROP_CHANCE_PERCENT"),
            ("dragon_coin_min", "DRAGON_COIN_DROP_MIN"),
            ("dragon_coin_max", "DRAGON_COIN_DROP_MAX"),
        ]:
            value = getattr(battles_cog, attr_name, None)
            try:
                guide[field_name] = int(value)
            except (TypeError, ValueError):
                pass

        dragon_ext = getattr(getattr(battles_cog, "battle_factory", None), "dragon_ext", None)
        if not dragon_ext:
            return guide

        try:
            defeats_per_level = int(dragon_ext.get_level_up_threshold(1))
            guide["defeats_per_level"] = defeats_per_level
        except Exception:
            pass

        stage_map = getattr(dragon_ext, "default_dragon_stages", None)
        if isinstance(stage_map, dict) and stage_map:
            stages = []
            for stage_name, stage_info in stage_map.items():
                if not isinstance(stage_info, dict):
                    continue
                level_range = stage_info.get("level_range")
                if not isinstance(level_range, (list, tuple)) or len(level_range) != 2:
                    continue
                try:
                    min_level = int(level_range[0])
                    max_level = int(level_range[1])
                except (TypeError, ValueError):
                    continue
                stages.append(
                    {
                        "name": str(stage_name),
                        "min_level": min_level,
                        "max_level": max_level,
                    }
                )
            if stages:
                guide["stages"] = sorted(stages, key=lambda item: item["min_level"])

        return guide

    def _build_guidebook_index_section(self, prefix: str, sections: list[dict]) -> dict:
        section_lookup = {section["label"]: section for section in sections}
        section_numbers = {
            section["label"]: idx + 2 for idx, section in enumerate(sections)
        }

        def _section_lines(labels: list[str]) -> str:
            lines = []
            for label in labels:
                section = section_lookup.get(label)
                if not section:
                    continue
                page_count = len(section.get("pages", []))
                page_word = "page" if page_count == 1 else "pages"
                lines.append(
                    f"• {section_numbers[label]}. {section['emoji']} **{section['label']}**"
                    f" ({page_count} {page_word}): {section['summary']}"
                )
            return "\n".join(lines) if lines else "No sections available."

        return {
            "label": "Guide Index",
            "summary": "Master contents pages for the full handbook, from starter flow to endgame systems.",
            "emoji": "📖",
            "pages": [
                {
                    "title": "How To Use This Booklet",
                    "description": (
                        "Use the dropdown to jump between topics, or the buttons to read page by page."
                    ),
                    "fields": [
                        {
                            "name": "Start Here First",
                            "value": (
                                f"1. `{prefix}create`\n"
                                f"2. `{prefix}profile`\n"
                                f"3. `{prefix}race`\n"
                                f"4. `{prefix}adventures`\n"
                                f"5. `{prefix}adventure 1`\n"
                                f"6. `{prefix}status`\n"
                                f"7. `{prefix}daily` and `{prefix}vote`"
                            ),
                            "inline": False,
                        },
                        {
                            "name": "Important Early Warnings",
                            "value": (
                                f"• `{prefix}follow` is useful, but it changes luck and uses reset-point logic\n"
                                f"• `{prefix}race` should match the kind of build you want to play\n"
                                "• Do not spend heavily on random upgrades before your farming loop feels stable"
                            ),
                            "inline": False,
                        },
                    ],
                },
                {
                    "title": "New Player Command Index",
                    "description": "These are the commands most players need in their first few sessions.",
                    "fields": [
                        {
                            "name": "Character Setup",
                            "value": (
                                f"• `{prefix}create` create your character\n"
                                f"• `{prefix}profile` inspect stats, money, luck, and progress\n"
                                f"• `{prefix}race` choose your stat split\n"
                                f"• `{prefix}class` choose your class path"
                            ),
                            "inline": False,
                        },
                        {
                            "name": "Leveling and Progression",
                            "value": (
                                f"• `{prefix}adventures` preview what levels you can clear\n"
                                f"• `{prefix}adventure <level>` start an adventure run\n"
                                f"• `{prefix}status` check whether your run finished\n"
                                f"• `{prefix}xp` and `{prefix}exchange` keep your growth moving"
                            ),
                            "inline": False,
                        },
                        {
                            "name": "Free Rewards and Long-Term Systems",
                            "value": (
                                f"• `{prefix}daily` for your daily reward and streak\n"
                                f"• `{prefix}vote` for crate rewards\n"
                                f"• `{prefix}crates` / `{prefix}open <rarity>` to use those rewards\n"
                                f"• `{prefix}follow`, `{prefix}pray`, `{prefix}sacrifice` when you are ready for god systems"
                            ),
                            "inline": False,
                        },
                    ],
                },
                {
                    "title": "Leveling Basics",
                    "description": "Your character level controls how far you can push adventure content.",
                    "fields": [
                        {
                            "name": "How Leveling Works",
                            "value": (
                                "• You generally need to match the adventure number with your level to run it\n"
                                "• Better gear, race choice, class setup, and luck improve success rates\n"
                                "• Loot and rewards from your PvE loop feed back into stronger future runs"
                            ),
                            "inline": False,
                        },
                        {
                            "name": "Simple Early Loop",
                            "value": (
                                f"1. `{prefix}adventures` to find a good success chance\n"
                                f"2. `{prefix}adventure <best_level>` to run content safely\n"
                                f"3. `{prefix}status` when the timer is up\n"
                                f"4. `{prefix}exchange` loot for XP or money\n"
                                f"5. `{prefix}equip`, `{prefix}merge`, or `{prefix}upgrade` when upgrades are worth it"
                            ),
                            "inline": False,
                        },
                    ],
                },
                {
                    "title": "Early Game Index",
                    "description": "Core onboarding, routine rewards, and the systems most new players touch first.",
                    "fields": [
                        {
                            "name": "Sections",
                            "value": _section_lines(
                                [
                                    "Your Next Steps",
                                    "Getting Started",
                                    "Progression Loop",
                                    "Race & Identity",
                                    "Daily, Vote, Crates, Boosters",
                                    "Glossary & Economy Map",
                                    "Troubleshooting",
                                ]
                            ),
                            "inline": False,
                        }
                    ],
                },
                {
                    "title": "Combat and Build Index",
                    "description": "Directors for classes, PvE/PvP, gods, pets, tower systems, and challenge content.",
                    "fields": [
                        {
                            "name": "Sections",
                            "value": _section_lines(
                                [
                                    "Combat Systems",
                                    "Classes",
                                    "Gods & Favor",
                                    "Pets & Eggs",
                                    "Battle Tower Deep Dive",
                                    "Couples Battle Tower",
                                    "Ice Dragon Challenge",
                                    "PvE Pet Combat",
                                    "Egg Lifecycle",
                                ]
                            ),
                            "inline": False,
                        }
                    ],
                },
                {
                    "title": "Economy and Social Index",
                    "description": "Trading, party systems, side activities, upgrades, and leaderboard-oriented play.",
                    "fields": [
                        {
                            "name": "Sections",
                            "value": _section_lines(
                                [
                                    "Economy & Trading",
                                    "Group Play",
                                    "Advanced Systems",
                                    "Gambling & Minigames",
                                    "Gear Lifecycle Recipes",
                                    "Rankings & Achievements",
                                ]
                            ),
                            "inline": False,
                        }
                    ],
                },
                {
                    "title": "Endgame and Systems Index",
                    "description": "Late-game crafting, rotating content, and the full command directory.",
                    "fields": [
                        {
                            "name": "Sections",
                            "value": _section_lines(
                                [
                                    "Soulforge & Splice",
                                    "Seasonal & Event Systems",
                                    "Command Group Indexes",
                                    "Command Writeups",
                                    "Command Atlas",
                                ]
                            ),
                            "inline": False,
                        },
                        {
                            "name": "Navigation Note",
                            "value": (
                                "Section numbers in this index match the dropdown order. "
                                "Jump directly to any section without paging through the whole handbook."
                            ),
                            "inline": False,
                        },
                    ],
                },
            ],
        }

    def _build_guidebook_sections(self, prefix: str, profile_row=None) -> list[dict]:
        class_lines = ", ".join(
            self._humanize_class_line(name) for name in sorted(ALL_CLASSES_TYPES.keys())
        )
        commands_by_cog, ordered_cogs = self._collect_public_command_metadata(prefix)
        command_atlas_pages = self._build_command_atlas_pages(prefix)
        command_group_index_pages = self._build_command_group_indexes(
            prefix, commands_by_cog, ordered_cogs
        )
        command_writeup_pages = self._build_command_writeup_pages(
            prefix, commands_by_cog, ordered_cogs
        )
        total_public_commands = sum(len(entries) for entries in commands_by_cog.values())
        total_public_cogs = len(commands_by_cog)

        god_names = "Configured by your server admins."
        gods = getattr(self.bot, "gods", None)
        if isinstance(gods, dict) and gods:
            names = sorted(
                {
                    str(god.get("name")).strip()
                    for god in gods.values()
                    if isinstance(god, dict) and god.get("name")
                }
            )
            if names:
                god_names = ", ".join(names)

        matchup_lines = "\n".join(
            [
                "• **Light** > **Corrupted**",
                "• **Dark** > **Light**",
                "• **Corrupted** > **Dark**",
                "• **Nature** > **Electric**",
                "• **Electric** > **Water**",
                "• **Water** > **Fire**",
                "• **Fire** > **Nature**",
                "• **Wind** > **Electric**",
            ]
        )
        pet_metrics = self._get_pet_guide_metrics()
        dragon_guide = self._get_dragon_stage_guide_data()

        trust_tiers = sorted(
            pet_metrics.get("trust_tiers", []), key=lambda item: item.get("threshold", 0)
        )
        trust_lines = []
        for idx, tier in enumerate(trust_tiers):
            start = int(tier.get("threshold", 0))
            end = 100
            if idx + 1 < len(trust_tiers):
                end = max(start, int(trust_tiers[idx + 1].get("threshold", 100)) - 1)
            bonus = int(tier.get("bonus", 0))
            bonus_display = f"+{bonus}" if bonus > 0 else str(bonus)
            emoji = str(tier.get("emoji", "")).strip()
            name = str(tier.get("name", f"Tier {start}"))
            trust_lines.append(
                f"• {emoji} **{name}** ({start}-{end}): {bonus_display}% battle stats"
            )
        trust_tiers_text = "\n".join(trust_lines) if trust_lines else "Trust tiers unavailable."

        skill_unlocks_text = ", ".join(
            str(level) for level in pet_metrics.get("skill_unlock_levels", [])
        )
        skill_costs_text = ", ".join(
            str(cost) for cost in pet_metrics.get("skill_cost_values", [])
        )
        dragon_stage_lines = "\n".join(
            f"• **{stage['name']}**: levels {stage['min_level']}-{stage['max_level']}"
            for stage in dragon_guide.get("stages", [])
        )

        sections = [
            self._build_next_steps_section(prefix, profile_row),
            {
                "label": "Getting Started",
                "summary": "Create your character and set up your first progression routine.",
                "emoji": "🚀",
                "pages": [
                    {
                        "title": "First Login Checklist",
                        "description": (
                            f"1. `{prefix}create` to make your character\n"
                            f"2. `{prefix}profile` to inspect baseline stats\n"
                            f"3. `{prefix}race` to lock in your early stat identity\n"
                            f"4. `{prefix}inventory`, `{prefix}items`, `{prefix}loot`\n"
                            f"5. `{prefix}adventures` to preview success rates\n"
                            f"6. `{prefix}adventure <level>` to start progression"
                        ),
                        "fields": [
                            {
                                "name": "Goal",
                                "value": (
                                    "Build a stable cycle of XP + gold + gear before spending heavily."
                                ),
                                "inline": False,
                            },
                            {
                                "name": "Immediate Free Value",
                                "value": (
                                    f"• `{prefix}daily` for your daily reward\n"
                                    f"• `{prefix}vote` for crate income\n"
                                    f"• `{prefix}status` after every adventure so runs do not sit idle"
                                ),
                                "inline": False,
                            }
                        ],
                    },
                    {
                        "title": "Basic Command Index",
                        "description": "Grouped starter commands so new players can learn the game in chunks.",
                        "fields": [
                            {
                                "name": "Build Your Character",
                                "value": (
                                    f"• `{prefix}create`\n"
                                    f"• `{prefix}profile`\n"
                                    f"• `{prefix}race`\n"
                                    f"• `{prefix}class`"
                                ),
                                "inline": False,
                            },
                            {
                                "name": "Start Playing",
                                "value": (
                                    f"• `{prefix}adventures`\n"
                                    f"• `{prefix}adventure <level>`\n"
                                    f"• `{prefix}status`\n"
                                    f"• `{prefix}xp`"
                                ),
                                "inline": False,
                            },
                            {
                                "name": "Income and Rewards",
                                "value": (
                                    f"• `{prefix}daily`\n"
                                    f"• `{prefix}vote`\n"
                                    f"• `{prefix}crates`\n"
                                    f"• `{prefix}open <rarity>`\n"
                                    f"• `{prefix}exchange`"
                                ),
                                "inline": False,
                            },
                            {
                                "name": "Optional But Important",
                                "value": (
                                    f"• `{prefix}follow` once you understand luck/favor\n"
                                    f"• `{prefix}pray` and `{prefix}sacrifice` to build favor\n"
                                    f"• `{prefix}help <command>` whenever you need command-specific details"
                                ),
                                "inline": False,
                            },
                        ],
                    },
                    {
                        "title": "Syntax and Reading Help",
                        "description": (
                            "• `<arg>` required, `[arg]` optional, `...` repeatable\n"
                            f"• Use `{prefix}help <command>` for full docs\n"
                            f"• Use `{prefix}help module <name>` for category docs"
                        ),
                        "fields": [
                            {
                                "name": "Example",
                                "value": (
                                    f"`{prefix}trade add consumable weapon_element_scroll 1`\n"
                                    f"`{prefix}consume weapelement <item_id> Fire`"
                                ),
                                "inline": False,
                            }
                        ],
                    },
                    {
                        "title": "First 7 Days Plan",
                        "description": "Structured startup route so new players do not waste resources early.",
                        "fields": [
                            {
                                "name": "Days 1-2",
                                "value": (
                                    f"• Create + baseline: `{prefix}create`, `{prefix}profile`, `{prefix}inventory`\n"
                                    f"• Start PvE loop: `{prefix}adventures`, `{prefix}adventure <best_level>`\n"
                                    f"• Daily routine: `{prefix}daily`, `{prefix}vote`, `{prefix}status`"
                                ),
                                "inline": False,
                            },
                            {
                                "name": "Days 3-4",
                                "value": (
                                    f"• Stabilize gear: `{prefix}equip`, `{prefix}merge`, `{prefix}upgrade`\n"
                                    f"• Start pet prep: farm PvE, monitor eggs with `{prefix}pets eggs`\n"
                                    f"• Add basic economy flow: `{prefix}sell`, `{prefix}market`, `{prefix}trade`"
                                ),
                                "inline": False,
                            },
                            {
                                "name": "Days 5-7",
                                "value": (
                                    f"• Unlock consistency layers: `{prefix}battletower`, raidstats, presets\n"
                                    f"• Begin pet investment: `{prefix}pets status`, `{prefix}pets skills`, `{prefix}pets learn`\n"
                                    "• Shift from random spending to build-focused upgrades only"
                                ),
                                "inline": False,
                            },
                        ],
                    },
                ],
            },
            {
                "label": "Progression Loop",
                "summary": "Understand your early-to-late game growth loop.",
                "emoji": "📈",
                "pages": [
                    {
                        "title": "Core Loop",
                        "description": (
                            "Run content -> gain XP/gear/loot -> upgrade/equip -> push harder content."
                        ),
                        "fields": [
                            {
                                "name": "Daily Rhythm",
                                "value": (
                                    f"• `{prefix}profile` and `{prefix}inventory`\n"
                                    f"• `{prefix}adventures` -> `{prefix}adventure <best_level>`\n"
                                    f"• `{prefix}status` while adventure runs\n"
                                    f"• `{prefix}exchange` and gear updates\n"
                                    f"• Optional: `{prefix}battle`, `{prefix}battletower fight`"
                                ),
                                "inline": False,
                            },
                            {
                                "name": "Milestones",
                                "value": (
                                    "• Level 12 unlocks second class slot\n"
                                    "• Build predictable income before expensive upgrades\n"
                                    "• Add group/raid progression when solo loop is stable"
                                ),
                                "inline": False,
                            },
                        ],
                    }
                ],
            },
            {
                "label": "Combat Systems",
                "summary": "PvE, PvP, Battle Tower, raid multipliers, and loadout control.",
                "emoji": "⚔️",
                "pages": [
                    {
                        "title": "Main Combat Commands",
                        "description": (
                            f"• `{prefix}battle` (standard PvP)\n"
                            f"• `{prefix}raidbattle` (raidstats-influenced)\n"
                            f"• `{prefix}raidbattle2v2` (team mode)\n"
                            f"• `{prefix}scout` (preview PvE target)\n"
                            f"• `{prefix}battletower start/progress/fight`"
                        ),
                        "fields": [
                            {
                                "name": "Raid Growth Commands",
                                "value": (
                                    f"• `{prefix}increase damage`\n"
                                    f"• `{prefix}increase defense`\n"
                                    f"• `{prefix}increase health`\n"
                                    f"• `{prefix}raidstats` (`{prefix}rs`)"
                                ),
                                "inline": False,
                            }
                        ],
                    },
                    {
                        "title": "Elements and Matchups",
                        "description": matchup_lines,
                        "fields": [
                            {
                                "name": "Modifier Behavior",
                                "value": (
                                    "Advantage generally adds about +10% to +30% damage.\n"
                                    "Disadvantage generally applies about -10% to -30%."
                                ),
                                "inline": False,
                            },
                            {
                                "name": "Element Control",
                                "value": (
                                    f"Use `{prefix}consume weapelement <item_id> <element>` to change a weapon element."
                                ),
                                "inline": False,
                            },
                        ],
                    },
                ],
            },
        ]
        sections.extend(
            [
                {
                    "label": "Classes",
                    "summary": "Class lines, evolution, and role-based progression.",
                    "emoji": "🏹",
                    "pages": [
                        {
                            "title": "Class Families",
                            "description": class_lines,
                            "fields": [
                                {
                                    "name": "Core Commands",
                                    "value": (
                                        f"• `{prefix}class` choose/change classes\n"
                                        f"• `{prefix}myclass` inspect your current classes\n"
                                        f"• `{prefix}evolve` evolve class rank\n"
                                        f"• `{prefix}tree` view class trees"
                                    ),
                                    "inline": False,
                                }
                            ],
                        },
                        {
                            "title": "Class Strategy",
                            "description": (
                                "Pick one reliable farming line first, then build synergy with your second slot."
                            ),
                            "fields": [
                                {
                                    "name": "Practical Notes",
                                    "value": (
                                        "• Second class slot unlocks at level 12\n"
                                        "• Some lines unlock utility commands (steal/bless/gift etc.)\n"
                                        "• Avoid frequent class switching until your economy is stable"
                                    ),
                                    "inline": False,
                                }
                            ],
                        },
                    ],
                },
                {
                    "label": "Gods & Favor",
                    "summary": "Follow gods, earn favor, and manage luck-related effects.",
                    "emoji": "🙏",
                    "pages": [
                        {
                            "title": "God System Basics",
                            "description": f"Configured gods: {god_names}",
                            "fields": [
                                {
                                    "name": "Core Commands",
                                    "value": (
                                        f"• `{prefix}follow`\n"
                                        f"• `{prefix}pray`\n"
                                        f"• `{prefix}sacrifice`\n"
                                        f"• `{prefix}favor` / `{prefix}followers`"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Important Rules",
                                    "value": (
                                        "• God choices interact with reset points\n"
                                        "• Godless state can permanently restrict follow actions\n"
                                        "• Favor is best built consistently over time"
                                    ),
                                    "inline": False,
                                },
                            ],
                        }
                    ],
                },
                {
                    "label": "Pets & Eggs",
                    "summary": "Pet growth, aliases, egg flow, and pet-specific trading.",
                    "emoji": "🐾",
                    "pages": [
                        {
                            "title": "Pet Command Core",
                            "description": (
                                f"• `{prefix}pets`\n"
                                f"• `{prefix}pets rename <pet_id|alias> [nickname]`\n"
                                f"• `{prefix}pets alias <pet_id|alias> <alias|clear>`\n"
                                f"• `{prefix}pets status <id|alias>`\n"
                                f"• `{prefix}pets skills <id|alias>`\n"
                                f"• `{prefix}pets learn <id|alias> <skill_name>`\n"
                                f"• `{prefix}pets trade ...` / `{prefix}pets sell ...`"
                            ),
                            "fields": [
                                {
                                    "name": "Growth Basics",
                                    "value": (
                                        "Stages: Baby -> Juvenile -> Young -> Adult\n"
                                        "Default stage timing is approximately 2d / 2d / 1d before adult."
                                    ),
                                    "inline": False,
                                }
                            ],
                        },
                        {
                            "title": "Pet Leveling Math",
                            "description": "Pet progression uses cubic XP thresholds and milestone skill points.",
                            "fields": [
                                {
                                    "name": "Core Formula",
                                    "value": (
                                        f"• Max pet level: **{pet_metrics['max_level']}**\n"
                                        f"• XP threshold for level `N`: `int({pet_metrics['xp_curve_multiplier']} * N^3)`\n"
                                        f"• Skill points: +1 every `{pet_metrics['skill_point_interval']}` levels"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Reference Thresholds",
                                    "value": (
                                        f"• Level 10 threshold: `int({pet_metrics['xp_curve_multiplier']} * 10^3)` = **{int(pet_metrics['xp_curve_multiplier'] * (10 ** 3)):,} XP**\n"
                                        f"• Level 50 threshold: `int({pet_metrics['xp_curve_multiplier']} * 50^3)` = **{int(pet_metrics['xp_curve_multiplier'] * (50 ** 3)):,} XP**\n"
                                        f"• Level 100 threshold: `int({pet_metrics['xp_curve_multiplier']} * 100^3)` = **{int(pet_metrics['xp_curve_multiplier'] * (100 ** 3)):,} XP**"
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                        {
                            "title": "Trust Tiers and Battle Multipliers",
                            "description": "Battle stats scale from both level multiplier and trust multiplier.",
                            "fields": [
                                {
                                    "name": "Trust Tiers",
                                    "value": trust_tiers_text,
                                    "inline": False,
                                },
                                {
                                    "name": "Final Stat Model",
                                    "value": (
                                        f"`battle_stat = base_stat * (1 + level * {pet_metrics['level_stat_bonus_pct'] / 100:.2f}) * (1 + trust_bonus/100)`\n"
                                        f"At level {pet_metrics['max_level']}, level multiplier alone is about **x{1 + (pet_metrics['max_level'] * (pet_metrics['level_stat_bonus_pct'] / 100)):.2f}**."
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                        {
                            "title": "Skill Tree Architecture",
                            "description": "Element-based skill trees provide structured build paths.",
                            "fields": [
                                {
                                    "name": "Structure",
                                    "value": (
                                        f"• Elements: **{pet_metrics['skill_elements']}**\n"
                                        f"• Branches per element: **{pet_metrics['skill_branches_per_element']}**\n"
                                        f"• Skills per branch: **{pet_metrics['skills_per_branch']}**\n"
                                        "• Typical branch families follow offense, control/support, and specialty themes"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Command Route",
                                    "value": (
                                        f"1. `{prefix}pets status <pet>`\n"
                                        f"2. `{prefix}pets skills <pet>`\n"
                                        f"3. `{prefix}pets skillinfo <skill_name>`\n"
                                        f"4. `{prefix}pets learn <pet> <skill_name>`"
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                        {
                            "title": "Skill Costs, Unlock Levels, and Battery Life",
                            "description": "Skill learning uses fixed unlock bands and cost bands.",
                            "fields": [
                                {
                                    "name": "Unlock + Cost Bands",
                                    "value": (
                                        f"• Unlock levels: **{skill_unlocks_text}**\n"
                                        f"• Base costs by tier: **{skill_costs_text} SP**\n"
                                        "• Typical mapping: Lv1->1SP, Lv3->2SP, Lv5->3SP, Lv7->4SP, Lv10->5SP"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Battery Life Discount Rule",
                                    "value": (
                                        "If pet knows **Battery Life**:\n"
                                        "• Skills costing 4+ SP are reduced by 2\n"
                                        "• Skills costing 1-3 SP are reduced by 1\n"
                                        "• Cost floor remains 1 SP"
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                        {
                            "title": "Care Decay and Failure States (Death/Runaway)",
                            "description": "Ignoring care is a real loss condition, not cosmetic flavor.",
                            "fields": [
                                {
                                    "name": "Decay Rates (per hour)",
                                    "value": (
                                        "• Baby: Hunger ~0.83, Happiness ~0.42\n"
                                        "• Juvenile: Hunger ~0.67, Happiness ~0.33\n"
                                        "• Young: Hunger ~0.50, Happiness ~0.25\n"
                                        "• Adult: no hunger decay from this growth-stage model"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Failure Outcomes",
                                    "value": (
                                        "• Hunger reaches 0 -> starvation death flow\n"
                                        "• Happiness reaches 0 -> runaway flow\n"
                                        "• Both outcomes remove ownership and are effectively permanent losses"
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                        {
                            "title": "Pet Build Archetypes",
                            "description": "Use role-driven builds instead of random skill picks.",
                            "fields": [
                                {
                                    "name": "Common Archetypes",
                                    "value": (
                                        "• **Farm Carry**: trust consistency + stable damage branch picks\n"
                                        "• **Tank Utility**: defensive/control branch + survival passives\n"
                                        "• **Burst Finisher**: high-cost spike skills, lower sustained value\n"
                                        "• **Support Hybrid**: team buffs, debuff pressure, sustain utility"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Build Rule",
                                    "value": (
                                        "Pick one primary role per pet first, then only add cross-role skills if they solve a known fight breakpoint."
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                    ],
                },
                {
                    "label": "Economy & Trading",
                    "summary": "Market commands and direct player trade session workflows.",
                    "emoji": "💰",
                    "pages": [
                        {
                            "title": "Market + Offers",
                            "description": (
                                f"• `{prefix}sell <item_id> <price>`\n"
                                f"• `{prefix}buy <offer_id>`\n"
                                f"• `{prefix}shop` / `{prefix}market`\n"
                                f"• `{prefix}offer <item_id> <user> <price>`"
                            ),
                            "fields": [
                                {
                                    "name": "Bulk / Safety",
                                    "value": (
                                        f"• `{prefix}merch` / `{prefix}merchall`\n"
                                        f"• `{prefix}lock <item_id>` and `{prefix}unlock <item_id>`"
                                    ),
                                    "inline": False,
                                }
                            ],
                        },
                        {
                            "title": "Player Trade Sessions",
                            "description": (
                                f"• `{prefix}trade <user>`\n"
                                f"• `{prefix}trade add/set/remove money|item|resources|consumable ...`"
                            ),
                            "fields": [
                                {
                                    "name": "Tradable Premium Consumables",
                                    "value": (
                                        "• pet_age_potion\n"
                                        "• pet_speed_growth_potion\n"
                                        "• pet_mind_wipe\n"
                                        "• pet_element_scroll\n"
                                        "• splice_final_potion\n"
                                        "• weapon_element_scroll"
                                    ),
                                    "inline": False,
                                }
                            ],
                        },
                    ],
                },
                {
                    "label": "Group Play",
                    "summary": "Guild/alliance progression and organized raids/tournaments.",
                    "emoji": "🏰",
                    "pages": [
                        {
                            "title": "Social Progression Systems",
                            "description": (
                                f"• `{prefix}guild` for guild command group\n"
                                f"• `{prefix}alliance` for alliance command group\n"
                                f"• `{prefix}raidstats` and raid command suite\n"
                                f"• `{prefix}tournament` family of commands"
                            ),
                            "fields": [
                                {
                                    "name": "Why Join Group Content",
                                    "value": (
                                        "Group systems unlock shared progression, coordinated events, and stronger long-run efficiency."
                                    ),
                                    "inline": False,
                                }
                            ],
                        }
                    ],
                },
                {
                    "label": "Advanced Systems",
                    "summary": "Amulets, presets, and loadout optimization.",
                    "emoji": "🛠️",
                    "pages": [
                        {
                            "title": "Build Optimization",
                            "description": (
                                f"• `{prefix}amulet help`\n"
                                f"• `{prefix}amulet resources`\n"
                                f"• `{prefix}amulet craft/equip/unequip`\n"
                                f"• `{prefix}preset` command group for quick loadout swaps"
                            ),
                            "fields": [
                                {
                                    "name": "Optimization Pattern",
                                    "value": (
                                        "Maintain a safe farming loadout and a high-risk push loadout; switch with presets."
                                    ),
                                    "inline": False,
                                }
                            ],
                        }
                    ],
                },
                {
                    "label": "Race & Identity",
                    "summary": "Race stats, identity setup, and profile-facing systems.",
                    "emoji": "🧬",
                    "pages": [
                        {
                            "title": "Race Selection",
                            "description": f"Use `{prefix}race` to pick or change race (cooldown + reset-point constraints apply).",
                            "fields": [
                                {
                                    "name": "Race Stat Splits",
                                    "value": (
                                        "• Orc: +4 DEF, +0 ATK\n"
                                        "• Dwarf: +3 DEF, +1 ATK\n"
                                        "• Human: +2 DEF, +2 ATK\n"
                                        "• Elf: +1 DEF, +3 ATK\n"
                                        "• Jikill: +0 DEF, +4 ATK\n"
                                        "• Shadeborn: +5 DEF, -1 ATK\n"
                                        "• Djinn: -1 DEF, +5 ATK"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "When To Change",
                                    "value": (
                                        "Swap race only when your build focus changes significantly "
                                        "(e.g., survivability push vs burst offense)."
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                        {
                            "title": "Identity Commands",
                            "description": "Manage how your character appears and behaves in profile systems.",
                            "fields": [
                                {
                                    "name": "Useful Commands",
                                    "value": (
                                        f"• `{prefix}rename` character name\n"
                                        f"• `{prefix}profilepref` profile display settings\n"
                                        f"• `{prefix}color` profile color\n"
                                        f"• `{prefix}badges`\n"
                                        f"• `{prefix}public` / `{prefix}private` API visibility"
                                    ),
                                    "inline": False,
                                }
                            ],
                        },
                    ],
                },
                {
                    "label": "Daily, Vote, Crates, Boosters",
                    "summary": "High-value recurring rewards and passive acceleration systems.",
                    "emoji": "🎁",
                    "pages": [
                        {
                            "title": "Recurring Reward Loop",
                            "description": "These commands should be part of your default login routine.",
                            "fields": [
                                {
                                    "name": "Core Commands",
                                    "value": (
                                        f"• `{prefix}daily` (daily reward + streak systems)\n"
                                        f"• `{prefix}vote` (random crate rewards)\n"
                                        f"• `{prefix}streak` / streak restore commands\n"
                                        f"• `{prefix}crates` and `{prefix}open <rarity> [amount]`"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Crate Quick Facts",
                                    "value": (
                                        "Common -> Legendary -> Divine scaling exists.\n"
                                        "Fortune/Mystery/Materials crates have special reward logic."
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                        {
                            "title": "Booster Economy",
                            "description": (
                                f"`{prefix}store`, `{prefix}purchase`, `{prefix}boosters`, `{prefix}activate`"
                            ),
                            "fields": [
                                {
                                    "name": "Booster Effects",
                                    "value": (
                                        "• Time: reduces adventure completion time\n"
                                        "• Luck: improves adventure outcome chances\n"
                                        "• Money: increases adventure gold rewards\n"
                                        "• Duration: generally 24 hours after activation"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Activation Strategy",
                                    "value": (
                                        "Use boosters before long play sessions or batch adventure runs "
                                        "to maximize return per unit of time."
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                    ],
                },
                {
                    "label": "Gambling & Minigames",
                    "summary": "Betting commands, limits, and player-vs-player chance games.",
                    "emoji": "🎲",
                    "pages": [
                        {
                            "title": "Core Gambling Commands",
                            "description": "Most money games require a character profile and available balance.",
                            "fields": [
                                {
                                    "name": "Money Bets",
                                    "value": (
                                        f"• `{prefix}flip [heads|tails] [amount]`\n"
                                        f"• `{prefix}bet [maximum] [tip] [money]`\n"
                                        f"• `{prefix}blackjack [amount]`\n"
                                        f"• `{prefix}roulette <money> <bid>`\n"
                                        f"• `{prefix}farkle [bet]`"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Social and Fun Games",
                                    "value": (
                                        f"• `{prefix}pokerdraw [money] [enemy]` (`{prefix}pd`)\n"
                                        f"• `{prefix}dos [user]` (`{prefix}doubleorsteal`)\n"
                                        f"• `{prefix}fivecarddraw` (`{prefix}fc`)\n"
                                        f"• `{prefix}slots`\n"
                                        f"• `{prefix}8ball <question>`\n"
                                        f"• `{prefix}roulette table`, `{prefix}farklehelp`"
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                        {
                            "title": "Bet Limits and Payout Notes",
                            "description": "Hard caps are enforced by command validators and command logic.",
                            "fields": [
                                {
                                    "name": "Bet Limits",
                                    "value": (
                                        "• Flip: 0 to 250,000 (`all` supported, capped at 250,000)\n"
                                        "• Bet: money 0 to 100,000, and `money * (maximum - 1)` must stay <= 100,000\n"
                                        "• Blackjack: 0 to 5,000\n"
                                        "• Roulette: 0 to 100,000 (non red/black bids capped at 25,000)\n"
                                        "• Farkle: up to 250,000"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Payout Rules",
                                    "value": (
                                        "• Flip: correct side wins stake amount, wrong side loses stake\n"
                                        "• Bet: win payout is `(maximum - 1) * money`, loss is `money`\n"
                                        "• Blackjack: normal win pays 1x, natural blackjack pays 1.5x\n"
                                        "• Roulette: payout depends on bid type (inside/outside odds)\n"
                                        "• Double-or-Steal: starts from a $100 pot and escalates by player choice"
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                        {
                            "title": "Risk Management Checklist",
                            "description": "Use these steps to prevent one bad streak from collapsing your progression.",
                            "fields": [
                                {
                                    "name": "Safe Session Routine",
                                    "value": (
                                        f"1. Check bankroll with `{prefix}profile`\n"
                                        "2. Set a hard loss limit before betting\n"
                                        "3. Use small bets while learning each command's pacing\n"
                                        "4. Stop when you hit your limit; switch back to farming/progression loops"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Cooldown Awareness",
                                    "value": (
                                        "Most gambling commands have short cooldowns (about 4-15 seconds).\n"
                                        "Treat fast rerolls as variance pressure, not guaranteed recovery."
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                    ],
                },
                {
                    "label": "Gear Lifecycle Recipes",
                    "summary": "Exact command sequences for farming, upgrading, and selling safely.",
                    "emoji": "🔧",
                    "pages": [
                        {
                            "title": "Safe Upgrade Recipe",
                            "description": "Use this when you are unsure which item to invest into.",
                            "fields": [
                                {
                                    "name": "Sequence",
                                    "value": (
                                        f"1. `{prefix}inventory` and `{prefix}items`\n"
                                        f"2. `{prefix}equip <best_ids>`\n"
                                        f"3. `{prefix}merge <id1> <id2>` for weaker duplicates\n"
                                        f"4. `{prefix}upgrade <best_item_id>`\n"
                                        f"5. `{prefix}lock <best_item_id>` to prevent accidental sale"
                                    ),
                                    "inline": False,
                                }
                            ],
                        },
                        {
                            "title": "Market / Trade Safety Recipe",
                            "description": "Avoid item loss and bad pricing mistakes.",
                            "fields": [
                                {
                                    "name": "Before Selling",
                                    "value": (
                                        f"• Verify equipped state, then `{prefix}unlock` if needed\n"
                                        f"• Check value floors before `{prefix}sell`\n"
                                        f"• Use `{prefix}offer` for direct buyer-targeted sales"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Before Trading",
                                    "value": (
                                        f"• Start with `{prefix}trade <user>`\n"
                                        "• Add only what you can afford to lose\n"
                                        "• Re-read final trade state before accepting ✅"
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                    ],
                },
                {
                    "label": "Battle Tower Deep Dive",
                    "summary": "Progress, prestige, hidden-door progression, and run planning.",
                    "emoji": "🗼",
                    "pages": [
                        {
                            "title": "Tower Fundamentals",
                            "description": (
                                f"Use `{prefix}battletower start`, `{prefix}battletower progress`, `{prefix}battletower fight`."
                            ),
                            "fields": [
                                {
                                    "name": "What To Track",
                                    "value": (
                                        "• Floor level and prestige level\n"
                                        "• Run keys (3-key run progress)\n"
                                        "• Freedom meter / hidden-door readiness\n"
                                        "• Reward checkpoints (every 5 floors)"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Quality of Life",
                                    "value": (
                                        f"• `{prefix}battletower toggle_dialogue` for faster grinding\n"
                                        "• Keep a dedicated tower loadout/preset"
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                        {
                            "title": "Prestige and Long-Run Strategy",
                            "description": "Treat prestige as a long-cycle optimization layer, not a quick reset button.",
                            "fields": [
                                {
                                    "name": "Practical Strategy",
                                    "value": (
                                        "• Stabilize clear speed before prestige loops\n"
                                        "• Record floors where builds fail and patch those breakpoints\n"
                                        "• Use tower + element tuning together for consistency"
                                    ),
                                    "inline": False,
                                }
                            ],
                        },
                    ],
                },
                {
                    "label": "Couples Battle Tower",
                    "summary": "Married-duo tower rules, level flow, and rewards without guesswork.",
                    "emoji": "💞",
                    "pages": [
                        {
                            "title": "Entry Flow and Commands",
                            "description": (
                                f"• `{prefix}couples_battletower` / `{prefix}cbt` opens progress\n"
                                f"• `{prefix}cbt start` or `{prefix}cbt begin` starts a run\n"
                                f"• `{prefix}cbt progress`, `{prefix}cbt preview <level>`, `{prefix}cbt dialogue [level]`\n"
                                f"• `{prefix}cbt help` for the in-mode primer"
                            ),
                            "fields": [
                                {
                                    "name": "Requirements",
                                    "value": (
                                        "• You must be married\n"
                                        "• Both partners must join the same run\n"
                                        "• If one partner is already in combat, run start is blocked"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Cooldown Model",
                                    "value": (
                                        "• `start`: 1 hour cooldown mirrored to both partners\n"
                                        "• `begin`: 5 minute cooldown mirrored to both partners\n"
                                        "• If partner does not join, cancellation path resets the shared cooldown"
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                        {
                            "title": "Mechanics You Must Respect",
                            "description": "This mode has stricter fail conditions than standard tower.",
                            "fields": [
                                {
                                    "name": "Core Rule",
                                    "value": (
                                        "If either partner dies, the run ends immediately on most floors.\n"
                                        "Special exceptions exist on a few floors (for example, level 29 spirit-heal behavior)."
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Pre-Battle Dialogue Matters",
                                    "value": (
                                        "Couples floors include scripted mechanics pages before fights.\n"
                                        "Use preview/dialogue commands when a floor keeps failing; many gimmicks are explained there."
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                        {
                            "title": "Rewards, Progress, and Prestige",
                            "description": "30-floor couple progression with checkpoint rewards and finale flow.",
                            "fields": [
                                {
                                    "name": "Progression Structure",
                                    "value": (
                                        "• Floors 1-29 are combat with floor-specific rules\n"
                                        "• Floor 30 is a finale/ceremony flow\n"
                                        "• Major rewards appear at checkpoint floors (not every floor)"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Long-Run Loop",
                                    "value": (
                                        "• Re-runs stack prestige progression over time\n"
                                        f"• Track performance with `{prefix}cbt progress`\n"
                                        f"• Check the leaderboard with `{prefix}coupleslb` / `{prefix}cbtlb`"
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                    ],
                },
                {
                    "label": "Ice Dragon Challenge",
                    "summary": "Weekly scaling raid-boss system with party setup, stages, and drops.",
                    "emoji": "❄️",
                    "pages": [
                        {
                            "title": "Command Surface",
                            "description": (
                                f"• `{prefix}dragonchallenge` shows current dragon status\n"
                                f"• Aliases: `{prefix}dragon`, `{prefix}idc`, `{prefix}d`\n"
                                f"• `{prefix}dragonchallenge party` (`{prefix}dragonchallenge p`) forms a party\n"
                                f"• `{prefix}dragonchallenge leaderboard` (`{prefix}dragonchallenge lb`)"
                            ),
                            "fields": [
                                {
                                    "name": "Party Rules",
                                    "value": (
                                        "• Up to 4 players in one challenge\n"
                                        "• Party leader controls challenge start\n"
                                        "• Party creation is timed, so gather teammates before pressing start"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Cooldown",
                                    "value": "Party start command has a 2-hour user cooldown.",
                                    "inline": False,
                                },
                            ],
                        },
                        {
                            "title": "Stage Bands Quick Reference",
                            "description": "Dragon stages are level-banded and determine move/passive profiles.",
                            "fields": [
                                {
                                    "name": "Default Stage Bands",
                                    "value": dragon_stage_lines or "Stage data unavailable.",
                                    "inline": False,
                                },
                                {
                                    "name": "Data Source",
                                    "value": (
                                        "Live stage definitions are DB-driven in the dragon extension.\n"
                                        "If DB stage data is unavailable, the fallback stage map is used."
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                        {
                            "title": "40-Defeat Weekly Leveling Loop",
                            "description": "Dragon level progression is tied to aggregate weekly defeats.",
                            "fields": [
                                {
                                    "name": "Progress Rule",
                                    "value": (
                                        f"• Defeats required per level: **{dragon_guide['defeats_per_level']}**\n"
                                        "• Weekly defeat counter increases on each successful party kill\n"
                                        "• On level-up, weekly defeat counter resets for the next cycle"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Why This Matters",
                                    "value": (
                                        "The mode rewards consistency over burst grinding. Build a weekly farming rhythm, not sporadic all-in pushes."
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                        {
                            "title": "Weekly Reset Behavior",
                            "description": "Weekly reset logic primarily clears weekly defeat progress.",
                            "fields": [
                                {
                                    "name": "Reset Window",
                                    "value": (
                                        f"• Reset cadence: roughly every **{dragon_guide['weekly_reset_days']} days**\n"
                                        "• Weekly defeats are reset to 0 at reset\n"
                                        "• Last reset timestamp is updated for the next cycle check"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Player Planning",
                                    "value": (
                                        "Plan coordinated clears early in the reset cycle. Late-cycle starts often waste setup and party assembly time."
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                        {
                            "title": "Rewards Matrix",
                            "description": "Dragon rewards scale by level and party slot, with stage-aware drop rolls.",
                            "fields": [
                                {
                                    "name": "Base Reward Formula",
                                    "value": (
                                        "• Money baseline: `1000 * dragon_level`\n"
                                        "• XP baseline: `500 * dragon_level`\n"
                                        "• Party position applies divisor (`/1`, `/2`, `/3`, `/4`) for per-member split"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Drop + Bonus Layer",
                                    "value": (
                                        "• Weapon drops are stage/global table driven with min/max chance bounds\n"
                                        "• Effective chance grows with level bonus and respects max-chance caps\n"
                                        f"• Dragon Coin party bonus: **{dragon_guide['dragon_coin_chance_percent']}%** chance, "
                                        f"**{dragon_guide['dragon_coin_min']}-{dragon_guide['dragon_coin_max']}** each member"
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                        {
                            "title": "Party Formation and Failure Handling",
                            "description": "Party management is strict to prevent stale/chained challenge abuse.",
                            "fields": [
                                {
                                    "name": "Control Rules",
                                    "value": (
                                        "• Party leader (or linked main/alt) controls challenge start\n"
                                        "• Formation has timeout behavior; if it expires, start is canceled\n"
                                        "• Players are locked in-fight during battle lifecycle and released after resolution"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Team Advice",
                                    "value": (
                                        "Use complementary roles (damage, sustain, utility) and bring battle-ready pets for better turn pressure."
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                    ],
                },
                {
                    "label": "PvE Pet Combat",
                    "summary": "How pets join battles, scale, and gain capped battle XP.",
                    "emoji": "🐾",
                    "pages": [
                        {
                            "title": "How Battle XP Is Awarded",
                            "description": "Battle XP is routed to a default active pet target each win.",
                            "fields": [
                                {
                                    "name": "Award Route",
                                    "value": (
                                        "1. Equipped pet is preferred\n"
                                        "2. If no equipped pet and you own exactly one pet, that pet is used\n"
                                        "3. If no valid active pet target exists, pet battle XP is skipped"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Per-Win XP Formula",
                                    "value": (
                                        f"`pet_battle_xp = {pet_metrics['battle_xp_base']} + ({pet_metrics['battle_xp_per_tier']} * monster_tier)`\n"
                                        "This is computed before daily cap handling."
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                        {
                            "title": "Daily Battle XP Cap and Cap-Reached Behavior",
                            "description": "Pet battle XP is intentionally capped to control runaway growth.",
                            "fields": [
                                {
                                    "name": "Daily Cap",
                                    "value": (
                                        f"• Daily pet battle XP cap: **{pet_metrics['battle_daily_xp_cap']:,}** per user\n"
                                        "• Remaining daily budget is consumed by each valid battle award\n"
                                        "• If requested XP exceeds remaining budget, award is truncated to remaining amount"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "After Cap",
                                    "value": (
                                        "When cap is reached, battles still finish normally, but additional pet battle XP is blocked until daily reset."
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                        {
                            "title": "Combat Participation Rules Across PvE/Raid/Dragon/Tower",
                            "description": (
                                f"• `{prefix}pets equip <id|alias>` to enable battle participation\n"
                                f"• `{prefix}pets unequip` to disable\n"
                                "• Equipped pet must be at least Young stage"
                            ),
                            "fields": [
                                {
                                    "name": "Mode Coverage",
                                    "value": (
                                        "Equipped pets are pulled into supported battle types through the battle factory "
                                        "(PvE, raids, dragon, tower variants, and related systems)."
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Setup Checklist",
                                    "value": (
                                        f"• Use `{prefix}pets status <pet>` to inspect readiness\n"
                                        f"• Use `{prefix}pets equip <pet>` before pushing difficult modes\n"
                                        f"• Use `{prefix}pets skills` + `{prefix}pets learn` to specialize role"
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                    ],
                },
                {
                    "label": "Egg Lifecycle",
                    "summary": "Drop chances, hatching timeline, growth stages, and slot management.",
                    "emoji": "🥚",
                    "pages": [
                        {
                            "title": "Egg Drop Chance Model by PvE Level",
                            "description": "Egg rolls happen on PvE wins with explicit level-based rates and class scaling.",
                            "fields": [
                                {
                                    "name": "Base Chance Formula",
                                    "value": (
                                        "Non-god fights only, and only while `levelchoice < 12`.\n"
                                        "• Levels 1-10: `0.50 - ((level-1)/9) * 0.45`\n"
                                        "• Level 11: fixed `0.02`\n"
                                        "Reference: L1=50.0%, L5=30.0%, L10=5.0%, L11=2.0%"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Ranger Bonus Model",
                                    "value": (
                                        "Highest matching ranger-line bonus is applied:\n"
                                        "Caretaker +2%, Tamer +4%, Trainer +6%, Bowman +8%, Hunter +10%, Warden +13%, Ranger +15%.\n"
                                        "Adjusted bonus: `class_bonus * (1 - ((level-1)/9) * (1/3))` then added to base chance."
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                        {
                            "title": "IV/Substat Allocation and Hatch Scaling",
                            "description": "Egg stats are generated from monster base stats plus randomized IV distribution.",
                            "fields": [
                                {
                                    "name": "IV Generation Pipeline",
                                    "value": (
                                        "1. Seed roll from `uniform(10, 1000)` maps into weighted IV bands\n"
                                        "2. Final IV% band is re-rolled (30-100%)\n"
                                        "3. `total_iv_points = (IV% / 100) * 200`\n"
                                        "4. Points split across HP/ATK/DEF by normalized random weights + rounding correction"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Stat Construction",
                                    "value": (
                                        "• Egg DB stats: `monster_base + iv_split`\n"
                                        "• Hatch creates Baby pet at 25% stat multiplier\n"
                                        "• Stage multipliers by maturity: Baby 0.25, Juvenile 0.50, Young 0.75, Adult 1.00"
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                        {
                            "title": "36h Hatch Flow and Growth Timeline",
                            "description": (
                                f"• `{prefix}pets eggs` shows unhatched eggs and countdowns\n"
                                "• PvE egg hatch timer is 36 hours from drop\n"
                                "• Hatch and growth checks run every minute in background tasks"
                            ),
                            "fields": [
                                {
                                    "name": "Timeline",
                                    "value": (
                                        "• Egg incubation: 36h\n"
                                        "• Baby -> Juvenile: +2d\n"
                                        "• Juvenile -> Young: +2d\n"
                                        "• Young -> Adult: +1d\n"
                                        "Total from egg drop to adult is about 7.5 days without speed modifiers."
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Operational Notes",
                                    "value": (
                                        "• When hatch time is reached, egg is marked hatched and inserted into `monster_pets`\n"
                                        "• Young is the first battle-eligible growth stage\n"
                                        "• Speed Growth effects halve stage travel times while active"
                                    ),
                                    "inline": False,
                                }
                            ],
                        },
                        {
                            "title": "Shared Capacity Formula (Pets + Eggs + Pending Splice)",
                            "description": "Egg storage is part of a single shared capacity system.",
                            "fields": [
                                {
                                    "name": "Count Formula",
                                    "value": (
                                        "Active total is computed as:\n"
                                        "`COUNT(monster_pets)` + `COUNT(unhatched monster_eggs)` + `COUNT(pending splice_requests)`"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Tier Caps",
                                    "value": (
                                        "• Tier 0: 10\n"
                                        "• Tier 1: 12\n"
                                        "• Tier 2: 14\n"
                                        "• Tier 3: 17\n"
                                        "• Tier 4: 25"
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                        {
                            "title": "Capacity Overflow Flow (Release Prompt Path)",
                            "description": "If an egg drop rolls while you are capped, the game runs a release workflow first.",
                            "fields": [
                                {
                                    "name": "Prompt Flow",
                                    "value": (
                                        "1. System builds a combined list of your pets + unhatched eggs\n"
                                        "2. You get a dropdown selector with preview details\n"
                                        "3. You confirm release of one entry\n"
                                        "4. Released entry is deleted, then egg award continues"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Timeout and Cancel Behavior",
                                    "value": (
                                        "• Timeout/cancel => no egg awarded\n"
                                        "• Invalid selection => no egg awarded\n"
                                        "• This is intentional to prevent bypassing shared cap rules"
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                        {
                            "title": "Egg Trade/Sell/Release Safety",
                            "description": "Eggs can move between players, but all destructive actions are high-trust operations.",
                            "fields": [
                                {
                                    "name": "Supported Commands",
                                    "value": (
                                        f"• `{prefix}pets trade <your_type> <your_ref> <their_ref>`\n"
                                        f"• `{prefix}pets sell <pet|egg> <ref> <buyer> <price>`\n"
                                        f"• `{prefix}pets release <id|alias|egg_id>`"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Safety Notes",
                                    "value": (
                                        "• Trade/sell flows include interactive accept/decline steps\n"
                                        "• Capacity is validated before transfer completion\n"
                                        "• Release is permanent after confirmation and cannot be undone"
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                    ],
                },
                {
                    "label": "Soulforge & Splice",
                    "summary": "Quest requirements, forge unlock, splice generations, and late game.",
                    "emoji": "🧪",
                    "pages": [
                        {
                            "title": "Soulforge Start",
                            "description": (
                                f"• `{prefix}soulforge` starts/checks progression\n"
                                f"• `{prefix}soulforgeguide` for dedicated flow docs"
                            ),
                            "fields": [
                                {
                                    "name": "Core Requirements",
                                    "value": (
                                        "• 10 Eidolith Shards\n"
                                        "• Alchemist's Primer\n"
                                        "• 2,500,000 gold\n"
                                        f"• Then `{prefix}forgesoulforge` to unlock full systems"
                                    ),
                                    "inline": False,
                                }
                            ],
                        },
                        {
                            "title": "Splice Workflow",
                            "description": "After forge unlock, splicing becomes its own progression ecosystem.",
                            "fields": [
                                {
                                    "name": "Flow",
                                    "value": (
                                        f"• Gather/prepare candidate pets\n"
                                        f"• Use splice commands from the Soulforge/ProcessSplice systems\n"
                                        "• Track generation quality and outcomes over many runs"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Command Pointers",
                                    "value": (
                                        f"• `{prefix}soulforgeguide`\n"
                                        f"• `{prefix}eshards` (from extensions)\n"
                                        "• See module help for active splice command set in your build"
                                    ),
                                    "inline": False,
                                },
                            ],
                        },
                        {
                            "title": "Late-Game Notes",
                            "description": (
                                "Soulforge ties into high-end progression layers (god pets, shard systems, "
                                "and long-cycle optimization)."
                            ),
                            "fields": [
                                {
                                    "name": "Best Practice",
                                    "value": (
                                        "Track your splice outcomes and target specific improvement goals "
                                        "instead of random experimentation."
                                    ),
                                    "inline": False,
                                }
                            ],
                        },
                    ],
                },
                {
                    "label": "Rankings & Achievements",
                    "summary": "Long-term goals, leaderboard categories, and completion tracking.",
                    "emoji": "🏆",
                    "pages": [
                        {
                            "title": "Leaderboard Systems",
                            "description": (
                                f"Use `{prefix}richest`, `{prefix}best`, `{prefix}pvp`, "
                                f"`{prefix}btlb`, `{prefix}lovers` and related rank commands."
                            ),
                            "fields": [
                                {
                                    "name": "Achievement Tracking",
                                    "value": (
                                        f"• `{prefix}achievement` / achievement aliases\n"
                                        "• Categories include level milestones, loot exchange, battle counts, and crate milestones"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Climbing Efficiently",
                                    "value": (
                                        "Specialize per board: do not split resources across every leaderboard at once."
                                    ),
                                    "inline": False,
                                },
                            ],
                        }
                    ],
                },
                {
                    "label": "Seasonal & Event Systems",
                    "summary": "Event shops, event currencies, and limited-time optimization.",
                    "emoji": "🎉",
                    "pages": [
                        {
                            "title": "Event Families",
                            "description": (
                                "Your bot includes rotating systems like Halloween, Wintersday, Lunar New Year, Easter, and other event cogs."
                            ),
                            "fields": [
                                {
                                    "name": "When Active",
                                    "value": (
                                        "1. Check event help/shop command first\n"
                                        "2. Convert event drops quickly (don't hoard blindly)\n"
                                        "3. Prioritize non-repeatable unlocks before consumables"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Examples",
                                    "value": (
                                        f"• `{prefix}ss ...` (Halloween shop aliases)\n"
                                        f"• `{prefix}cs ...` (Wintersday shop aliases)\n"
                                        f"• `{prefix}lunar ...` / `{prefix}lny...` paths"
                                    ),
                                    "inline": False,
                                },
                            ],
                        }
                    ],
                },
                {
                    "label": "Glossary & Economy Map",
                    "summary": "What each major resource does and where it feeds into progression.",
                    "emoji": "📖",
                    "pages": [
                        {
                            "title": "Resource Glossary",
                            "description": "Use this as your quick reference while planning upgrades.",
                            "fields": [
                                {
                                    "name": "Core Resources",
                                    "value": (
                                        "• Money: primary upgrade/trade currency\n"
                                        "• Dragon Coins: premium currency (`dragoncoinshop`)\n"
                                        "• Favor: god progression and standing\n"
                                        "• Crates: gear/resource/utility reward containers\n"
                                        "• Crafting resources: amulet and crafting progression"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Advanced Resources",
                                    "value": (
                                        "• Raid multipliers: raid-specific combat growth\n"
                                        "• Soulforge shards/primer: splice unlock progression\n"
                                        "• Lovescore/family values: marriage-family subsystem scaling"
                                    ),
                                    "inline": False,
                                },
                            ],
                        }
                    ],
                },
                {
                    "label": "Command Group Indexes",
                    "summary": (
                        f"Audited index of {total_public_commands} public commands across {total_public_cogs} command groups."
                    ),
                    "emoji": "🗂️",
                    "pages": command_group_index_pages,
                },
                {
                    "label": "Command Writeups",
                    "summary": (
                        "Generated handbook pages based on the actual command help text and locale_doc docstrings."
                    ),
                    "emoji": "📝",
                    "pages": command_writeup_pages,
                },
                {
                    "label": "Troubleshooting",
                    "summary": "Common blockers and exact fixes.",
                    "emoji": "🩺",
                    "pages": [
                        {
                            "title": "If A Command Fails",
                            "description": "Most errors are state checks, not bugs.",
                            "fields": [
                                {
                                    "name": "Fast Debug Checklist",
                                    "value": (
                                        f"• Run `{prefix}profile` first (do you have a character?)\n"
                                        "• Check cooldowns and required currency/resources\n"
                                        "• Verify IDs/aliases are valid (items, pets, users)\n"
                                        f"• Use `{prefix}help <command>` for exact syntax\n"
                                        "• Confirm hidden/admin commands are not being used as normal player"
                                    ),
                                    "inline": False,
                                },
                                {
                                    "name": "Frequent Causes",
                                    "value": (
                                        "• Not enough money/resources\n"
                                        "• Wrong command argument order\n"
                                        "• Attempting locked content too early\n"
                                        "• Command used in wrong context (guild-only, has-char checks, etc.)"
                                    ),
                                    "inline": False,
                                },
                            ],
                        }
                    ],
                },
                {
                    "label": "Command Atlas",
                    "summary": "Dynamic index of all public commands grouped by module.",
                    "emoji": "📚",
                    "pages": command_atlas_pages,
                },
            ]
        )
        self._extend_sections_with_doc_digests(sections, prefix, commands_by_cog)
        sections.insert(0, self._build_guidebook_index_section(prefix, sections))
        return sections

    @commands.command(aliases=["commands", "cmds"], brief=_("View the command list"))
    @locale_doc
    async def documentation(self, ctx):
        _("""Sends a link to the official documentation.""")
        await ctx.send(
            _(
                "**Check {url} for a list of"
                " commands**"
            ).format(url=f"{self.bot.BASE_URL}")
        )

    @commands.command(aliases=["faq"], brief=_("View the tutorial"))
    @locale_doc
    async def tutorial(self, ctx):
        _("""Link to the bot tutorial and FAQ.""")
        await ctx.send(
            _(
                "**Check {url} for a tutorial**"
            ).format(url=f"{self.bot.BASE_URL}")
        )

    @commands.command(
        name="guidebook",
        aliases=[
            "guide",
            "handbook",
            "booklet",
            "gettingstarted",
            "newplayerguide",
            "starterguide",
        ],
        brief=_("Open the complete interactive new-player guidebook"),
    )
    @locale_doc
    async def guidebook(self, ctx):
        _(
            """Open an in-depth guidebook with dropdown navigation and pagination.

            Covers getting started, progression loops, combat, elements, classes, gods,
            pets, economy/trading, group content, and a dynamic command atlas.

            Aliases such as `{prefix}booklet` and `{prefix}gettingstarted` open the same guide."""
        )
        try:
            profile_row = None
            try:
                profile_row_raw = await self.bot.pool.fetchrow(
                    'SELECT "class", "god", "race", "money", "dragoncoins", "reset_points" '
                    'FROM profile WHERE "user"=$1;',
                    ctx.author.id,
                )
                if profile_row_raw:
                    profile_row = dict(profile_row_raw)
            except Exception:
                profile_row = None

            sections = self._build_guidebook_sections(ctx.clean_prefix, profile_row=profile_row)
            view = GuidebookView(
                ctx=ctx,
                sections=sections,
                color=self.bot.config.game.primary_colour,
            )
            await view.start()
        except Exception as e:
            await ctx.send(e)

    @is_supporter()
    @commands.command(brief=_("Allow someone/-thing to use help_me again"))
    @locale_doc
    async def unbanfromhelp_me(self, ctx, thing_to_unban: discord.User | int):
        _(
            """`<thing_to_unban>` - A discord User, their User ID, or a server ID

            Unbans a previously banned user/server from using the `{prefix}help_me` command.

            Only Support Team Members can use this command."""
        )
        if isinstance(thing_to_unban, discord.User):
            id = thing_to_unban.id
        else:
            id = thing_to_unban
            thing_to_unban = self.bot.get_guild(id)
        await self.bot.pool.execute('DELETE FROM help_me WHERE "id"=$1;', id)
        await ctx.send(
            _("{thing} has been unbanned for the help_me command :ok_hand:").format(
                thing=thing_to_unban.name
            )
        )

    @is_supporter()
    @commands.command(brief=_("Ban someone/-thing from using help_me"))
    @locale_doc
    async def banfromhelp_me(self, ctx, thing_to_ban: discord.User | int):
        _(
            """`<thing_to_ban>` - A discord User, their User ID, or a server ID

            Bans a user/server from using the `{prefix}help_me` command.

            Only Support Team Members can use this command."""
        )
        id = thing_to_ban.id if isinstance(thing_to_ban, discord.User) else thing_to_ban
        try:
            await self.bot.pool.execute('INSERT INTO help_me ("id") VALUES ($1);', id)
        except UniqueViolationError:
            return await ctx.send(_("Error... Maybe they're already banned?"))
        await ctx.send(_("They have been banned for the help_me command :ok_hand:"))

    @commands.guild_only()
    @commands.group(
        invoke_without_command=True, brief=_("Ask our Support Team for help")
    )
    @locale_doc
    async def help_me(self, ctx, *, text: str):
        _(
            """`<text>` - The text to describe the question or the issue you are having

            Ask our support team for help, allowing them to join your server and help you personally.
            If they do not join within 48 hours, you may use the help_me command again.

            Make sure the bot has permissions to create instant invites.
            English is preferred."""
        )
        if (
            cd := await self.bot.redis.execute_command("TTL", f"help_me:{ctx.guild.id}")
        ) != -2:
            time = timedelta(seconds=cd)
            return await ctx.send(
                _(
                    "You server already has a help_me request open! Please wait until"
                    " the support team gets to you or wait {time} to try again. "
                ).format(time=time)
            )
        blocked = await self.bot.pool.fetchrow(
            'SELECT * FROM help_me WHERE "id"=$1 OR "id"=$2;',
            ctx.guild.id,
            ctx.author.id,
        )
        if blocked:
            return await ctx.send(
                _("You or your server has been blacklisted for some reason.")
            )

        if not await ctx.confirm(
            _(
                "Are you sure? This will notify our support team and allow them to join"
                " the server."
            )
        ):
            return

        try:
            inv = await ctx.channel.create_invite()
        except discord.Forbidden:
            return await ctx.send(_("Error when creating Invite."))
        em = discord.Embed(title="Help Request", colour=0xFF0000)
        em.add_field(name="Requested by", value=f"{ctx.author}")
        em.add_field(name="Requested in server", value=f"{ctx.guild.name}")
        em.add_field(name="Requested in channel", value=f"#{ctx.channel}")
        em.add_field(name="Content", value=text)
        em.add_field(name="Invite", value=inv)
        em.set_footer(text=f"Server ID: {ctx.guild.id}")

        with handle_message_parameters(embed=em) as params:
            message = await self.bot.http.send_message(
                self.bot.config.game.help_me_channel, params=params
            )
        await self.bot.redis.execute_command(
            "SET",
            f"help_me:{ctx.guild.id}",
            message["id"],
            "EX",
            172800,  # 48 hours
        )
        await ctx.send(
            _("Support team has been notified and will join as soon as possible!")
        )

    @is_supporter()
    @help_me.command(hidden=True, brief=_("Finish the help_me request"))
    @locale_doc
    async def finish(self, ctx, guild_id: int):
        _(
            """`<guild_id>` - The server ID of the requesting server

            Clear a server's help_me cooldown. If this is not done, they will be on cooldown for 48 hours."""
        )
        await self.bot.redis.execute_command("DEL", f"help_me:{guild_id}")
        await ctx.send("Clear!", delete_after=5)

    @has_open_help_request()
    @help_me.command(aliases=["correct"], brief=_("Change your help_me text"))
    @locale_doc
    async def edit(self, ctx, *, new_text: str):
        _(
            """`<new_text>` - The new text to use in your help_me request

            Edit the text on your open help_me request. Our Support Team will see the new text right away.

            You can only use this command if your server has an open help_me request."""
        )
        message = await self.bot.http.get_message(
            self.bot.config.game.help_me_channel, ctx.help_me
        )
        inv = discord.utils.find(
            lambda f: f["name"] == "Invite", message["embeds"][0]["fields"]
        )["value"]
        old_text = discord.utils.find(
            lambda f: f["name"] == "Content", message["embeds"][0]["fields"]
        )["value"]

        em = discord.Embed(title="Help Request", colour=0xFF0000)
        em.add_field(name="Requested by", value=f"{ctx.author}")
        em.add_field(name="Requested in server", value=f"{ctx.guild.name}")
        em.add_field(name="Requested in channel", value=f"#{ctx.channel}")
        em.add_field(name="Content", value=new_text)
        em.add_field(name="Invite", value=inv)
        em.set_footer(text=f"Server ID: {ctx.guild.id}")

        await self.bot.http.edit_message(
            self.bot.config.game.help_me_channel,
            ctx.help_me,
            content=None,
            embed=em.to_dict(),
        )
        await ctx.send(
            _("Successfully changed your help_me text from `{old}` to `{new}`!").format(
                old=old_text, new=new_text
            )
        )

    @has_open_help_request()
    @help_me.command(
        aliases=["revoke", "remove"], brief=_("Cancel your open help_me request")
    )
    @locale_doc
    async def delete(self, ctx):
        _(
            """Cancel your ongoing help_me request. Our Support Team will not join your server.

            You can only use this command if your server has an open help_me request."""
        )
        if not await ctx.confirm(
            _("Are you sure you want to cancel your help_me request?")
        ):
            return await ctx.send(_("Cancelled cancellation."))
        await self.bot.http.delete_message(
            self.bot.config.game.help_me_channel, ctx.help_me
        )
        await self.bot.redis.execute_command("DEL", f"help_me:{ctx.guild.id}")
        with handle_message_parameters(
            content=f"help_me request for server {ctx.guild} ({ctx.guild.id}) was cancelled by {ctx.author}"
        ) as params:
            await self.bot.http.send_message(
                self.bot.config.game.help_me_channel, params=params
            )
        await ctx.send(_("Your help_me request has been cancelled."))

    @has_open_help_request()
    @help_me.command(brief=_("View your current help_me request"))
    @locale_doc
    async def view(self, ctx):
        _(
            """View how your server's current help_me request looks like to our Support Team.

            You can only use this command if your server has an open help_me request."""
        )
        message = await self.bot.http.get_message(
            self.bot.config.game.help_me_channel, ctx.help_me
        )
        embed = discord.Embed().from_dict(message["embeds"][0])

        await ctx.send(
            _("Your help request is visible to our support team like this:"),
            embed=embed,
        )


class IdleHelp(commands.HelpCommand):
    def __init__(self, *args, **kwargs):
        kwargs["command_attrs"] = {
            "brief": _("Views the help on a topic."),
            "help": _(
                """Views the help on a topic.

            The topic may either be a command name or a module name.
            Command names are always preferred, so for example, `{prefix}help adventure`
            will show the help on the command, not the module.

            To view the help on a module explicitely, use `{prefix}help module [name]`"""
            ),
        }

        super().__init__(*args, **kwargs)
        self.verify_checks = False
        self.color = None
        self.gm_exts = {"GameMaster"}
        self.owner_exts = {"Owner"}
        self.group_emoji = "💠"
        self.command_emoji = "🔷"
        self._owner_table_checked = False
        self._owner_table_name = None
        self._owner_table_column = None
        self._db_gm_cache = set()

    async def _is_db_gm(self, user_id: int) -> bool:
        gm_cache = getattr(self.context.bot, "_gm_cache", None)
        if isinstance(gm_cache, set) and user_id in gm_cache:
            return True
        if user_id in self._db_gm_cache:
            return True
        try:
            result = await self.context.bot.pool.fetchrow(
                "SELECT 1 FROM game_masters WHERE user_id = $1",
                user_id,
            )
        except Exception:
            return False
        is_gm = result is not None
        if is_gm:
            self._db_gm_cache.add(user_id)
            if isinstance(gm_cache, set):
                gm_cache.add(user_id)
        return is_gm

    async def _resolve_owner_db_table(self) -> None:
        if self._owner_table_checked:
            return

        self._owner_table_checked = True
        table_candidates = ("bot_owners", "game_owners", "owners")
        column_candidates = ("user_id", "owner_id")

        for table in table_candidates:
            try:
                exists = await self.context.bot.pool.fetchval(
                    "SELECT to_regclass($1)",
                    f"public.{table}",
                )
            except Exception:
                continue
            if not exists:
                continue

            for column in column_candidates:
                try:
                    await self.context.bot.pool.fetchrow(
                        f"SELECT 1 FROM {table} WHERE {column} = $1 LIMIT 1",
                        0,
                    )
                except Exception:
                    continue
                self._owner_table_name = table
                self._owner_table_column = column
                return

    async def _is_db_owner(self, user_id: int) -> bool:
        await self._resolve_owner_db_table()
        if not self._owner_table_name or not self._owner_table_column:
            return False
        try:
            result = await self.context.bot.pool.fetchrow(
                f"SELECT 1 FROM {self._owner_table_name} WHERE {self._owner_table_column} = $1",
                user_id,
            )
        except Exception:
            return False
        return result is not None

    async def _is_owner_user(self, user: discord.abc.User) -> bool:
        config_owner_ids = set(getattr(self.context.bot.config.game, "owner_ids", []) or [])
        if user.id in self.context.bot.owner_ids or user.id in config_owner_ids:
            return True
        try:
            if await self.context.bot.is_owner(user):
                return True
        except Exception:
            pass
        return await self._is_db_owner(user.id)

    async def _is_gm_user(self, user: discord.abc.User) -> bool:
        config_gms = set(getattr(self.context.bot.config.game, "game_masters", []) or [])
        if user.id in config_gms:
            return True
        return await self._is_db_gm(user.id)

    async def command_callback(self, ctx, *, command=None):
        await self.prepare_help_command(ctx, command)
        bot = ctx.bot

        if command is None:
            mapping = self.get_bot_mapping()
            return await self.send_bot_help(mapping)

        PREFER_COG = False
        if command.lower().startswith(("module ", "module:")):
            command = command[7:]
            PREFER_COG = True

        if PREFER_COG:
            if command.lower() == "gamemaster":
                command = "GameMaster"
            else:
                command = command.title()
            cog = bot.get_cog(command)
            if cog is not None:
                return await self.send_cog_help(cog)

        maybe_coro = discord.utils.maybe_coroutine

        keys = command.split(" ")
        cmd = bot.all_commands.get(keys[0])
        if cmd is None:
            cog = bot.get_cog(command.title())
            if cog is not None:
                return await self.send_cog_help(cog)

            string = await maybe_coro(
                self.command_not_found, self.remove_mentions(keys[0])
            )
            return await self.send_error_message(string)

        for key in keys[1:]:
            try:
                found = cmd.all_commands.get(key)
            except AttributeError:
                string = await maybe_coro(
                    self.subcommand_not_found, cmd, self.remove_mentions(key)
                )
                return await self.send_error_message(string)
            else:
                if found is None:
                    string = await maybe_coro(
                        self.subcommand_not_found, cmd, self.remove_mentions(key)
                    )
                    return await self.send_error_message(string)
                cmd = found

        if isinstance(cmd, commands.Group):
            return await self.send_group_help(cmd)
        else:
            return await self.send_command_help(cmd)

    async def send_bot_help(self, mapping):
        e = discord.Embed(
            title=_(
                "Fable Help {version}",
            ).format(version=self.context.bot.version),
            color=self.context.bot.config.game.primary_colour,
            url="https://wiki.fablerpg.xyz/",
        )
        e.set_author(
            name=self.context.bot.user,
            icon_url=self.context.bot.user.display_avatar.url,
        )
        e.description = _(
            "**Welcome to the Fable help.**\nCheck out our tutorial!\n-"

        ).format(prefix=self.context.clean_prefix)

        is_owner = await self._is_owner_user(self.context.author)
        is_gm = is_owner or await self._is_gm_user(self.context.author)

        allowed = []
        for cog in sorted(mapping.keys(), key=lambda x: x.qualified_name if x else ""):
            if cog is None:
                continue
            if not is_gm and cog.qualified_name in self.gm_exts:
                continue
            if not is_owner and cog.qualified_name in self.owner_exts:
                continue
            if (
                cog.qualified_name not in self.gm_exts
                and len([c for c in cog.get_commands() if not c.hidden]) == 0
            ):
                continue
            allowed.append(cog.qualified_name)
        cogs = [allowed[x : x + 3] for x in range(0, len(allowed), 3)]
        length_list = [len(element) for row in cogs for element in row]
        column_width = max(length_list)
        rows = []
        for row in cogs:
            rows.append("".join(element.ljust(column_width + 2) for element in row))
        e.add_field(name=_("Modules"), value="```{}```".format("\n".join(rows)))

        await self.context.send(embed=e)

    async def send_cog_help(self, cog):
        is_owner = await self._is_owner_user(self.context.author)
        is_gm = is_owner or await self._is_gm_user(self.context.author)

        if cog.qualified_name in self.gm_exts and not is_gm:
            return await self.context.send(
                _("You do not have access to these commands!")
            )
        if cog.qualified_name in self.owner_exts and not is_owner:
            return await self.context.send(
                _("You do not have access to these commands!")
            )

        menu = CogMenu(
            title=(
                f"[{cog.qualified_name.upper()}] {len(set(cog.walk_commands()))}"
                " commands"
            ),
            bot=self.context.bot,
            color=self.context.bot.config.game.primary_colour,
            description=[
                f"{self.group_emoji if isinstance(c, commands.Group) else self.command_emoji}"
                f" `{self.context.clean_prefix}{c.qualified_name} {c.signature}` - {_(c.brief) if c.brief else _('No brief help available')}"
                for c in cog.get_commands()
            ],
            footer=_("See '{prefix}help <command>' for more detailed info").format(
                prefix=self.context.clean_prefix
            ),
        )

        await menu.start(self.context)

    async def send_command_help(self, command: Command):
        if command.cog:
            is_owner = await self._is_owner_user(self.context.author)
            is_gm = is_owner or await self._is_gm_user(self.context.author)

            if command.cog.qualified_name in self.gm_exts and not is_gm:
                return await self.context.send(
                    _("You do not have access to this command!")
                )
            if command.cog.qualified_name in self.owner_exts and not is_owner:
                return await self.context.send(
                    _("You do not have access to this command!")
                )

        e = discord.Embed(
            title=(
                f"[{command.cog.qualified_name.upper()}] {command.qualified_name}"
                f" {command.signature}"
            ),
            colour=self.context.bot.config.game.primary_colour,
            description=_(command.help).format(prefix=self.context.clean_prefix)
            if command.help
            else _("No help available"),
        )
        e.set_author(
            name=self.context.bot.user,
            icon_url=self.context.bot.user.display_avatar.url,
        )

        if command.aliases:
            e.add_field(
                name=_("Aliases"), value="`{}`".format("`, `".join(command.aliases))
            )
        await self.context.send(embed=e)

    async def send_group_help(self, group):
        if group.cog:
            is_owner = await self._is_owner_user(self.context.author)
            is_gm = is_owner or await self._is_gm_user(self.context.author)

            if group.cog.qualified_name in self.gm_exts and not is_gm:
                return await self.context.send(
                    _("You do not have access to this command!")
                )
            if group.cog.qualified_name in self.owner_exts and not is_owner:
                return await self.context.send(
                    _("You do not have access to this command!")
                )

        menu = SubcommandMenu(
            title=(
                f"[{group.cog.qualified_name.upper()}] {group.qualified_name}"
                f" {group.signature}"
            ),
            bot=self.context.bot,
            color=self.context.bot.config.game.primary_colour,
            description=_(group.help).format(prefix=self.context.clean_prefix),
            cmds=list(group.commands),
        )
        await menu.start(self.context)


async def setup(bot: Bot) -> None:
    bot.remove_command("help")
    await bot.add_cog(Help(bot))
    bot.help_command = IdleHelp()
    bot.help_command.cog = bot.get_cog("Help")
