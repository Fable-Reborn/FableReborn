from __future__ import annotations

import discord

from .content import CARD_LIBRARY, RELIC_LIBRARY
from .models import RunState


def _truncate(value: str, limit: int = 100) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: limit - 3]}..."


class ActionButton(discord.ui.Button):
    def __init__(self, label: str, style: discord.ButtonStyle, action: str):
        super().__init__(label=label, style=style)
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        await self.view.cog.handle_view_action(  # type: ignore[attr-defined]
            interaction,
            self.action,
            None,
        )


class ActionSelect(discord.ui.Select):
    def __init__(
        self,
        *,
        placeholder: str,
        action: str,
        options: list[discord.SelectOption],
    ):
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        await self.view.cog.handle_view_action(  # type: ignore[attr-defined]
            interaction,
            self.action,
            self.values[0],
        )


class CharacterPickerSelect(discord.ui.Select):
    def __init__(self, view: "CharacterPickerView"):
        self.picker_view = view
        options = [
            discord.SelectOption(
                label=view.cog.character_display_name(character_key),
                value=character_key,
                description=_truncate(view.cog.character_picker_blurb(character_key), 100),
                default=character_key == view.selected_character,
            )
            for character_key in view.character_order
        ]
        super().__init__(
            placeholder="Choose a character",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        self.picker_view.selected_character = self.values[0]
        self.picker_view.refresh()
        await interaction.response.edit_message(
            embed=self.picker_view.cog.build_character_picker_embed(self.picker_view.selected_character),
            view=self.picker_view,
        )


class CharacterPickerNavButton(discord.ui.Button):
    def __init__(self, label: str, delta: int):
        super().__init__(label=label, style=discord.ButtonStyle.secondary)
        self.delta = delta

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, CharacterPickerView):
            return
        current = view.character_order.index(view.selected_character)
        view.selected_character = view.character_order[(current + self.delta) % len(view.character_order)]
        view.refresh()
        await interaction.response.edit_message(
            embed=view.cog.build_character_picker_embed(view.selected_character),
            view=view,
        )


class CharacterPickerStartButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Start Run", style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, CharacterPickerView):
            return
        await view.cog.start_run_from_picker(interaction, view.selected_character)


class CharacterPickerView(discord.ui.View):
    def __init__(self, cog, user_id: int, selected_character: str = "ironclad"):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id
        self.character_order = ["ironclad", "silent", "defect", "watcher", "necrobinder"]
        self.selected_character = (
            selected_character if selected_character in self.character_order else self.character_order[0]
        )
        self.refresh()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This character picker belongs to someone else.",
                ephemeral=True,
            )
            return False
        return True

    def refresh(self) -> None:
        self.clear_items()
        self.add_item(CharacterPickerSelect(self))
        self.add_item(CharacterPickerNavButton("Prev", -1))
        self.add_item(CharacterPickerNavButton("Next", 1))
        self.add_item(CharacterPickerStartButton())


class SpireRunView(discord.ui.View):
    def __init__(self, cog, run: RunState):
        super().__init__(timeout=900)
        self.cog = cog
        self.run = run
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.run.user_id:
            await interaction.response.send_message(
                "This run belongs to someone else.",
                ephemeral=True,
            )
            return False
        return True

    def _build(self) -> None:
        if self.run.phase == "neow" and self.run.event is not None:
            options = [
                discord.SelectOption(
                    label=option.label,
                    value=option.option_id,
                    description=_truncate(option.description),
                )
                for option in self.run.event.options
            ]
            self.add_item(
                ActionSelect(
                    placeholder="Choose Neow's blessing",
                    action="neow_choice",
                    options=options,
                )
            )
        elif self.run.phase == "map":
            options = [
                discord.SelectOption(
                    label=_truncate(f"{index + 1}. {self.cog.node_label(node, self.run)}", 95),
                    value=str(index),
                    description=_truncate(self.cog.map_choice_description(node, self.run)),
                )
                for index, node in enumerate(self.run.map_choices)
            ]
            self.add_item(
                ActionSelect(
                    placeholder="Choose your next node",
                    action="map_choice",
                    options=options,
                )
            )
        elif self.run.phase == "combat" and self.run.combat is not None:
            if self.run.selection_context and self.run.selection_context.startswith(("card:", "potion:")):
                options = [
                    discord.SelectOption(
                        label=_truncate(self.cog.enemy_target_label(self.run, enemy), 95),
                        value=enemy.enemy_id,
                        description=_truncate(self.cog.enemy_target_description(enemy)),
                    )
                    for enemy in self.cog.engine.list_playable_targets(self.run)
                ]
                self.add_item(
                    ActionSelect(
                        placeholder="Choose a target",
                        action="target_enemy",
                        options=options,
                    )
                )
                self.add_item(ActionButton("Cancel", discord.ButtonStyle.secondary, "cancel_selection"))
                self.add_item(ActionButton("Deck", discord.ButtonStyle.secondary, "show_deck"))
                self.add_item(ActionButton("Discard", discord.ButtonStyle.secondary, "show_discard"))
                if "frozen_eye" in self.run.relics:
                    self.add_item(ActionButton("Draw", discord.ButtonStyle.secondary, "show_draw"))
            elif self.run.selection_context == "gambling_chip":
                options = [
                    discord.SelectOption(
                        label=_truncate(self.cog.engine.card_name(card), 95),
                        value=card.instance_id,
                        description=_truncate(self.cog.engine.card_description(card)),
                    )
                    for card in self.run.combat.hand
                ]
                if options:
                    self.add_item(
                        ActionSelect(
                            placeholder="Discard any cards with Gambling Chip",
                            action="gambling_chip_discard",
                            options=options[:25],
                        )
                    )
                self.add_item(ActionButton("Keep Hand", discord.ButtonStyle.primary, "finish_gambling_chip"))
                self.add_item(ActionButton("Deck", discord.ButtonStyle.secondary, "show_deck"))
                self.add_item(ActionButton("Discard", discord.ButtonStyle.secondary, "show_discard"))
                if "frozen_eye" in self.run.relics:
                    self.add_item(ActionButton("Draw", discord.ButtonStyle.secondary, "show_draw"))
            else:
                playable_hand = [
                    card
                    for card in self.run.combat.hand
                    if self.cog.engine.card_is_playable(self.run, card, self.run.combat)
                ]
                if playable_hand:
                    options = []
                    for card in playable_hand:
                        label = (
                            f"{self.cog.engine.card_name(card)} "
                            f"[{self.cog.engine.card_cost_label(card, self.run.combat)}]"
                        )
                        description = _truncate(self.cog.engine.card_description(card))
                        options.append(
                            discord.SelectOption(
                                label=_truncate(label, 95),
                                value=card.instance_id,
                                description=description,
                            )
                        )
                    self.add_item(
                        ActionSelect(
                            placeholder="Play a card",
                            action="play_card",
                            options=options,
                        )
                    )
            if self.run.selection_context != "gambling_chip":
                self.add_item(ActionButton("End Turn", discord.ButtonStyle.primary, "end_turn"))
                self.add_item(ActionButton("Deck", discord.ButtonStyle.secondary, "show_deck"))
                self.add_item(ActionButton("Discard", discord.ButtonStyle.secondary, "show_discard"))
                if "frozen_eye" in self.run.relics:
                    self.add_item(ActionButton("Draw", discord.ButtonStyle.secondary, "show_draw"))
                if self.run.potions and not self.run.selection_context:
                    potion_options = [
                        discord.SelectOption(
                            label=self.cog.potion_name(key),
                            value=f"{index}:{key}",
                            description=_truncate(self.cog.potion_description(key)),
                        )
                        for index, key in enumerate(self.run.potions)
                    ]
                    self.add_item(
                        ActionSelect(
                            placeholder="Use a potion",
                            action="use_potion",
                            options=potion_options,
                        )
                    )
        elif self.run.phase == "reward" and self.run.reward is not None:
            options = [
                discord.SelectOption(
                    label=CARD_LIBRARY[key].name,
                    value=str(index),
                    description=_truncate(CARD_LIBRARY[key].description),
                )
                for index, key in enumerate(self.run.reward.card_choices)
            ]
            self.add_item(
                ActionSelect(
                    placeholder="Choose a card reward",
                    action="reward_choice",
                    options=options,
                )
            )
            if self.run.reward.source not in {"neow", "event_forced", "tiny_house", "toolbox", "orrery"}:
                self.add_item(ActionButton("Skip", discord.ButtonStyle.secondary, "skip_reward"))
            if "singing_bowl" in self.run.relics and self.run.reward.source not in {"event_forced", "toolbox"}:
                self.add_item(ActionButton("Singing Bowl", discord.ButtonStyle.primary, "singing_bowl"))
            self.add_item(ActionButton("Deck", discord.ButtonStyle.secondary, "show_deck"))
        elif self.run.phase == "boss_relic" and self.run.reward is not None:
            options = [
                discord.SelectOption(
                    label=RELIC_LIBRARY[key].name,
                    value=str(index),
                    description=_truncate(RELIC_LIBRARY[key].description),
                )
                for index, key in enumerate(self.run.reward.relic_choices)
            ]
            if options:
                self.add_item(
                    ActionSelect(
                        placeholder="Choose a boss relic",
                        action="boss_relic_choice",
                        options=options,
                    )
                )
        elif self.run.phase == "treasure":
            self.add_item(ActionButton("Take Relic", discord.ButtonStyle.success, "treasure_relic"))
            if "sapphire" not in self.run.keys:
                self.add_item(ActionButton("Take Sapphire Key", discord.ButtonStyle.primary, "treasure_key"))
        elif self.run.phase == "rest":
            if "coffee_dripper" not in self.run.relics:
                self.add_item(ActionButton("Rest", discord.ButtonStyle.success, "rest"))
            if "fusion_hammer" not in self.run.relics:
                self.add_item(ActionButton("Smith", discord.ButtonStyle.primary, "smith"))
            if "shovel" in self.run.relics:
                self.add_item(ActionButton("Dig", discord.ButtonStyle.primary, "dig"))
            if "girya" in self.run.relics and int(self.run.meta.get("girya_lifts", 0)) < 3:
                self.add_item(ActionButton("Lift", discord.ButtonStyle.primary, "lift"))
            if "peace_pipe" in self.run.relics:
                self.add_item(ActionButton("Toke", discord.ButtonStyle.primary, "toke"))
            if "ruby" not in self.run.keys and self.run.act < 4:
                self.add_item(ActionButton("Recall", discord.ButtonStyle.danger, "recall"))
            self.add_item(ActionButton("Deck", discord.ButtonStyle.secondary, "show_deck"))
        elif self.run.phase == "shop" and self.run.shop is not None:
            if self.run.shop.offers:
                options = []
                for offer in self.run.shop.offers:
                    if offer.kind == "card":
                        prefix = "Sale: " if offer.sale else ""
                        label = f"{prefix}{CARD_LIBRARY[offer.key].name} - {offer.cost}g"
                        description = CARD_LIBRARY[offer.key].description
                    elif offer.kind == "potion":
                        label = f"{self.cog.potion_name(offer.key)} - {offer.cost}g"
                        description = self.cog.potion_description(offer.key)
                    else:
                        label = f"{RELIC_LIBRARY[offer.key].name} - {offer.cost}g"
                        description = RELIC_LIBRARY[offer.key].description
                    options.append(
                        discord.SelectOption(
                            label=_truncate(label, 95),
                            value=offer.offer_id,
                            description=_truncate(description),
                        )
                    )
                self.add_item(
                    ActionSelect(
                        placeholder="Buy an item",
                        action="shop_buy",
                        options=options,
                    )
                )
            self.add_item(ActionButton("Remove Card", discord.ButtonStyle.primary, "shop_remove"))
            self.add_item(ActionButton("Leave Shop", discord.ButtonStyle.secondary, "leave_shop"))
            self.add_item(ActionButton("Deck", discord.ButtonStyle.secondary, "show_deck"))
        elif self.run.phase == "event" and self.run.event is not None:
            options = [
                discord.SelectOption(
                    label=option.label,
                    value=option.option_id,
                    description=_truncate(option.description),
                )
                for option in self.run.event.options
            ]
            self.add_item(
                ActionSelect(
                    placeholder="Choose an event option",
                    action="event_choice",
                    options=options,
                )
            )
            self.add_item(ActionButton("Deck", discord.ButtonStyle.secondary, "show_deck"))
        elif self.run.phase in {"upgrade", "remove"}:
            placeholder = "Choose a card"
            if self.run.phase == "remove" and (
                self.run.selection_context == "transform"
                or (self.run.selection_context or "").startswith("transform:")
            ):
                placeholder = "Choose a card to transform"
            elif self.run.phase == "remove" and self.run.selection_context == "bonfire":
                placeholder = "Choose an offering"
            elif self.run.phase == "remove" and (self.run.selection_context or "").startswith("astrolabe:"):
                placeholder = "Choose a card to transform"
            elif self.run.phase == "remove" and (self.run.selection_context or "").startswith("empty_cage:"):
                placeholder = "Choose a card to remove"
            elif self.run.phase == "remove" and (self.run.selection_context or "").startswith("bottle:"):
                placeholder = "Choose a card to bottle"
            elif self.run.phase == "remove" and self.run.selection_context == "dollys_mirror":
                placeholder = "Choose a card to duplicate"
            elif self.run.phase == "remove" and self.run.selection_context == "duplicator":
                placeholder = "Choose a card to duplicate"
            elif self.run.phase == "remove" and self.run.selection_context == "peace_pipe":
                placeholder = "Choose a card to remove"
            elif self.run.phase == "remove" and (self.run.selection_context or "").startswith("forbidden_grimoire:"):
                placeholder = "Choose a card to remove"
            bottle_restriction = None
            if (self.run.selection_context or "").startswith("bottle:"):
                bottle_restriction = {
                    "bottled_flame": "attack",
                    "bottled_lightning": "skill",
                    "bottled_tornado": "power",
                }.get((self.run.selection_context or "").split(":", 1)[1])
            options = [
                discord.SelectOption(
                    label=_truncate(self.cog.engine.card_name(card), 95),
                    value=card.instance_id,
                    description=_truncate(self.cog.engine.card_description(card)),
                )
                for card in self.run.deck
                if (self.run.phase != "upgrade" or not card.upgraded)
                and (bottle_restriction is None or CARD_LIBRARY[card.key].card_type == bottle_restriction)
            ]
            if options:
                self.add_item(
                    ActionSelect(
                        placeholder=placeholder,
                        action=f"{self.run.phase}_choice",
                        options=options[:25],
                    )
                )
            if self.run.selection_context not in {"event", "transform", "bonfire", "dollys_mirror", "duplicator"} and not (
                self.run.selection_context or ""
            ).startswith(("transform:", "astrolabe:", "empty_cage:", "bottle:")):
                self.add_item(ActionButton("Cancel", discord.ButtonStyle.secondary, "cancel_selection"))
            self.add_item(ActionButton("Deck", discord.ButtonStyle.secondary, "show_deck"))
        elif self.run.phase in {"victory", "defeat"}:
            self.add_item(ActionButton("Deck", discord.ButtonStyle.secondary, "show_deck"))

        if self.run.phase not in {"victory", "defeat"}:
            self.add_item(ActionButton("Abandon", discord.ButtonStyle.danger, "abandon"))
