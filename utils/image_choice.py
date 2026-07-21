from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import discord
from discord.ext import commands


IMAGE_EXTENSIONS = (".webp", ".png", ".jpg", ".jpeg")


@dataclass
class ImageChoice:
    label: str
    embed: discord.Embed
    image_path: Path | None = None
    value: Any = None
    description: str | None = None


def find_image_path(directory: Path, stem: str) -> Path | None:
    for extension in IMAGE_EXTENSIONS:
        path = directory / f"{stem}{extension}"
        if path.is_file():
            return path
    return None


def _attachment_name(label: str, image_path: Path) -> str:
    stem = "".join(
        char.lower() if char.isascii() and char.isalnum() else "_"
        for char in label
    ).strip("_")
    stem = stem or image_path.stem.lower().replace(" ", "_")
    return f"{stem}{image_path.suffix or '.webp'}"


def embed_with_image(
    embed: discord.Embed,
    image_path: Path | None,
    *,
    label: str,
) -> tuple[discord.Embed, list[discord.File]]:
    embed = embed.copy()
    if not image_path or not image_path.is_file():
        embed.set_image(url=None)
        return embed, []

    filename = _attachment_name(label, image_path)
    file = discord.File(str(image_path), filename=filename)
    embed.set_image(url=f"attachment://{filename}")
    return embed, [file]


class ImageChoiceSelect(discord.ui.Select):
    def __init__(self, picker: "ImageChoiceView") -> None:
        self.picker = picker
        options = []
        for index, choice in enumerate(picker.choices):
            options.append(
                discord.SelectOption(
                    label=choice.label[:100],
                    value=str(index),
                    description=(choice.description or "")[:100] or None,
                    default=index == picker.index,
                )
            )
        super().__init__(
            placeholder=picker.placeholder[:100],
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.picker.index = int(self.values[0])
        await self.picker.refresh(interaction)


class ImageChoiceView(discord.ui.View):
    def __init__(
        self,
        ctx: commands.Context,
        choices: list[ImageChoice],
        *,
        placeholder: str,
        timeout: float = 90.0,
    ) -> None:
        super().__init__(timeout=timeout)
        if not choices:
            raise ValueError("ImageChoiceView needs at least one choice")
        if len(choices) > 25:
            raise ValueError("Discord selects support at most 25 choices")
        self.ctx = ctx
        self.choices = choices
        self.placeholder = placeholder
        self.index = 0
        self.value: Any = None
        self.message: discord.Message | None = None
        self.add_item(ImageChoiceSelect(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.ctx.author.id:
            return True
        await interaction.response.send_message(
            "This picker was not started by you.",
            ephemeral=True,
        )
        return False

    def _sync_select(self) -> None:
        for item in self.children:
            if isinstance(item, ImageChoiceSelect):
                for index, option in enumerate(item.options):
                    option.default = index == self.index
                break

    def _current_payload(self) -> tuple[discord.Embed, list[discord.File]]:
        self._sync_select()
        choice = self.choices[self.index]
        embed = choice.embed.copy()
        page_text = f"{self.index + 1}/{len(self.choices)}"
        footer_text = getattr(embed.footer, "text", None)
        embed.set_footer(text=f"{footer_text} | {page_text}" if footer_text else page_text)
        return embed_with_image(embed, choice.image_path, label=choice.label)

    async def prompt(self) -> Any:
        embed, files = self._current_payload()
        kwargs = {"embed": embed, "view": self}
        if files:
            kwargs["file"] = files[0]
        self.message = await self.ctx.send(**kwargs)
        await self.wait()
        return self.value

    async def refresh(self, interaction: discord.Interaction) -> None:
        embed, files = self._current_payload()
        await interaction.response.edit_message(
            embed=embed,
            attachments=files,
            view=self,
        )

    async def on_timeout(self) -> None:
        if self.message:
            try:
                await self.message.edit(view=None)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, row=1)
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.index = (self.index - 1) % len(self.choices)
        await self.refresh(interaction)

    @discord.ui.button(label="Select", style=discord.ButtonStyle.success, row=1)
    async def select(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        choice = self.choices[self.index]
        self.value = choice.value if choice.value is not None else self.index
        await interaction.response.edit_message(view=None)
        self.stop()

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, row=1)
    async def next(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.index = (self.index + 1) % len(self.choices)
        await self.refresh(interaction)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, row=1)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.value = None
        await interaction.response.edit_message(view=None)
        self.stop()
