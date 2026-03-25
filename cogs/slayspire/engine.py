from __future__ import annotations

import copy
import random
from functools import lru_cache
from itertools import combinations

from .content import (
    BOSS_RELIC_POOL,
    BOSS_ENCOUNTERS_BY_ACT,
    CARD_LIBRARY,
    CHARACTER_LIBRARY,
    COMMON_ENCOUNTER_TEMPLATES_BY_ACT,
    ELITE_ENCOUNTERS_BY_ACT,
    ENEMY_LIBRARY,
    EVENT_LIBRARY,
    POTION_LIBRARY,
    POTION_POOL,
    RELIC_LIBRARY,
    SHOP_RELIC_POOL,
    TREASURE_RELIC_POOL,
)
from .models import (
    CardInstance,
    CombatState,
    EnemyState,
    EventOptionState,
    EventState,
    RewardState,
    RunState,
    ShopOffer,
    ShopState,
)


class SpireEngine:
    ACT_COUNT = 3
    FLOORS_PER_ACT = 17
    ACT4_FLOORS = 4
    MAP_COLUMNS = 7
    MAP_NODE_ROWS = FLOORS_PER_ACT - 2
    MAP_BOSS_FLOOR = FLOORS_PER_ACT - 1
    MAX_FLOORS = ACT_COUNT * FLOORS_PER_ACT + ACT4_FLOORS
    MAP_ROOM_WEIGHTS = {
        "combat": 53,
        "elite": 8,
        "rest": 12,
        "shop": 5,
        "event": 22,
    }
    DEBUFF_STATUSES = {
        "confused",
        "constricted",
        "debilitate",
        "doom",
        "frail",
        "hex",
        "lock_on",
        "poison",
        "vulnerable",
        "weak",
    }
    CHARACTER_RELICS = {
        "ironclad": {
            "burning_blood",
            "black_blood",
            "champion_belt",
            "paper_frog",
            "red_skull",
            "self_forming_clay",
            "charons_ashes",
            "runic_cube",
            "mark_of_pain",
            "brimstone",
        },
        "silent": {
            "ring_of_the_snake",
            "ring_of_the_serpent",
            "snecko_skull",
            "tingsha",
            "tough_bandages",
            "the_specimen",
            "hovering_kite",
            "wrist_blade",
            "twisted_funnel",
        },
        "defect": {
            "cracked_core",
            "frozen_core",
            "data_disk",
            "gold_plated_cables",
            "emotion_chip",
            "runic_capacitor",
            "inserter",
            "nuclear_battery",
        },
        "watcher": {
            "pure_water",
            "holy_water",
            "damaru",
            "teardrop_locket",
            "cloak_clasp",
            "melange",
            "violet_lotus",
        },
        "necrobinder": {
            "bound_phylactery",
            "phylactery_unbound",
            "bone_flute",
            "book_repair_knife",
            "funerary_mask",
            "big_hat",
            "bookmark",
            "ivory_tile",
            "undying_sigil",
        },
    }

    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()

    def _relic_matches_character(self, run: RunState, relic_key: str) -> bool:
        for character, relics in self.CHARACTER_RELICS.items():
            if relic_key in relics:
                return character == run.character
        return True

    def _eligible_relic_candidates(
        self,
        run: RunState,
        pool: list[str],
        *,
        exclude: set[str] | None = None,
        rarities: set[str] | None = None,
        allow_special: bool = False,
    ) -> list[str]:
        exclude_keys = exclude or set()
        candidates: list[str] = []
        for relic_key in pool:
            if relic_key in run.relics or relic_key in exclude_keys:
                continue
            relic = RELIC_LIBRARY[relic_key]
            if not allow_special and relic.rarity in {"starter", "special"}:
                continue
            if rarities is not None and relic.rarity not in rarities:
                continue
            if not self._relic_matches_character(run, relic_key):
                continue
            candidates.append(relic_key)
        return candidates

    def start_new_run(
        self,
        *,
        user_id: int,
        guild_id: int,
        channel_id: int,
        character: str = "ironclad",
    ) -> RunState:
        character_key = character.lower().strip()
        if character_key not in CHARACTER_LIBRARY:
            raise ValueError(f"Unsupported character: {character}")

        character_def = CHARACTER_LIBRARY[character_key]
        run = RunState(
            user_id=user_id,
            guild_id=guild_id,
            channel_id=channel_id,
            character=character_key,
            max_hp=int(character_def["max_hp"]),
            hp=int(character_def["max_hp"]),
            gold=99,
            relics=[],
        )
        self._obtain_relic(run, str(character_def["starter_relic"]))
        for card_key in character_def["starting_deck"]:
            run.deck.append(self.create_card_instance(run, card_key))
        run.push_log(f"{character_def['name']} enters the Spire.")
        self._prepare_neow_options(run)
        run.phase = "neow"
        return run

    def _prepare_neow_options(self, run: RunState) -> None:
        blessing = self.rng.choice(
            [
                ("remove_card", "Remove a card from your deck."),
                ("upgrade_card", "Upgrade a card in your deck."),
                ("choose_class_card", "Choose a card to add to your deck."),
                ("random_rare_card", "Obtain a random Rare card."),
            ]
        )
        support = self.rng.choice(
            [
                ("max_hp_bonus", f"Gain {self._neow_max_hp_bonus(run)} Max HP."),
                ("common_relic", "Obtain a random common relic."),
                ("gold_100", "Gain 100 Gold."),
                ("potions_3", "Obtain 3 random potions."),
                ("neows_lament", "Enemies in your next 3 combats have 1 HP."),
            ]
        )
        tradeoff = self.rng.choice(
            [
                ("lose_max_hp_gain_250", f"Lose {self._neow_max_hp_cost(run)} Max HP. Gain 250 Gold."),
                ("damage_rare_relic", "Lose 30% of your current HP. Obtain a random rare relic."),
                ("curse_remove_2", "Obtain a Curse. Remove 2 cards from your deck."),
                ("lose_gold_rare_card", "Lose all Gold. Choose a Rare card to obtain."),
            ]
        )
        boss_swap = ("replace_starter_boss", "Replace your starter relic with a random Boss relic.")
        run.event = EventState(
            key="neow",
            name="Neow",
            description="Another life. Another try. Choose your blessing.",
            options=[
                EventOptionState(option_id=blessing[0], label="Blessing", description=blessing[1]),
                EventOptionState(option_id=support[0], label="Boon", description=support[1]),
                EventOptionState(option_id=tradeoff[0], label="Tradeoff", description=tradeoff[1]),
                EventOptionState(option_id=boss_swap[0], label="Boss Swap", description=boss_swap[1]),
            ],
        )
        run.selection_context = None

    def _neow_max_hp_bonus(self, run: RunState) -> int:
        return {"ironclad": 8, "silent": 7, "defect": 7, "watcher": 7, "necrobinder": 6}[run.character]

    def _neow_max_hp_cost(self, run: RunState) -> int:
        return {"ironclad": 8, "silent": 6, "defect": 7, "watcher": 7, "necrobinder": 6}[run.character]

    def create_card_instance(
        self,
        run: RunState,
        key: str,
        *,
        upgraded: bool = False,
        misc: int = 0,
        cost_adjustment: int = 0,
    ) -> CardInstance:
        instance = CardInstance(
            instance_id=f"c{run.next_instance_id}",
            key=key,
            upgraded=upgraded,
            misc=misc,
            cost_adjustment=cost_adjustment,
        )
        run.next_instance_id += 1
        return instance

    def _max_potion_slots(self, run: RunState) -> int:
        return 3 + (2 if "potion_belt" in run.relics else 0)

    def _can_heal_run(self, run: RunState) -> bool:
        return "mark_of_the_bloom" not in run.relics

    def _heal_run(self, run: RunState, amount: int) -> int:
        if amount <= 0 or not self._can_heal_run(run):
            return 0
        old_hp = run.hp
        run.hp = min(run.max_hp, run.hp + amount)
        return run.hp - old_hp

    def _increase_max_hp(self, run: RunState, amount: int, *, heal_current: bool = True) -> int:
        if amount <= 0:
            return 0
        run.max_hp += amount
        if heal_current:
            return self._heal_run(run, amount)
        run.hp = min(run.hp, run.max_hp)
        return 0

    def _gain_gold(self, run: RunState, amount: int) -> int:
        if amount <= 0:
            return 0
        if "ectoplasm" in run.relics:
            return 0
        run.gold += amount
        if "bloody_idol" in run.relics:
            self._heal_run(run, 5)
        return amount

    def _queue_pending_transition(self, run: RunState, *, act_advance: bool) -> None:
        run.meta["pending_transition"] = {"act_advance": 1 if act_advance else 0}

    def _complete_pending_transition(self, run: RunState) -> bool:
        payload = run.meta.pop("pending_transition", None)
        if not isinstance(payload, dict):
            return False
        if int(payload.get("act_advance", 0)):
            run.act += 1
            run.act_floor = 0
        self._prepare_map_choices(run)
        run.phase = "map"
        run.selection_context = None
        run.reward = None
        run.shop = None
        run.event = None
        return True

    def _resume_after_delayed_choice(self, run: RunState) -> None:
        if self._complete_pending_transition(run):
            return
        return_phase = str(run.meta.pop("pending_selection_return", "advance"))
        run.selection_context = None
        if return_phase == "shop":
            run.phase = "shop"
            run.reward = None
            run.event = None
            return
        if return_phase == "combat":
            run.phase = "combat"
            run.reward = None
            run.event = None
            return
        self._advance_after_noncombat(run)

    def _remember_delayed_choice_return(self, run: RunState) -> None:
        if "pending_transition" in run.meta:
            return
        if run.phase == "shop":
            run.meta["pending_selection_return"] = "shop"
        elif run.phase == "combat":
            run.meta["pending_selection_return"] = "combat"
        else:
            run.meta["pending_selection_return"] = "advance"

    def _trigger_combat_hp_loss_relics(
        self,
        run: RunState,
        combat: CombatState,
        amount: int,
        messages: list[str] | None = None,
    ) -> None:
        if amount <= 0:
            return
        self._sync_player_hp_relics(run, combat, messages)
        if "runic_cube" in run.relics:
            self._draw_cards(run, combat, 1)
            if messages is not None:
                messages.append("Runic Cube draws 1 card.")
            else:
                combat.log.append("Runic Cube draws 1 card.")
        if "self_forming_clay" in run.relics:
            combat.player_statuses["next_turn_block"] = (
                combat.player_statuses.get("next_turn_block", 0) + 3
            )
            if messages is not None:
                messages.append("Self-Forming Clay prepares 3 Block for next turn.")
            else:
                combat.log.append("Self-Forming Clay prepares 3 Block for next turn.")
        if "emotion_chip" in run.relics:
            combat.player_statuses["emotion_chip_ready"] = 1
            if messages is not None:
                messages.append("Emotion Chip will trigger your first Orb an extra time.")
            else:
                combat.log.append("Emotion Chip will trigger your first Orb an extra time.")

    def _sync_player_hp_relics(
        self,
        run: RunState,
        combat: CombatState | None,
        messages: list[str] | None = None,
    ) -> None:
        if combat is None or "red_skull" not in run.relics:
            return
        low_hp = run.hp * 2 <= run.max_hp
        active = combat.player_statuses.get("red_skull_active", 0) > 0
        if low_hp and not active:
            combat.player_statuses["strength"] = combat.player_statuses.get("strength", 0) + 3
            combat.player_statuses["red_skull_active"] = 1
            if messages is not None:
                messages.append("Red Skull grants 3 Strength.")
        elif active and not low_hp:
            combat.player_statuses["strength"] = combat.player_statuses.get("strength", 0) - 3
            if combat.player_statuses["strength"] == 0:
                combat.player_statuses.pop("strength", None)
            combat.player_statuses.pop("red_skull_active", None)
            if messages is not None:
                messages.append("Red Skull's Strength fades.")

    def _opening_hand_relic_card_ids(self, run: RunState) -> list[str]:
        ids: list[str] = []
        for relic_key in ("bottled_flame", "bottled_lightning", "bottled_tornado"):
            instance_id = run.meta.get(f"{relic_key}_card")
            if isinstance(instance_id, str):
                ids.append(instance_id)
        return ids

    def _clear_bound_relic_card(self, run: RunState, instance_id: str) -> None:
        for relic_key in ("bottled_flame", "bottled_lightning", "bottled_tornado"):
            if run.meta.get(f"{relic_key}_card") == instance_id:
                run.meta.pop(f"{relic_key}_card", None)

    def _roll_toolbox_cards(self) -> list[str]:
        choices: list[str] = []
        used: set[str] = set()
        for rarity in ("uncommon", "uncommon", "rare"):
            choice = self._pick_colorless_card(rarity=rarity, exclude=used)
            if choice is None:
                continue
            used.add(choice)
            choices.append(choice)
        return choices

    def start_specific_combat(
        self, run: RunState, enemy_key: str | tuple[str, ...], encounter_kind: str
    ) -> None:
        enemy_keys = (
            list(enemy_key)
            if isinstance(enemy_key, tuple)
            else [str(enemy_key)]
        )
        enemies: list[EnemyState] = []
        reward_gold = 0
        for index, key in enumerate(enemy_keys, start=1):
            enemy = self._build_enemy_state(key, encounter_kind, run.relics, index)
            enemy_reward_gold = self.rng.randint(*ENEMY_LIBRARY[key].gold_range)
            enemy.meta["reward_gold"] = enemy_reward_gold
            reward_gold += enemy_reward_gold
            enemies.append(enemy)
        deck_cards = [copy.deepcopy(card) for card in run.deck]
        innate_cards = [card for card in deck_cards if self.card_innate(card)]
        draw_pile = [card for card in deck_cards if not self.card_innate(card)]
        self.rng.shuffle(draw_pile)
        bottled_ids = self._opening_hand_relic_card_ids(run)
        for bottled_id in bottled_ids:
            for pile in (draw_pile, innate_cards):
                bottled = self._find_card(pile, bottled_id)
                if bottled is None:
                    continue
                if bottled not in innate_cards:
                    pile.remove(bottled)
                    innate_cards.append(bottled)
                break
        combat = CombatState(
            encounter_kind=encounter_kind,
            enemies=enemies,
            hand=innate_cards,
            draw_pile=draw_pile,
            player_statuses=self._combat_statuses_from_relics(run),
            reward_gold=reward_gold,
        )
        combat.player_meta["combat_start_hp"] = run.hp
        combat.player_meta["cards_drawn_turn"] = 0
        combat.player_meta["osty_attacks_turn"] = 0
        combat.player_meta["osty_attacks_combat"] = 0
        combat.player_meta["played_card_keys_turn"] = {}
        combat.max_energy += sum(
            1
            for relic_key in run.relics
            if relic_key in {
                "coffee_dripper",
                "cursed_key",
                "ectoplasm",
                "fusion_hammer",
                "mark_of_pain",
                "philosophers_stone",
                "runic_dome",
                "sozu",
                "velvet_choker",
            }
        )
        if encounter_kind in {"elite", "boss"} and "slavers_collar" in run.relics:
            combat.max_energy += 1
        if "philosophers_stone" in run.relics:
            for enemy in combat.enemies:
                enemy.statuses["strength"] = enemy.statuses.get("strength", 0) + 1
        for enemy in combat.enemies:
            if enemy.key == "centurion":
                enemy.current_intent_index = self._choose_centurion_intent(enemy, combat, opening=True)
            elif enemy.key == "mystic":
                enemy.current_intent_index = self._choose_mystic_intent(enemy, combat, opening=True)
            elif enemy.key == "hexaghost":
                enemy.current_intent_index = self._choose_hexaghost_intent(enemy, opening=True)
            elif enemy.key == "writhing_mass":
                enemy.current_intent_index = self._choose_writhing_mass_intent(enemy, opening=True)
            elif enemy.key == "the_maw":
                enemy.current_intent_index = self._choose_maw_intent(enemy, opening=True)
            elif enemy.key == "the_champ":
                enemy.current_intent_index = self._choose_champ_intent(enemy, combat, opening=True)
            elif enemy.key == "the_collector":
                enemy.current_intent_index = self._choose_collector_intent(enemy, combat, opening=True)
            elif enemy.key == "awakened_one":
                enemy.current_intent_index = self._choose_awakened_one_intent(enemy, opening=True)
            elif enemy.key == "bronze_automaton":
                enemy.current_intent_index = self._choose_bronze_automaton_intent(enemy, combat, opening=True)
            elif enemy.key == "donu":
                enemy.current_intent_index = self._choose_donu_intent(enemy, opening=True)
            elif enemy.key == "deca":
                enemy.current_intent_index = self._choose_deca_intent(enemy, opening=True)
            elif enemy.key == "reptomancer":
                enemy.current_intent_index = self._choose_reptomancer_intent(enemy, combat, opening=True)
            elif enemy.key == "time_eater":
                enemy.current_intent_index = self._choose_time_eater_intent(enemy, opening=True)
            elif enemy.key == "corrupt_heart":
                enemy.current_intent_index = self._choose_corrupt_heart_intent(enemy, opening=True)
        if "anchor" in run.relics:
            combat.player_block += 10
            combat.log.append("Anchor grants 10 Block.")
        if "bag_of_marbles" in run.relics:
            for enemy in combat.enemies:
                self._apply_status_to_enemy(enemy, "vulnerable", 1)
            combat.log.append("Bag Of Marbles applies 1 Vulnerable to all enemies.")
        if "red_mask" in run.relics:
            for enemy in combat.enemies:
                self._apply_status_to_enemy(enemy, "weak", 1)
            combat.log.append("Red Mask applies 1 Weak to all enemies.")
        if "mutagenic_strength" in run.relics:
            self._modify_status(combat.player_statuses, "strength", 3, temporary=True)
            combat.log.append("Mutagenic Strength grants 3 Strength.")
        if run.character == "defect":
            combat.orb_slots = 3
        if "prismatic_shard" in run.relics and combat.orb_slots <= 0:
            combat.orb_slots = 1
        if "inserter" in run.relics:
            combat.orb_slots += 1
        if "runic_capacitor" in run.relics:
            combat.orb_slots += 3
        if "cracked_core" in run.relics:
            self._channel_orb(combat, "lightning")
        if "nuclear_battery" in run.relics:
            self._channel_orb(combat, "plasma")
        draw_count = max(0, 5 - len(innate_cards))
        if "bag_of_preparation" in run.relics or "ring_of_the_snake" in run.relics:
            draw_count += 2
        if "ring_of_the_serpent" in run.relics:
            draw_count += 1
        if "snecko_eye" in run.relics:
            draw_count += 2
        combat.energy = combat.max_energy + (1 if "lantern" in run.relics else 0)
        if run.meta.pop("ancient_tea_set_ready", 0):
            combat.energy += 2
            combat.log.append("Ancient Tea Set grants 2 Energy.")
        if encounter_kind == "boss" and "pantograph" in run.relics:
            healed = self._heal_run(run, 25)
            if healed > 0:
                combat.log.append(f"Pantograph heals {healed} HP.")
        if "blood_vial" in run.relics:
            healed = self._heal_run(run, 2)
            if healed > 0:
                combat.log.append(f"Blood Vial heals {healed} HP.")
        if encounter_kind == "elite" and "sling_of_courage" in run.relics:
            combat.player_statuses["strength"] = combat.player_statuses.get("strength", 0) + 2
            combat.log.append("Sling Of Courage grants 2 Strength.")
        if "teardrop_locket" in run.relics:
            combat.stance = "calm"
            combat.log.append("Teardrop Locket enters Calm.")
        if "twisted_funnel" in run.relics:
            for enemy in combat.enemies:
                self._apply_status_to_enemy(enemy, "poison", 4)
            combat.log.append("Twisted Funnel applies 4 Poison to all enemies.")
        if "mark_of_pain" in run.relics:
            combat.log.extend(self._create_cards_in_combat(run, combat, key="wound", location="draw", count=2))
        if run.character == "necrobinder":
            self._apply_necrobinder_opening_effects(run, combat)
        self._sync_player_hp_relics(run, combat, combat.log)
        if run.character == "necrobinder":
            self._apply_necrobinder_turn_start_effects(run, combat)
        self._draw_cards(run, combat, draw_count)
        if "pure_water" in run.relics:
            combat.hand.append(self.create_card_instance(run, "miracle"))
        if "holy_water" in run.relics:
            for _ in range(3):
                combat.hand.append(self.create_card_instance(run, "miracle"))
        if "damaru" in run.relics:
            _, messages = self._apply_status_to_player(combat, "mantra", 1)
            combat.log.extend(message.replace("You gain 1 Mantra.", "Damaru grants 1 Mantra.") for message in messages)
        lament = int(run.meta.get("neows_lament", 0))
        if lament > 0:
            for enemy in combat.enemies:
                enemy.hp = min(enemy.hp, 1)
            run.meta["neows_lament"] = lament - 1
            if run.meta["neows_lament"] <= 0:
                run.meta.pop("neows_lament", None)
            combat.log.append("Neow's Lament reduces all enemies to 1 HP.")
        if "brimstone" in run.relics:
            combat.player_statuses["strength"] = combat.player_statuses.get("strength", 0) + 2
            for enemy in combat.enemies:
                enemy.statuses["strength"] = enemy.statuses.get("strength", 0) + 1
            combat.log.append("Brimstone grants you 2 Strength and all enemies 1 Strength.")
        run.combat = combat
        run.reward = None
        run.shop = None
        run.event = None
        run.phase = "combat"
        if "toolbox" in run.relics:
            run.reward = RewardState(
                source="toolbox",
                gold=0,
                card_choices=self._roll_toolbox_cards(),
            )
            run.phase = "reward"
            run.selection_context = None
        elif "gambling_chip" in run.relics and combat.hand:
            run.selection_context = "gambling_chip"
        else:
            run.selection_context = None
        encounter_names = ", ".join(enemy.name for enemy in enemies)
        run.push_log(f"Floor {run.floor}: {encounter_names} block the path.")

    def _encounter_pool_for_act(
        self,
        pools_by_act: dict[int, list[tuple[str, ...]]],
        act: int,
    ) -> list[tuple[str, ...]]:
        pool_act = max(1, min(act, self.ACT_COUNT))
        return pools_by_act[pool_act]

    def _common_encounter_history(self, run: RunState) -> list[str]:
        history_by_act = run.meta.get("monster_encounter_history")
        if not isinstance(history_by_act, dict):
            history_by_act = {}
            run.meta["monster_encounter_history"] = history_by_act
        act_key = str(max(1, min(run.act, self.ACT_COUNT)))
        history = history_by_act.get(act_key)
        if not isinstance(history, list):
            history = []
        history = [str(entry) for entry in history]
        history_by_act[act_key] = history
        return history

    def _common_encounter_template_pool(self, run: RunState) -> list[str]:
        act = max(1, min(run.act, self.ACT_COUNT))
        table = COMMON_ENCOUNTER_TEMPLATES_BY_ACT[act]
        history = self._common_encounter_history(run)
        early_count = int(table["early_count"])
        pool_key = "early" if len(history) < early_count else "late"
        pool = [str(entry) for entry in list(table[pool_key])]
        recent = set(history[-2:])
        filtered = [entry for entry in pool if entry not in recent]
        return filtered or pool

    def _random_shape_group(self, count: int) -> tuple[str, ...]:
        shapes = ["repulsor", "repulsor", "spiker", "spiker", "exploder", "exploder"]
        return tuple(str(entry) for entry in self.rng.sample(shapes, count))

    def _random_gremlin_gang(self) -> tuple[str, ...]:
        gremlins = [
            "mad_gremlin",
            "mad_gremlin",
            "sneaky_gremlin",
            "sneaky_gremlin",
            "fat_gremlin",
            "fat_gremlin",
            "gremlin_wizard",
            "shield_gremlin",
        ]
        return tuple(str(entry) for entry in self.rng.sample(gremlins, 4))

    def _resolve_common_encounter_template(self, template_id: str) -> tuple[str, ...]:
        if template_id == "cultist":
            return ("cultist",)
        if template_id == "jaw_worm":
            return ("jaw_worm",)
        if template_id == "two_louses":
            return (
                self.rng.choice(["red_louse", "green_louse"]),
                self.rng.choice(["red_louse", "green_louse"]),
            )
        if template_id == "small_slimes":
            return (
                self.rng.choice(["acid_slime", "spike_slime"]),
                self.rng.choice(["acid_slime_small", "spike_slime_small"]),
            )
        if template_id == "gremlin_gang":
            return self._random_gremlin_gang()
        if template_id == "large_slime":
            return (self.rng.choice(["acid_slime_large", "spike_slime_large"]),)
        if template_id == "lots_of_slimes":
            return (
                "spike_slime_small",
                "spike_slime_small",
                "spike_slime_small",
                "acid_slime_small",
                "acid_slime_small",
            )
        if template_id == "blue_slaver":
            return ("blue_slaver",)
        if template_id == "red_slaver":
            return ("red_slaver",)
        if template_id == "three_louses":
            return (
                self.rng.choice(["red_louse", "green_louse"]),
                self.rng.choice(["red_louse", "green_louse"]),
                self.rng.choice(["red_louse", "green_louse"]),
            )
        if template_id == "two_fungi_beasts":
            return ("fungi_beast", "fungi_beast")
        if template_id == "exordium_thugs":
            return (
                self.rng.choice(["red_louse", "green_louse", "acid_slime", "spike_slime"]),
                self.rng.choice(["looter", "cultist", "blue_slaver", "red_slaver"]),
            )
        if template_id == "exordium_wildlife":
            return (
                self.rng.choice(["fungi_beast", "jaw_worm"]),
                self.rng.choice(["red_louse", "green_louse", "acid_slime", "spike_slime"]),
            )
        if template_id == "spheric_guardian":
            return ("spheric_guardian",)
        if template_id == "chosen":
            return ("chosen",)
        if template_id == "shelled_parasite":
            return ("shelled_parasite",)
        if template_id == "three_byrds":
            return ("byrd", "byrd", "byrd")
        if template_id == "thieves":
            return ("looter", "mugger")
        if template_id == "chosen_and_byrd":
            return ("chosen", "byrd")
        if template_id == "cultist_and_chosen":
            return ("cultist", "chosen")
        if template_id == "sentry_and_spheric_guardian":
            return ("sentry", "spheric_guardian")
        if template_id == "snake_plant":
            return ("snake_plant",)
        if template_id == "snecko":
            return ("snecko",)
        if template_id == "centurion_and_mystic":
            return ("centurion", "mystic")
        if template_id == "three_cultists":
            return ("cultist", "cultist", "cultist")
        if template_id == "shelled_parasite_and_fungi_beast":
            return ("shelled_parasite", "fungi_beast")
        if template_id == "three_darklings":
            return ("darkling", "darkling", "darkling")
        if template_id == "orb_walker":
            return ("orb_walker",)
        if template_id == "three_shapes":
            return self._random_shape_group(3)
        if template_id == "four_shapes":
            return self._random_shape_group(4)
        if template_id == "the_maw":
            return ("the_maw",)
        if template_id == "spheric_guardian_and_shapes":
            return ("spheric_guardian", *self._random_shape_group(2))
        if template_id == "writhing_mass":
            return ("writhing_mass",)
        if template_id == "jaw_worm_horde":
            return ("jaw_worm", "jaw_worm", "jaw_worm")
        if template_id == "spire_growth":
            return ("spire_growth",)
        if template_id == "transient":
            return ("transient",)
        raise ValueError(f"Unsupported common encounter template: {template_id}")

    def _roll_common_encounter(self, run: RunState) -> tuple[str, ...]:
        template_id = self.rng.choice(self._common_encounter_template_pool(run))
        self._common_encounter_history(run).append(str(template_id))
        return self._resolve_common_encounter_template(str(template_id))

    def _roll_elite_encounter(self, run: RunState) -> tuple[str, ...]:
        encounters = self._encounter_pool_for_act(ELITE_ENCOUNTERS_BY_ACT, run.act)
        return self.rng.choice(encounters)

    def _roll_boss_encounter(self, run: RunState) -> tuple[str, ...]:
        encounters = self._encounter_pool_for_act(BOSS_ENCOUNTERS_BY_ACT, run.act)
        return self.rng.choice(encounters)

    def alive_enemies(self, run: RunState) -> list[EnemyState]:
        if run.combat is None:
            return []
        return [enemy for enemy in run.combat.enemies if enemy.hp > 0]

    def _default_target_enemy(self, combat: CombatState) -> EnemyState | None:
        return next((enemy for enemy in combat.enemies if enemy.hp > 0), None)

    def _prune_enemies(self, enemies: list[EnemyState]) -> list[EnemyState]:
        return [
            enemy
            for enemy in enemies
            if enemy.hp > 0 or int(enemy.meta.get("revive_pending", 0)) > 0
        ]

    def _has_remaining_enemies(self, combat: CombatState) -> bool:
        return any(enemy.hp > 0 for enemy in combat.enemies)

    def _other_living_darkling_exists(
        self,
        combat: CombatState,
        enemy_id: str,
    ) -> bool:
        return any(
            enemy.key == "darkling" and enemy.enemy_id != enemy_id and enemy.hp > 0
            for enemy in combat.enemies
        )

    def card_needs_target(self, run: RunState, card: CardInstance) -> bool:
        if run.combat is None:
            return False
        card_def = CARD_LIBRARY[card.key]
        return card_def.target == "enemy" and len(self.alive_enemies(run)) > 1

    def potion_needs_target(self, run: RunState, potion_key: str) -> bool:
        if run.combat is None:
            return False
        potion = POTION_LIBRARY[potion_key]
        return potion.target == "enemy" and len(self.alive_enemies(run)) > 1

    def list_playable_targets(self, run: RunState) -> list[EnemyState]:
        return self.alive_enemies(run)

    def map_node_type(self, run: RunState, entry: str) -> str:
        node = self.map_node_data(run, entry)
        if node is not None:
            return str(node.get("node_type", entry))
        return entry

    def map_node_data(self, run: RunState, entry: str) -> dict[str, object] | None:
        map_state = self._current_act_map(run)
        if map_state is not None:
            nodes = {
                str(node["id"]): node
                for node in list(map_state.get("nodes", []))
                if isinstance(node, dict) and "id" in node
            }
            node = nodes.get(entry)
            if node is not None:
                return node
            if entry == "boss":
                return {
                    "id": f"act{run.act}-boss",
                    "row": self.MAP_BOSS_FLOOR,
                    "col": self.MAP_COLUMNS // 2,
                    "node_type": "boss",
                }
        if run.act == 4:
            act4_nodes = {
                "rest": {"id": "act4-rest", "row": 1, "col": 3, "node_type": "rest"},
                "shop": {"id": "act4-shop", "row": 2, "col": 3, "node_type": "shop"},
                "elite_key": {"id": "act4-elite", "row": 3, "col": 3, "node_type": "elite_key"},
                "boss": {"id": "act4-boss", "row": 4, "col": 3, "node_type": "boss"},
            }
            return act4_nodes.get(entry)
        return None

    def map_choice_label(self, run: RunState, entry: str) -> str:
        node_type = self.map_node_type(run, entry)
        node = self.map_node_data(run, entry)
        if node is not None:
            row = int(node.get("row", 0))
            col = int(node.get("col", 0)) + 1
            return f"{self._node_label(node_type)} F{row} C{col}"
        return self._node_label(node_type)

    def map_choice_description(self, run: RunState, entry: str) -> str:
        node = self.map_node_data(run, entry)
        if node is not None:
            row = int(node.get("row", 0))
            col = int(node.get("col", 0)) + 1
            node_id = str(node.get("id", entry))
            return f"Floor {row}, Column {col}, Node {node_id}"
        return f"Choose {self._node_label(self.map_node_type(run, entry)).lower()}."

    def _current_act_map(self, run: RunState) -> dict[str, object] | None:
        act_map = run.meta.get("act_map")
        if not isinstance(act_map, dict):
            return None
        if int(act_map.get("act", 0)) != run.act:
            return None
        self._normalize_act_map_connections(act_map)
        return act_map

    def _node_label(self, node: str) -> str:
        labels = {
            "combat": "Combat",
            "elite": "Elite",
            "rest": "Rest Site",
            "shop": "Shop",
            "event": "Unknown",
            "treasure": "Treasure",
            "elite_key": "Burning Elite",
            "boss": "Boss",
        }
        return labels.get(node, node.title())

    def _map_adjacent_columns(self, col: int) -> list[int]:
        return sorted(
            {
                max(0, min(self.MAP_COLUMNS - 1, col + delta))
                for delta in (-1, 0, 1)
            }
        )

    def _map_target_candidates(
        self,
        source_col: int,
        *,
        desired_count: int,
        available_cols: set[int] | None = None,
    ) -> list[tuple[int, ...]]:
        options = [
            col
            for col in self._map_adjacent_columns(source_col)
            if available_cols is None or col in available_cols
        ]
        if not options:
            options = self._map_adjacent_columns(source_col)
        if desired_count < 1 or desired_count > len(options):
            desired_count = len(options)
        candidates = list(combinations(options, desired_count))
        if candidates:
            return candidates
        for size in range(1, len(options) + 1):
            candidates = list(combinations(options, size))
            if candidates:
                return candidates
        return [(source_col,)]

    def _resolve_non_crossing_map_targets(
        self,
        source_specs: list[dict[str, object]],
    ) -> dict[int, list[int]]:
        if not source_specs:
            return {}

        normalized_specs: list[dict[str, object]] = []
        for spec in sorted(source_specs, key=lambda entry: int(entry["source_col"])):
            source_col = int(spec["source_col"])
            preferred_cols = tuple(sorted({int(col) for col in list(spec["preferred_cols"])}))
            available_cols_value = spec.get("available_cols")
            available_cols = None
            if available_cols_value is not None:
                available_cols = {
                    int(col)
                    for col in list(available_cols_value)
                }
            candidates = self._map_target_candidates(
                source_col,
                desired_count=max(1, len(preferred_cols)),
                available_cols=available_cols,
            )
            preferred_set = set(preferred_cols)
            candidate_scores = {
                candidate: (
                    len(preferred_set.intersection(candidate)),
                    sum(
                        abs(candidate[index] - preferred_cols[index])
                        for index in range(min(len(candidate), len(preferred_cols)))
                    )
                    + abs(len(candidate) - len(preferred_cols)) * self.MAP_COLUMNS,
                    sum(1 << col for col in candidate),
                )
                for candidate in candidates
            }
            normalized_specs.append(
                {
                    "source_col": source_col,
                    "preferred_cols": preferred_cols,
                    "candidates": tuple(candidates),
                    "candidate_scores": candidate_scores,
                }
            )

        @lru_cache(maxsize=None)
        def search(
            index: int,
            prev_max: int,
            coverage_mask: int,
        ) -> tuple[tuple[int, int, int], tuple[tuple[int, ...], ...]]:
            if index >= len(normalized_specs):
                return ((coverage_mask.bit_count(), 0, 0), ())

            spec = normalized_specs[index]
            best_score: tuple[int, int, int] | None = None
            best_choices: tuple[tuple[int, ...], ...] = ()
            for candidate in spec["candidates"]:
                if prev_max >= 0 and candidate[0] < prev_max:
                    continue
                overlap, distance, candidate_mask = spec["candidate_scores"][candidate]
                future_score, future_choices = search(
                    index + 1,
                    candidate[-1],
                    coverage_mask | candidate_mask,
                )
                total_score = (
                    future_score[0],
                    future_score[1] + overlap,
                    future_score[2] - distance,
                )
                if best_score is None or total_score > best_score:
                    best_score = total_score
                    best_choices = (candidate,) + future_choices

            if best_score is None:
                return ((coverage_mask.bit_count(), -self.MAP_COLUMNS, -9999), ())
            return best_score, best_choices

        _, choices = search(0, -1, 0)
        if not choices:
            return {
                int(spec["source_col"]): list(spec["preferred_cols"])
                for spec in normalized_specs
            }
        return {
            int(normalized_specs[index]["source_col"]): list(choice)
            for index, choice in enumerate(choices)
        }

    def _ensure_map_row_target_spread(
        self,
        source_specs: list[dict[str, object]],
        normalized_targets: dict[int, list[int]],
    ) -> dict[int, list[int]]:
        unique_targets = {
            col
            for target_cols in normalized_targets.values()
            for col in target_cols
        }
        if len(unique_targets) >= 2:
            return normalized_targets

        ordered_specs = sorted(source_specs, key=lambda entry: int(entry["source_col"]))
        attempts: list[tuple[int, int]] = []
        for spec in ordered_specs:
            source_col = int(spec["source_col"])
            current_targets = normalized_targets.get(source_col, [])
            if not current_targets:
                continue
            lower_options = [
                col
                for col in self._map_adjacent_columns(source_col)
                if col not in current_targets and col < min(current_targets)
            ]
            attempts.extend((source_col, col) for col in reversed(lower_options))
        for spec in reversed(ordered_specs):
            source_col = int(spec["source_col"])
            current_targets = normalized_targets.get(source_col, [])
            if not current_targets:
                continue
            higher_options = [
                col
                for col in self._map_adjacent_columns(source_col)
                if col not in current_targets and col > max(current_targets)
            ]
            attempts.extend((source_col, col) for col in higher_options)
        for spec in ordered_specs:
            source_col = int(spec["source_col"])
            current_targets = normalized_targets.get(source_col, [])
            if not current_targets:
                continue
            fallback_options = [
                col
                for col in self._map_adjacent_columns(source_col)
                if col not in current_targets
            ]
            attempts.extend((source_col, col) for col in fallback_options)

        seen_attempts: set[tuple[int, int]] = set()
        for source_col, extra_col in attempts:
            if (source_col, extra_col) in seen_attempts:
                continue
            seen_attempts.add((source_col, extra_col))
            adjusted_specs: list[dict[str, object]] = []
            for spec in ordered_specs:
                spec_source_col = int(spec["source_col"])
                preferred_cols = list(normalized_targets.get(spec_source_col, []))
                if spec_source_col == source_col:
                    preferred_cols = sorted({*preferred_cols, extra_col})
                adjusted_specs.append(
                    {
                        "source_col": spec_source_col,
                        "preferred_cols": preferred_cols,
                        "available_cols": spec.get("available_cols"),
                    }
                )
            adjusted_targets = self._resolve_non_crossing_map_targets(adjusted_specs)
            adjusted_unique_targets = {
                col
                for target_cols in adjusted_targets.values()
                for col in target_cols
            }
            if len(adjusted_unique_targets) >= 2:
                return adjusted_targets
        return normalized_targets

    def _normalize_act_map_connections(self, act_map: dict[str, object]) -> None:
        if int(act_map.get("non_crossing_layout", 0)) == 1:
            return

        nodes = [
            node
            for node in list(act_map.get("nodes", []))
            if isinstance(node, dict) and "id" in node
        ]
        if not nodes:
            act_map["non_crossing_layout"] = 1
            return

        nodes_by_id = {str(node["id"]): node for node in nodes}
        nodes_by_row: dict[int, list[dict[str, object]]] = {}
        for node in nodes:
            row = int(node.get("row", 0))
            nodes_by_row.setdefault(row, []).append(node)

        for row, row_nodes in nodes_by_row.items():
            next_row_nodes = {
                int(node.get("col", 0)): str(node["id"])
                for node in nodes_by_row.get(row + 1, [])
            }
            if not next_row_nodes:
                continue
            source_specs: list[dict[str, object]] = []
            for node in sorted(row_nodes, key=lambda entry: int(entry.get("col", 0))):
                next_cols = [
                    int(next_node.get("col", 0))
                    for next_id in list(node.get("next_ids", []))
                    if (next_node := nodes_by_id.get(str(next_id))) is not None
                ]
                if not next_cols:
                    continue
                source_specs.append(
                    {
                        "source_col": int(node.get("col", 0)),
                        "preferred_cols": next_cols,
                        "available_cols": next_row_nodes.keys(),
                    }
                )
            normalized_targets = self._resolve_non_crossing_map_targets(source_specs)
            if not normalized_targets:
                continue
            for node in row_nodes:
                source_col = int(node.get("col", 0))
                target_cols = normalized_targets.get(source_col)
                if not target_cols:
                    continue
                node["next_ids"] = [
                    next_row_nodes[col]
                    for col in target_cols
                    if col in next_row_nodes
                ]

        visited = [str(value) for value in list(act_map.get("visited", []))]
        if visited:
            current_node = nodes_by_id.get(visited[-1])
            if current_node is not None:
                act_map["reachable"] = [
                    str(value)
                    for value in list(current_node.get("next_ids", []))
                ]
        else:
            first_row_nodes = sorted(
                nodes_by_row.get(1, []),
                key=lambda entry: int(entry.get("col", 0)),
            )
            act_map["reachable"] = [str(node["id"]) for node in first_row_nodes]
        act_map["non_crossing_layout"] = 1

    def _generate_act_map(self, run: RunState) -> None:
        rows = self.MAP_NODE_ROWS
        active_cols = sorted(self.rng.sample(range(1, self.MAP_COLUMNS - 1), 3))
        edges_by_id: dict[str, list[str]] = {}
        parents_by_id: dict[str, list[str]] = {}
        node_rows: dict[int, set[int]] = {1: set(active_cols)}

        for row in range(1, rows):
            next_cols: set[int] = set()
            source_specs: list[dict[str, object]] = []
            for col in sorted(node_rows.get(row, set())):
                options = self._map_adjacent_columns(col)
                count = 2 if self.rng.random() < 0.45 else 1
                chosen = sorted(self.rng.sample(list(options), count))
                source_specs.append(
                    {
                        "source_col": col,
                        "preferred_cols": chosen,
                    }
                )
            normalized_targets = self._resolve_non_crossing_map_targets(source_specs)
            normalized_targets = self._ensure_map_row_target_spread(
                source_specs,
                normalized_targets,
            )
            for col in sorted(node_rows.get(row, set())):
                node_id = f"a{run.act}r{row}c{col}"
                chosen = normalized_targets.get(col, [])
                next_ids = [f"a{run.act}r{row + 1}c{next_col}" for next_col in chosen]
                edges_by_id[node_id] = next_ids
                for next_id in next_ids:
                    parents_by_id.setdefault(next_id, []).append(node_id)
                next_cols.update(chosen)
            node_rows[row + 1] = next_cols

        nodes: list[dict[str, object]] = []
        node_type_by_id: dict[str, str] = {}
        for row in range(1, rows + 1):
            for col in sorted(node_rows.get(row, set())):
                node_id = f"a{run.act}r{row}c{col}"
                node_type = self._map_room_type_for_row(
                    run,
                    row,
                    parent_types=[
                        node_type_by_id[parent_id]
                        for parent_id in parents_by_id.get(node_id, [])
                        if parent_id in node_type_by_id
                    ],
                )
                node_type_by_id[node_id] = node_type
                nodes.append(
                    {
                        "id": node_id,
                        "row": row,
                        "col": col,
                        "node_type": node_type,
                        "next_ids": list(edges_by_id.get(node_id, [])),
                    }
                )

        if not self.has_key(run, "emerald"):
            elite_candidates = [node for node in nodes if str(node["node_type"]) == "elite"]
            if elite_candidates:
                self.rng.choice(elite_candidates)["node_type"] = "elite_key"

        run.meta["act_map"] = {
            "act": run.act,
            "nodes": nodes,
            "reachable": [
                str(node["id"])
                for node in nodes
                if int(node.get("row", 0)) == 1
            ],
            "visited": [],
        }
        self._normalize_act_map_connections(run.meta["act_map"])

    def _map_room_type_for_row(
        self,
        run: RunState,
        row: int,
        *,
        parent_types: list[str],
    ) -> str:
        if row == 1:
            return "combat"
        if row == 9:
            return "treasure"
        if row == self.MAP_NODE_ROWS:
            return "rest"
        weights = dict(self.MAP_ROOM_WEIGHTS)
        blocked = {
            parent_type
            for parent_type in parent_types
            if parent_type in {"elite", "elite_key", "rest", "shop", "treasure"}
        }
        if "elite_key" in blocked:
            blocked.add("elite")
        for blocked_type in blocked:
            weights.pop(blocked_type, None)
        if not weights:
            weights = {"combat": 70, "event": 30}
        return self._weighted_rarity_choice(weights)

    def choose_map_node(self, run: RunState, index: int) -> str:
        if run.phase != "map":
            raise ValueError("Run is not awaiting a map choice.")
        if index < 0 or index >= len(run.map_choices):
            raise ValueError("Invalid map choice.")

        entry = run.map_choices[index]
        node = self.map_node_type(run, entry)
        act_map = self._current_act_map(run)
        if act_map is not None:
            nodes = {
                str(node_data["id"]): node_data
                for node_data in list(act_map.get("nodes", []))
                if isinstance(node_data, dict) and "id" in node_data
            }
            chosen = nodes.get(entry)
            if chosen is not None:
                visited = [str(value) for value in list(act_map.get("visited", []))]
                visited.append(entry)
                act_map["visited"] = visited
                act_map["reachable"] = [str(value) for value in list(chosen.get("next_ids", []))]
        run.floor += 1
        run.act_floor += 1
        if "maw_bank" in run.relics and not run.meta.get("maw_bank_broken"):
            if self._gain_gold(run, 12) > 0:
                run.push_log("Maw Bank grants 12 Gold.")
        if node == "boss":
            if run.act == 4:
                self.start_specific_combat(run, ("corrupt_heart",), "boss")
            else:
                self.start_specific_combat(run, self._roll_boss_encounter(run), "boss")
            return "A boss encounter begins."
        if node == "combat":
            self.start_specific_combat(run, self._roll_common_encounter(run), "combat")
            return "A common encounter begins."
        if node == "elite":
            self.start_specific_combat(run, self._roll_elite_encounter(run), "elite")
            return "An elite encounter begins."
        if node == "elite_key":
            encounter = ("spire_shield", "spire_spear") if run.act == 4 else self._roll_elite_encounter(run)
            self.start_specific_combat(run, encounter, "elite")
            if run.combat is not None and run.act < 4:
                run.combat.player_meta["emerald_key_reward"] = 1
            return "A burning elite encounter begins."
        if node == "rest":
            if "ancient_tea_set" in run.relics:
                run.meta["ancient_tea_set_ready"] = 1
            run.phase = "rest"
            run.selection_context = None
            return "A rest site offers a moment to recover."
        if node == "shop":
            self._open_shop(run)
            return "A merchant opens their wares."
        if node == "event":
            if "ssserpent_head" in run.relics:
                if self._gain_gold(run, 50) > 0:
                    run.push_log("Ssserpent Head grants 50 Gold.")
            return self._open_event(run)
        if node == "treasure":
            if (
                run.act < 4
                and "nloths_hungry_face" in run.relics
                and not run.meta.get("nloths_hungry_face_used")
            ):
                run.meta["nloths_hungry_face_used"] = 1
                run.push_log("N'loth's Hungry Face leaves the chest empty.")
                self._advance_after_noncombat(run)
                return "The chest is empty."
            if run.act < 4 and "cursed_key" in run.relics:
                curse_key = self._random_neow_curse()
                curse_messages = self._add_card_to_deck(run, self.create_card_instance(run, curse_key))
                if curse_messages:
                    run.push_log(" ".join(curse_messages))
                run.push_log(f"Cursed Key adds {CARD_LIBRARY[curse_key].name}.")
            if run.act >= 4 or self.has_key(run, "sapphire"):
                relic_key, relic_messages = self._grant_random_relic(run)
                self._advance_after_noncombat(run)
                extra = f" {' '.join(relic_messages)}" if relic_messages else ""
                return f"You find a treasure chest and claim {RELIC_LIBRARY[relic_key].name}.{extra}"
            relic_key, _ = self._grant_random_relic_preview(run)
            run.reward = RewardState(source="treasure", gold=0, relic_choices=[relic_key])
            run.phase = "treasure"
            run.selection_context = None
            return "You open a treasure chest."
        raise ValueError(f"Unknown node type: {node}")

    def rest(self, run: RunState) -> str:
        if run.phase != "rest":
            raise ValueError("You are not at a rest site.")
        if "coffee_dripper" in run.relics:
            raise ValueError("Coffee Dripper prevents resting.")
        heal_amount = max(12, run.max_hp * 3 // 10)
        if "regal_pillow" in run.relics:
            heal_amount += 15
        if "eternal_feather" in run.relics:
            heal_amount += 3 * (len(run.deck) // 5)
        healed = self._heal_run(run, heal_amount)
        if "dream_catcher" in run.relics:
            run.reward = RewardState(
                source="dream_catcher",
                gold=0,
                card_choices=self._roll_reward_cards(run, source="combat"),
            )
            run.phase = "reward"
            run.selection_context = None
            return f"You rest and recover {healed} HP. Dream Catcher offers a card reward."
        self._advance_after_noncombat(run)
        return f"You rest and recover {healed} HP."

    def dig(self, run: RunState) -> str:
        if run.phase != "rest":
            raise ValueError("You are not at a rest site.")
        if "shovel" not in run.relics:
            raise ValueError("You need Shovel to Dig.")
        relic_key, details = self._grant_random_relic(run)
        self._advance_after_noncombat(run)
        suffix = f" {' '.join(details)}" if details else ""
        return f"You Dig and uncover {RELIC_LIBRARY[relic_key].name}.{suffix}"

    def lift(self, run: RunState) -> str:
        if run.phase != "rest":
            raise ValueError("You are not at a rest site.")
        if "girya" not in run.relics:
            raise ValueError("You need Girya to Lift.")
        lifts = int(run.meta.get("girya_lifts", 0))
        if lifts >= 3:
            raise ValueError("Girya has already been used 3 times.")
        run.meta["girya_lifts"] = lifts + 1
        self._advance_after_noncombat(run)
        return "You Lift and permanently gain 1 Strength."

    def begin_toke(self, run: RunState) -> None:
        if run.phase != "rest":
            raise ValueError("You are not at a rest site.")
        if "peace_pipe" not in run.relics:
            raise ValueError("You need Peace Pipe to Toke.")
        run.phase = "remove"
        run.selection_context = "peace_pipe"

    def recall(self, run: RunState) -> str:
        if run.phase != "rest":
            raise ValueError("You are not at a rest site.")
        if run.act >= 4:
            raise ValueError("Recall is not available here.")
        if self.has_key(run, "ruby"):
            raise ValueError("You already have the Ruby Key.")
        run.keys.append("ruby")
        self._advance_after_noncombat(run)
        run.push_log("Ruby Key claimed at a rest site.")
        return "You Recall the Ruby Key."

    def begin_upgrade(self, run: RunState, context: str = "rest") -> None:
        if context == "rest" and "fusion_hammer" in run.relics:
            raise ValueError("Fusion Hammer prevents smithing at rest sites.")
        run.phase = "upgrade"
        run.selection_context = context

    def upgrade_card(self, run: RunState, instance_id: str) -> str:
        card = self._find_card(run.deck, instance_id)
        if card is None:
            raise ValueError("Card not found.")
        if card.upgraded:
            raise ValueError("Card is already upgraded.")
        card.upgraded = True
        label = self.card_name(card)
        context = run.selection_context or "rest"
        if context == "rest":
            self._advance_after_noncombat(run)
        elif context == "event":
            self._advance_after_noncombat(run)
        elif context == "designer_adjustments":
            self._advance_after_noncombat(run)
        elif context == "neow":
            self._prepare_map_choices(run)
            run.phase = "map"
        elif self._complete_pending_transition(run):
            pass
        run.selection_context = None
        run.event = None
        return f"{label} has been upgraded."

    def remove_card(self, run: RunState, instance_id: str) -> str:
        target = self._find_card(run.deck, instance_id)
        if target is None:
            raise ValueError("Card not found.")
        context = run.selection_context or ""
        if context.startswith("bottle:"):
            relic_key = context.split(":", 1)[1]
            required_type = {
                "bottled_flame": "attack",
                "bottled_lightning": "skill",
                "bottled_tornado": "power",
            }.get(relic_key)
            if required_type is None:
                raise ValueError("Unknown bottle relic.")
            if CARD_LIBRARY[target.key].card_type != required_type:
                raise ValueError(f"Choose a {required_type.title()} card.")
            run.meta[f"{relic_key}_card"] = target.instance_id
            run.selection_context = None
            run.event = None
            self._resume_after_delayed_choice(run)
            return f"{self.card_name(target)} is now bottled."
        if context in {"dollys_mirror", "duplicator"}:
            copy_card = self.create_card_instance(
                run,
                target.key,
                upgraded=target.upgraded,
                misc=target.misc,
                cost_adjustment=target.cost_adjustment,
            )
            extras = self._add_card_to_deck(run, copy_card)
            run.selection_context = None
            run.event = None
            if context == "duplicator":
                self._advance_after_noncombat(run)
            else:
                self._resume_after_delayed_choice(run)
            suffix = f" {' '.join(extras)}" if extras else ""
            source = "Duplicator" if context == "duplicator" else "Dolly's Mirror"
            return f"{source} copies {self.card_name(target)}.{suffix}"
        if run.selection_context == "transform" or (run.selection_context or "").startswith("transform:"):
            return self._transform_card(run, target)
        if (run.selection_context or "").startswith("astrolabe:"):
            return self._astrolabe_transform_card(run, target)
        if run.selection_context == "bonfire":
            return self._offer_bonfire_card(run, target)
        run.deck = [card for card in run.deck if card.instance_id != instance_id]
        self._clear_bound_relic_card(run, instance_id)
        label = self.card_name(target)
        if run.selection_context == "shop":
            if run.shop is None:
                raise ValueError("Shop is unavailable.")
            run.shop.remove_used = True
            if run.shop.remove_cost > 0:
                run.meta["maw_bank_broken"] = 1
            run.gold -= run.shop.remove_cost
            run.meta["shop_remove_uses"] = int(run.meta.get("shop_remove_uses", 0)) + 1
            run.shop.remove_cost = self._current_shop_remove_cost(run)
            run.phase = "shop"
        elif (run.selection_context or "").startswith("neow_remove:"):
            remaining = max(0, int((run.selection_context or "neow_remove:1").split(":", 1)[1]) - 1)
            if remaining > 0:
                run.selection_context = f"neow_remove:{remaining}"
                run.phase = "remove"
                run.meta["neow_pending_removals"] = remaining
                return f"{label} has been removed from your deck. Choose another card to remove."
            run.meta.pop("neow_pending_removals", None)
            self._prepare_map_choices(run)
            run.phase = "map"
        elif (run.selection_context or "").startswith("empty_cage:"):
            remaining = max(0, int((run.selection_context or "empty_cage:1").split(":", 1)[1]) - 1)
            if remaining > 0:
                run.selection_context = f"empty_cage:{remaining}"
                run.phase = "remove"
                return f"{label} has been removed from your deck. Choose another card to remove."
            if not self._complete_pending_transition(run):
                self._advance_after_noncombat(run)
        elif run.selection_context == "designer_cleanup":
            self._advance_after_noncombat(run)
        elif run.selection_context == "designer_full_service":
            upgrades = self._upgrade_random_unupgraded_cards(run, 1)
            self._advance_after_noncombat(run)
            suffix = f" {' '.join(upgrades)}" if upgrades else ""
            run.selection_context = None
            run.event = None
            return f"{label} has been removed from your deck.{suffix}"
        elif (run.selection_context or "").startswith("forbidden_grimoire:"):
            remaining = max(0, int((run.selection_context or "forbidden_grimoire:1").split(":", 1)[1]) - 1)
            if remaining > 0 and run.deck:
                run.selection_context = f"forbidden_grimoire:{remaining}"
                run.phase = "remove"
                return f"{label} has been removed from your deck. Choose another card to remove."
            resume_phase = str(run.meta.pop("forbidden_grimoire_resume_phase", "map"))
            if resume_phase == "map":
                self._advance_after_noncombat(run)
            else:
                run.phase = resume_phase
        elif run.selection_context == "peace_pipe":
            self._advance_after_noncombat(run)
        else:
            if not self._complete_pending_transition(run):
                self._advance_after_noncombat(run)
        run.selection_context = None
        run.event = None
        return f"{label} has been removed from your deck."

    def choose_event_option(self, run: RunState, option_id: str) -> str:
        if run.phase != "event" or run.event is None:
            raise ValueError("No event is active.")
        if run.event.key == "living_wall":
            return self._resolve_living_wall_option(run, option_id)
        if run.event.key == "transmogrifier":
            return self._resolve_transmogrifier_option(run, option_id)
        if run.event.key == "the_library":
            return self._resolve_library_option(run, option_id)
        if run.event.key == "the_mausoleum":
            return self._resolve_mausoleum_option(run, option_id)
        if run.event.key == "bonfire_spirits":
            return self._resolve_bonfire_spirits_option(run, option_id)
        if run.event.key == "council_of_ghosts":
            return self._resolve_council_of_ghosts_option(run, option_id)
        if run.event.key == "winding_halls":
            return self._resolve_winding_halls_option(run, option_id)
        if run.event.key == "falling":
            return self._resolve_falling_option(run, option_id)
        if run.event.key == "colosseum":
            return self._resolve_colosseum_option(run, option_id)
        if run.event.key == "designer_inspire":
            return self._resolve_designer_inspire_option(run, option_id)
        if run.event.key == "face_trader":
            return self._resolve_face_trader_option(run, option_id)
        if run.event.key == "nloth":
            return self._resolve_nloth_option(run, option_id)
        if run.event.key == "moai_head":
            return self._resolve_moai_head_option(run, option_id)
        if run.event.key == "divine_fountain":
            return self._resolve_divine_fountain_option(run, option_id)
        if run.event.key == "masked_bandits":
            return self._resolve_masked_bandits_option(run, option_id)
        if run.event.key == "tomb_of_lord_red_mask":
            return self._resolve_tomb_of_lord_red_mask_option(run, option_id)
        if run.event.key == "hypnotizing_colored_mushrooms":
            return self._resolve_colored_mushrooms_option(run, option_id)
        if run.event.key == "dead_adventurer":
            return self._resolve_dead_adventurer_option(run, option_id)
        if run.event.key == "mind_bloom":
            return self._resolve_mind_bloom_option(run, option_id)
        if run.event.key == "secret_portal":
            return self._resolve_secret_portal_option(run, option_id)
        if run.event.key == "mysterious_sphere":
            return self._resolve_mysterious_sphere_option(run, option_id)
        if run.event.key == "scrap_ooze":
            return self._resolve_scrap_ooze_option(run, option_id)
        if run.event.key == "the_joust":
            return self._resolve_the_joust_option(run, option_id)
        if run.event.key == "knowing_skull":
            return self._resolve_knowing_skull_option(run, option_id)
        if run.event.key == "sensory_stone":
            return self._resolve_sensory_stone_option(run, option_id)
        if run.event.key == "we_meet_again":
            return self._resolve_we_meet_again_option(run, option_id)
        return self._resolve_standard_event_option(run, option_id)

    def _resolve_dead_adventurer_option(self, run: RunState, option_id: str) -> str:
        if run.event is None or run.event.key != "dead_adventurer":
            raise ValueError("Dead Adventurer is not active.")
        if option_id == "leave":
            run.meta.pop("dead_adventurer", None)
            run.push_log("Event resolved: Dead Adventurer - Leave.")
            run.event = None
            self._advance_after_noncombat(run)
            return "You leave the corpse undisturbed."
        if option_id != "search":
            raise ValueError("Invalid event option.")
        state = dict(run.meta.get("dead_adventurer", {}))
        searches = int(state.get("searches", 0)) + 1
        state["searches"] = searches
        encounter_chance = min(1.0, 0.25 * searches)
        if self.rng.random() < encounter_chance:
            run.meta.pop("dead_adventurer", None)
            encounter = self.rng.choice(
                [
                    ("lagavulin",),
                    ("gremlin_nob",),
                    ("sentry", "sentry", "sentry"),
                ]
            )
            self.start_specific_combat(run, encounter, "elite")
            if run.combat is not None:
                run.combat.player_meta["dead_adventurer"] = state
            return "You disturb what killed the adventurer. An elite attacks."

        remaining_rewards = [
            reward
            for reward in ("gold", "relic", "nothing")
            if not state.get(f"found_{reward}", False)
        ]
        reward_key = self.rng.choice(remaining_rewards or ["nothing"])
        state[f"found_{reward_key}"] = True
        run.meta["dead_adventurer"] = state
        if reward_key == "gold":
            gained = self._gain_gold(run, 30)
            message = f"You find {gained} gold on the corpse." if gained > 0 else "Ectoplasm prevents the gold."
        elif reward_key == "relic":
            relic_key, relic_messages = self._grant_random_relic(run)
            suffix = f" {' '.join(relic_messages)}" if relic_messages else ""
            message = f"You uncover {RELIC_LIBRARY[relic_key].name}.{suffix}"
        else:
            message = "You find nothing of value."
        run.event = EventState(
            key="dead_adventurer",
            name="Dead Adventurer",
            description="You can keep searching, but the danger nearby is growing.",
            options=[
                EventOptionState(
                    option_id="search",
                    label="Search",
                    description="Press deeper into the corpse's belongings.",
                ),
                EventOptionState(
                    option_id="leave",
                    label="Leave",
                    description="Leave before anything worse shows up.",
                ),
            ],
        )
        return message

    def _resolve_masked_bandits_option(self, run: RunState, option_id: str) -> str:
        if run.event is None or run.event.key != "masked_bandits":
            raise ValueError("Masked Bandits is not active.")
        if option_id == "pay":
            lost = run.gold
            run.gold = 0
            run.push_log("Event resolved: Masked Bandits - Pay.")
            run.event = None
            self._advance_after_noncombat(run)
            return f"You hand over {lost} Gold and move on."
        if option_id != "fight":
            raise ValueError("Invalid event option.")
        run.event = None
        self.start_specific_combat(run, ("pointy", "romeo", "bear"), "combat")
        if run.combat is not None:
            run.combat.reward_gold += self.rng.randint(25, 35)
            run.combat.player_meta["masked_bandits_red_mask"] = 1
        return "You refuse to pay. The bandits attack."

    def _resolve_tomb_of_lord_red_mask_option(self, run: RunState, option_id: str) -> str:
        if run.event is None or run.event.key != "tomb_of_lord_red_mask":
            raise ValueError("Tomb of Lord Red Mask is not active.")
        if option_id == "leave":
            run.push_log("Event resolved: Tomb of Lord Red Mask - Leave.")
            run.event = None
            self._advance_after_noncombat(run)
            return "You leave the tomb undisturbed."
        if option_id == "don":
            if "red_mask" not in run.relics:
                raise ValueError("You do not have Red Mask.")
            self._gain_gold(run, 222)
            run.push_log("Event resolved: Tomb of Lord Red Mask - Don the Red Mask.")
            run.event = None
            self._advance_after_noncombat(run)
            return "The tomb accepts the mask and rewards you with 222 Gold."
        if option_id != "offer":
            raise ValueError("Invalid event option.")
        lost = run.gold
        run.gold = 0
        _, messages = self._grant_specific_relic(run, "red_mask")
        run.push_log("Event resolved: Tomb of Lord Red Mask - Offer.")
        run.event = None
        self._advance_after_noncombat(run)
        suffix = f" {' '.join(messages)}" if messages else ""
        return f"You offer {lost} Gold and obtain Red Mask.{suffix}"

    def _resolve_colored_mushrooms_option(self, run: RunState, option_id: str) -> str:
        if run.event is None or run.event.key != "hypnotizing_colored_mushrooms":
            raise ValueError("Hypnotizing Colored Mushrooms is not active.")
        if option_id == "stomp":
            run.event = None
            self.start_specific_combat(run, ("fungi_beast",), "combat")
            if run.combat is not None:
                run.combat.player_meta["colored_mushrooms_reward"] = "odd_mushroom"
            return "The mushrooms release spores and a Fungi Beast attacks."
        if option_id != "eat":
            raise ValueError("Invalid event option.")
        return self._resolve_standard_event_option(run, option_id)

    def _resolve_living_wall_option(self, run: RunState, option_id: str) -> str:
        if run.event is None or run.event.key != "living_wall":
            raise ValueError("Living Wall is not active.")
        if option_id == "forget":
            run.event = None
            run.phase = "remove"
            run.selection_context = "event"
            return "Choose a card to remove."
        if option_id == "change":
            run.event = None
            run.phase = "remove"
            run.selection_context = "transform"
            return "Choose a card to transform."
        if option_id == "grow":
            run.event = None
            self.begin_upgrade(run, "event")
            return "Choose a card to upgrade."
        raise ValueError("Invalid event option.")

    def _resolve_transmogrifier_option(self, run: RunState, option_id: str) -> str:
        if run.event is None or run.event.key != "transmogrifier":
            raise ValueError("Transmogrifier is not active.")
        if option_id == "leave":
            run.push_log("Event resolved: Transmogrifier - Leave.")
            run.event = None
            self._advance_after_noncombat(run)
            return "You leave the machine alone."
        if option_id != "pray":
            raise ValueError("Invalid event option.")
        run.event = None
        run.phase = "remove"
        run.selection_context = "transform"
        return "Choose a card to transform."

    def _resolve_library_option(self, run: RunState, option_id: str) -> str:
        if run.event is None or run.event.key != "the_library":
            raise ValueError("The Library is not active.")
        if option_id == "sleep":
            return self._resolve_standard_event_option(run, option_id)
        if option_id != "read":
            raise ValueError("Invalid event option.")
        run.event = None
        run.reward = RewardState(
            source="event_forced",
            gold=0,
            card_choices=self._roll_offer_cards(run, 20, source="event"),
        )
        run.phase = "reward"
        run.push_log("Event resolved: The Library - Read.")
        return "Choose 1 of 20 cards to add to your deck."

    def _resolve_mausoleum_option(self, run: RunState, option_id: str) -> str:
        if run.event is None or run.event.key != "the_mausoleum":
            raise ValueError("The Mausoleum is not active.")
        if option_id == "leave":
            run.push_log("Event resolved: The Mausoleum - Leave.")
            run.event = None
            self._advance_after_noncombat(run)
            return "You leave the coffin sealed."
        if option_id != "open":
            raise ValueError("Invalid event option.")
        relic_key = self._roll_relic_from_rarity(run, "common", "uncommon", "rare")
        if relic_key is None:
            relic_key, relic_messages = self._grant_random_relic(run)
        else:
            relic_messages = self._obtain_relic(run, relic_key)
        messages = [f"You obtain {RELIC_LIBRARY[relic_key].name}."]
        messages.extend(relic_messages)
        if self.rng.random() < 0.5:
            if relic_key == "omamori":
                run.meta["ignore_omamori_once"] = 1
            curse_messages = self._add_card_to_deck(run, self.create_card_instance(run, "writhe"))
            messages.append("A dark presence leaves Writhe in your deck.")
            messages.extend(curse_messages)
        run.push_log("Event resolved: The Mausoleum - Open Coffin.")
        run.event = None
        self._advance_after_noncombat(run)
        return " ".join(messages)

    def _resolve_bonfire_spirits_option(self, run: RunState, option_id: str) -> str:
        if run.event is None or run.event.key != "bonfire_spirits":
            raise ValueError("Bonfire Spirits is not active.")
        if option_id == "leave":
            run.push_log("Event resolved: Bonfire Spirits - Leave.")
            run.event = None
            self._advance_after_noncombat(run)
            return "You leave the bonfire undisturbed."
        if option_id != "offer":
            raise ValueError("Invalid event option.")
        run.event = None
        run.phase = "remove"
        run.selection_context = "bonfire"
        return "Choose a card to offer to the bonfire."

    def _resolve_council_of_ghosts_option(self, run: RunState, option_id: str) -> str:
        if run.event is None or run.event.key != "council_of_ghosts":
            raise ValueError("Council of Ghosts is not active.")
        if option_id == "leave":
            run.push_log("Event resolved: Council of Ghosts - Leave.")
            run.event = None
            self._advance_after_noncombat(run)
            return "You refuse the ghosts' bargain."
        if option_id != "accept":
            raise ValueError("Invalid event option.")
        loss = max(1, run.max_hp // 2)
        run.max_hp = max(1, run.max_hp - loss)
        run.hp = min(run.hp, run.max_hp)
        for _ in range(5):
            self._add_card_to_deck(run, self.create_card_instance(run, "apparition"))
        run.push_log("Event resolved: Council of Ghosts - Accept.")
        run.event = None
        self._advance_after_noncombat(run)
        return "You lose half your Max HP and receive 5 Apparitions."

    def _resolve_winding_halls_option(self, run: RunState, option_id: str) -> str:
        if run.event is None or run.event.key != "winding_halls":
            raise ValueError("Winding Halls is not active.")
        if option_id == "embrace":
            run.max_hp = max(1, run.max_hp - 5)
            run.hp = min(run.hp, run.max_hp)
            self._add_card_to_deck(run, self.create_card_instance(run, "madness"))
            self._add_card_to_deck(run, self.create_card_instance(run, "madness"))
            run.push_log("Event resolved: Winding Halls - Embrace Madness.")
            run.event = None
            self._advance_after_noncombat(run)
            return "You lose 5 Max HP and obtain 2 Madness."
        if option_id == "panic":
            healed = self._heal_run(run, max(1, run.max_hp // 4))
            self._add_card_to_deck(run, self.create_card_instance(run, "writhe"))
            run.push_log("Event resolved: Winding Halls - Panic.")
            run.event = None
            self._advance_after_noncombat(run)
            return f"You heal {healed} HP and obtain Writhe."
        return self._resolve_standard_event_option(run, option_id)

    def _resolve_falling_option(self, run: RunState, option_id: str) -> str:
        if run.event is None or run.event.key != "falling":
            raise ValueError("Falling is not active.")
        target = self._find_card(run.deck, option_id)
        if target is None:
            raise ValueError("Invalid event option.")
        label = self.card_name(target)
        run.deck = [card for card in run.deck if card.instance_id != option_id]
        run.push_log(f"Event resolved: Falling - Lose {label}.")
        run.event = None
        self._advance_after_noncombat(run)
        return f"You lose {label} to the fall."

    def _resolve_colosseum_option(self, run: RunState, option_id: str) -> str:
        if run.event is None or run.event.key != "colosseum":
            raise ValueError("Colosseum is not active.")
        stage = int(run.meta.get("colosseum_stage", 0))
        if stage <= 1:
            if option_id == "leave":
                run.meta.pop("colosseum_stage", None)
                run.push_log("Event resolved: Colosseum - Leave.")
                run.event = None
                self._advance_after_noncombat(run)
                return "You leave the arena behind."
            if option_id != "fight":
                raise ValueError("Invalid event option.")
            run.event = None
            run.meta["colosseum_stage"] = 1
            self.start_specific_combat(run, ("blue_slaver", "red_slaver"), "combat")
            if run.combat is not None:
                run.combat.player_meta["colosseum_stage"] = 1
            return "The arena gates slam shut. The slavers attack."
        if option_id == "cowardice":
            run.meta.pop("colosseum_stage", None)
            run.push_log("Event resolved: Colosseum - Cowardice.")
            run.event = None
            self._advance_after_noncombat(run)
            return "You take your winnings and leave."
        if option_id != "victory":
            raise ValueError("Invalid event option.")
        run.event = None
        run.meta["colosseum_stage"] = 2
        self.start_specific_combat(run, ("taskmaster", "gremlin_nob"), "elite")
        if run.combat is not None:
            run.combat.player_meta["colosseum_stage"] = 2
        return "The crowd roars louder. A second, deadlier fight begins."

    def _resolve_designer_inspire_option(self, run: RunState, option_id: str) -> str:
        if run.event is None or run.event.key != "designer_inspire":
            raise ValueError("Designer In-Spire is not active.")
        if option_id == "punch":
            return self._resolve_standard_event_option(run, option_id)
        if option_id == "adjustments":
            if run.gold < 40:
                raise ValueError("Not enough gold.")
            run.gold -= 40
            run.event = None
            if self.rng.random() < 0.5:
                run.phase = "upgrade"
                run.selection_context = "designer_adjustments"
                return "You pay 40 Gold. Choose a card to upgrade."
            upgrades = self._upgrade_random_unupgraded_cards(run, 2)
            self._advance_after_noncombat(run)
            suffix = f" {' '.join(upgrades)}" if upgrades else ""
            return f"You pay 40 Gold and the designer gets to work.{suffix}"
        if option_id == "clean_up":
            if run.gold < 60:
                raise ValueError("Not enough gold.")
            run.gold -= 60
            run.event = None
            if self.rng.random() < 0.5:
                run.phase = "remove"
                run.selection_context = "designer_cleanup"
                return "You pay 60 Gold. Choose a card to remove."
            run.phase = "remove"
            run.selection_context = "transform:2"
            return "You pay 60 Gold. Choose a card to transform."
        if option_id != "full_service":
            raise ValueError("Invalid event option.")
        if run.gold < 90:
            raise ValueError("Not enough gold.")
        run.gold -= 90
        run.event = None
        run.phase = "remove"
        run.selection_context = "designer_full_service"
        return "You pay 90 Gold. Choose a card to remove."

    def _resolve_face_trader_option(self, run: RunState, option_id: str) -> str:
        if run.event is None or run.event.key != "face_trader":
            raise ValueError("Face Trader is not active.")
        if option_id == "leave":
            run.push_log("Event resolved: Face Trader - Leave.")
            run.event = None
            self._advance_after_noncombat(run)
            return "You keep your face and leave."
        if option_id == "touch":
            loss = max(1, run.max_hp // 10)
            run.hp = max(0, run.hp - loss)
            self._gain_gold(run, 75)
            run.push_log("Event resolved: Face Trader - Touch.")
            run.event = None
            self._advance_after_noncombat(run)
            if run.hp <= 0:
                run.phase = "defeat"
                return "The touch proves fatal."
            return f"You lose {loss} HP and gain 75 Gold."
        if option_id != "trade":
            raise ValueError("Invalid event option.")
        face_pool = [
            "cultist_headpiece",
            "face_of_cleric",
            "gremlin_visage",
            "nloths_hungry_face",
            "ssserpent_head",
        ]
        available = [key for key in face_pool if key not in run.relics] or face_pool
        relic_key = self.rng.choice(available)
        _, messages = self._grant_specific_relic(run, relic_key)
        run.push_log(f"Event resolved: Face Trader - Trade for {RELIC_LIBRARY[relic_key].name}.")
        run.event = None
        self._advance_after_noncombat(run)
        suffix = f" {' '.join(messages)}" if messages else ""
        return f"You obtain {RELIC_LIBRARY[relic_key].name}.{suffix}"

    def _resolve_nloth_option(self, run: RunState, option_id: str) -> str:
        if run.event is None or run.event.key != "nloth":
            raise ValueError("N'loth is not active.")
        if option_id == "leave":
            run.push_log("Event resolved: N'loth - Leave.")
            run.event = None
            self._advance_after_noncombat(run)
            return "You refuse N'loth's bargain."
        if not option_id.startswith("trade:"):
            raise ValueError("Invalid event option.")
        relic_key = option_id.split(":", 1)[1]
        if relic_key not in run.relics:
            raise ValueError("That relic can no longer be traded.")
        relic_name = RELIC_LIBRARY[relic_key].name
        self._remove_relic(run, relic_key)
        _, messages = self._grant_specific_relic(run, "nloths_gift")
        run.push_log(f"Event resolved: N'loth - Trade {relic_name}.")
        run.event = None
        self._advance_after_noncombat(run)
        suffix = f" {' '.join(messages)}" if messages else ""
        return f"You trade away {relic_name} and obtain N'loth's Gift.{suffix}"

    def _resolve_moai_head_option(self, run: RunState, option_id: str) -> str:
        if run.event is None or run.event.key != "moai_head":
            raise ValueError("The Moai Head is not active.")
        if option_id == "leave":
            run.push_log("Event resolved: The Moai Head - Leave.")
            run.event = None
            self._advance_after_noncombat(run)
            return "You leave the stone head behind."
        if option_id == "offer":
            if "golden_idol" not in run.relics:
                raise ValueError("You do not have Golden Idol.")
            self._remove_relic(run, "golden_idol")
            self._gain_gold(run, 333)
            run.push_log("Event resolved: The Moai Head - Offer Idol.")
            run.event = None
            self._advance_after_noncombat(run)
            return "You offer Golden Idol and gain 333 Gold."
        if option_id != "jump_inside":
            raise ValueError("Invalid event option.")
        loss = max(1, run.max_hp // 8)
        run.max_hp = max(1, run.max_hp - loss)
        if self._can_heal_run(run):
            run.hp = run.max_hp
            message = f"You recover to full HP and lose {loss} Max HP."
        else:
            run.hp = min(run.hp, run.max_hp)
            message = f"You lose {loss} Max HP."
        run.push_log("Event resolved: The Moai Head - Jump Inside.")
        run.event = None
        self._advance_after_noncombat(run)
        return message

    def _resolve_divine_fountain_option(self, run: RunState, option_id: str) -> str:
        if run.event is None or run.event.key != "divine_fountain":
            raise ValueError("Divine Fountain is not active.")
        if option_id == "leave":
            run.push_log("Event resolved: Divine Fountain - Leave.")
            run.event = None
            self._advance_after_noncombat(run)
            return "You leave the fountain untouched."
        if option_id != "drink":
            raise ValueError("Invalid event option.")
        removed = [
            card for card in run.deck if CARD_LIBRARY[card.key].rarity == "curse"
        ]
        run.deck = [card for card in run.deck if CARD_LIBRARY[card.key].rarity != "curse"]
        run.push_log("Event resolved: Divine Fountain - Drink.")
        run.event = None
        self._advance_after_noncombat(run)
        if not removed:
            return "The fountain leaves you unchanged."
        return f"The fountain washes away {len(removed)} Curse card(s)."

    def _resolve_mind_bloom_option(self, run: RunState, option_id: str) -> str:
        if run.event is None or run.event.key != "mind_bloom":
            raise ValueError("Mind Bloom is not active.")
        if option_id == "war":
            run.event = None
            encounter = self.rng.choice([("hexaghost",), ("slime_boss",), ("guardian",)])
            self.start_specific_combat(run, encounter, "boss")
            if run.combat is not None:
                run.combat.encounter_kind = "combat"
                run.combat.player_meta["mind_bloom_war"] = 1
            return "Reality twists. An Act 1 boss appears."
        if option_id == "awake":
            run.event = None
            upgraded = 0
            for card in run.deck:
                if not card.upgraded:
                    card.upgraded = True
                    upgraded += 1
            _, relic_messages = self._grant_specific_relic(run, "mark_of_the_bloom")
            self._advance_after_noncombat(run)
            suffix = f" {' '.join(relic_messages)}" if relic_messages else ""
            return f"{upgraded} card(s) are upgraded. You obtain Mark Of The Bloom.{suffix}"
        if option_id == "rich":
            run.event = None
            gained = self._gain_gold(run, 999)
            messages = [
                f"You gain {gained} Gold." if gained > 0 else "Ectoplasm prevents the Gold.",
                *self._add_card_to_deck(run, self.create_card_instance(run, "normality")),
                *self._add_card_to_deck(run, self.create_card_instance(run, "normality")),
            ]
            self._advance_after_noncombat(run)
            return " ".join(messages)
        if option_id == "healthy":
            run.event = None
            healed = self._heal_run(run, run.max_hp)
            messages = [f"You heal {healed} HP."]
            messages.extend(self._add_card_to_deck(run, self.create_card_instance(run, "doubt")))
            self._advance_after_noncombat(run)
            return " ".join(messages)
        raise ValueError("Invalid event option.")

    def _resolve_secret_portal_option(self, run: RunState, option_id: str) -> str:
        if run.event is None or run.event.key != "secret_portal":
            raise ValueError("Secret Portal is not active.")
        if option_id == "leave":
            run.push_log("Event resolved: Secret Portal - Leave.")
            run.event = None
            self._advance_after_noncombat(run)
            return "You let the portal close."
        if option_id != "enter":
            raise ValueError("Invalid event option.")
        run.event = None
        run.act_floor = self.MAP_NODE_ROWS
        run.floor = max(run.floor, (run.act - 1) * self.FLOORS_PER_ACT + run.act_floor)
        self._prepare_map_choices(run)
        run.phase = "map"
        run.selection_context = None
        run.push_log("Event resolved: Secret Portal - Enter.")
        return "The portal hurls you to the edge of the boss chamber."

    def _resolve_mysterious_sphere_option(self, run: RunState, option_id: str) -> str:
        if run.event is None or run.event.key != "mysterious_sphere":
            raise ValueError("Mysterious Sphere is not active.")
        if option_id == "leave":
            run.push_log("Event resolved: Mysterious Sphere - Leave.")
            run.event = None
            self._advance_after_noncombat(run)
            return "You back away from the sphere."
        if option_id != "open":
            raise ValueError("Invalid event option.")
        run.event = None
        self.start_specific_combat(run, ("orb_walker", "orb_walker"), "combat")
        if run.combat is not None:
            run.combat.player_meta["mysterious_sphere_rare_relic"] = 1
        return "The sphere cracks open and two Orb Walkers attack."

    def _resolve_scrap_ooze_option(self, run: RunState, option_id: str) -> str:
        if run.event is None or run.event.key != "scrap_ooze":
            raise ValueError("Scrap Ooze is not active.")
        if option_id == "leave":
            run.meta.pop("scrap_ooze", None)
            run.push_log("Event resolved: Scrap Ooze - Leave.")
            run.event = None
            self._advance_after_noncombat(run)
            return "You leave the ooze alone."
        if option_id != "reach":
            raise ValueError("Invalid event option.")
        state = dict(run.meta.get("scrap_ooze", {}))
        hp_loss = int(state.get("hp_loss", 3))
        chance = int(state.get("chance", 25))
        run.hp = max(0, run.hp - hp_loss)
        if run.hp <= 0:
            run.meta.pop("scrap_ooze", None)
            run.event = None
            run.phase = "defeat"
            return "The Scrap Ooze kills you."
        if self.rng.randrange(100) < chance:
            run.meta.pop("scrap_ooze", None)
            rarity = self._weighted_rarity_choice({"common": 17, "uncommon": 33, "rare": 50})
            relic_key = self._roll_relic_from_rarity(run, rarity)
            self._remember_delayed_choice_return(run)
            if relic_key is None:
                relic_key, relic_messages = self._grant_random_relic(run)
            else:
                relic_messages = self._obtain_relic(run, relic_key)
            run.push_log("Event resolved: Scrap Ooze - Reach.")
            run.event = None
            if run.phase not in {"remove", "reward", "shop", "combat"}:
                self._advance_after_noncombat(run)
            suffix = f" {' '.join(relic_messages)}" if relic_messages else ""
            return f"You lose {hp_loss} HP and drag out {RELIC_LIBRARY[relic_key].name}.{suffix}"
        state["hp_loss"] = hp_loss + 1
        state["chance"] = min(100, chance + 10)
        run.meta["scrap_ooze"] = state
        run.event = EventState(
            key="scrap_ooze",
            name="Scrap Ooze",
            description="The relic is still buried in the sludge.",
            options=[
                EventOptionState(
                    option_id="reach",
                    label="Reach",
                    description=f"Lose {state['hp_loss']} HP. {state['chance']}% chance for a relic.",
                ),
                EventOptionState(
                    option_id="leave",
                    label="Leave",
                    description="Back away from the ooze.",
                ),
            ],
        )
        return f"You lose {hp_loss} HP, but the relic slips deeper into the ooze."

    def _resolve_the_joust_option(self, run: RunState, option_id: str) -> str:
        if run.event is None or run.event.key != "the_joust":
            raise ValueError("The Joust is not active.")
        if option_id not in {"murderer", "owner"}:
            raise ValueError("Invalid event option.")
        if run.gold < 50:
            raise ValueError("You do not have enough Gold.")
        run.gold -= 50
        owner_wins = self.rng.random() < 0.3
        won = (option_id == "owner" and owner_wins) or (option_id == "murderer" and not owner_wins)
        payout = 250 if option_id == "owner" else 100
        gained = self._gain_gold(run, payout) if won else 0
        run.push_log(f"Event resolved: The Joust - {option_id.title()}.")
        run.event = None
        self._advance_after_noncombat(run)
        if won:
            if gained > 0:
                return f"Your wager pays off. You gain {gained} Gold."
            return "Your wager pays off, but Ectoplasm prevents the Gold."
        return "Your wager fails and the knights take your stake."

    def _knowing_skull_base_cost(self, run: RunState) -> int:
        return max(6, run.max_hp // 10)

    def _knowing_skull_cost(self, run: RunState, option_id: str) -> int:
        state = dict(run.meta.get("knowing_skull", {}))
        cost = self._knowing_skull_base_cost(run) + int(state.get(option_id, 0))
        if "tungsten_rod" in run.relics:
            cost = max(0, cost - 1)
        return cost

    def _refresh_knowing_skull_event(self, run: RunState) -> None:
        run.event = EventState(
            key="knowing_skull",
            name="Knowing Skull",
            description="The skull waits patiently for another offering.",
            options=[
                EventOptionState(
                    option_id="potion",
                    label="A Pick Me Up?",
                    description=f"Get a Potion. Lose {self._knowing_skull_cost(run, 'potion')} HP.",
                ),
                EventOptionState(
                    option_id="gold",
                    label="Riches?",
                    description=f"Gain 90 Gold. Lose {self._knowing_skull_cost(run, 'gold')} HP.",
                ),
                EventOptionState(
                    option_id="card",
                    label="Success?",
                    description=f"Get a Colorless card. Lose {self._knowing_skull_cost(run, 'card')} HP.",
                ),
                EventOptionState(
                    option_id="leave",
                    label="How do I leave?",
                    description=f"Lose {self._knowing_skull_cost(run, 'leave')} HP and leave.",
                ),
            ],
        )

    def _resolve_knowing_skull_option(self, run: RunState, option_id: str) -> str:
        if run.event is None or run.event.key != "knowing_skull":
            raise ValueError("Knowing Skull is not active.")
        if option_id not in {"potion", "gold", "card", "leave"}:
            raise ValueError("Invalid event option.")
        state = dict(run.meta.get("knowing_skull", {}))
        hp_loss = self._knowing_skull_cost(run, option_id)
        state[option_id] = int(state.get(option_id, 0)) + 1
        run.meta["knowing_skull"] = state
        run.hp = max(0, run.hp - hp_loss)
        if run.hp <= 0:
            run.meta.pop("knowing_skull", None)
            run.event = None
            run.phase = "defeat"
            return "The skull drains the last of your life."
        if option_id == "leave":
            run.meta.pop("knowing_skull", None)
            run.push_log("Event resolved: Knowing Skull - Leave.")
            run.event = None
            self._advance_after_noncombat(run)
            return f"You pay {hp_loss} HP to leave the skull behind."
        if option_id == "potion":
            gained = self._grant_random_potions(run, 1)
            reward_text = (
                f"You receive {POTION_LIBRARY[gained[0]].name}."
                if gained
                else "You have no room for a potion."
            )
        elif option_id == "gold":
            gained_gold = self._gain_gold(run, 90)
            reward_text = (
                f"You gain {gained_gold} Gold."
                if gained_gold > 0
                else "Ectoplasm prevents the Gold."
            )
        else:
            rarity = "rare" if self.rng.random() < 0.2 else "uncommon"
            card_key = self._pick_colorless_card(rarity=rarity)
            if card_key is None:
                reward_text = "The skull offers nothing."
            else:
                reward_text = f"{CARD_LIBRARY[card_key].name} joins your deck."
                self._add_card_to_deck(run, self.create_card_instance(run, card_key))
        self._refresh_knowing_skull_event(run)
        return f"You lose {hp_loss} HP. {reward_text}"

    def _roll_sensory_stone_cards(self, run: RunState) -> list[str]:
        choices: list[str] = []
        used: set[str] = set()
        for _ in range(self._reward_card_choice_count(run)):
            rarity = self._roll_reward_card_rarity(run, source="event", affect_offset=False)
            colorless_rarity = "rare" if rarity == "rare" else "uncommon"
            card_key = self._pick_colorless_card(rarity=colorless_rarity, exclude=used)
            if card_key is None:
                break
            used.add(card_key)
            choices.append(card_key)
        return choices

    def _resolve_sensory_stone_option(self, run: RunState, option_id: str) -> str:
        if run.event is None or run.event.key != "sensory_stone":
            raise ValueError("Sensory Stone is not active.")
        mapping = {
            "recall_one": (1, 0),
            "recall_two": (2, 5),
            "recall_three": (3, 10),
        }
        payload = mapping.get(option_id)
        if payload is None:
            raise ValueError("Invalid event option.")
        reward_count, hp_loss = payload
        if hp_loss > 0:
            run.hp = max(0, run.hp - hp_loss)
            if run.hp <= 0:
                run.event = None
                run.phase = "defeat"
                return "The memory consumes you."
        run.meta["sensory_stone_remaining"] = reward_count
        run.event = None
        run.reward = RewardState(
            source="sensory_stone",
            gold=0,
            card_choices=self._roll_sensory_stone_cards(run),
        )
        run.phase = "reward"
        if hp_loss > 0:
            return f"The memory cuts deep. Lose {hp_loss} HP and choose a Colorless card."
        return "Choose a Colorless card."

    def _resolve_we_meet_again_option(self, run: RunState, option_id: str) -> str:
        if run.event is None or run.event.key != "we_meet_again":
            raise ValueError("We Meet Again is not active.")
        payload = dict(run.meta.get("we_meet_again", {}))
        if option_id == "attack":
            run.meta.pop("we_meet_again", None)
            run.push_log("Event resolved: We Meet Again - Attack.")
            run.event = None
            self._advance_after_noncombat(run)
            return "Your acquaintance vanishes before you can strike."
        if option_id == "give_potion":
            potion_key = str(payload.get("potion_key", ""))
            if potion_key not in run.potions:
                raise ValueError("That potion is no longer available.")
            run.potions.remove(potion_key)
            offered = POTION_LIBRARY[potion_key].name
        elif option_id == "give_gold":
            gold_cost = int(payload.get("gold_cost", 0))
            if gold_cost <= 0 or run.gold < gold_cost:
                raise ValueError("You do not have enough Gold.")
            run.gold -= gold_cost
            offered = f"{gold_cost} Gold"
        elif option_id == "give_card":
            card_id = str(payload.get("card_id", ""))
            card = self._find_card(run.deck, card_id)
            if card is None:
                raise ValueError("That card is no longer available.")
            offered = self.card_name(card)
            run.deck = [entry for entry in run.deck if entry.instance_id != card.instance_id]
            self._clear_bound_relic_card(run, card.instance_id)
        else:
            raise ValueError("Invalid event option.")
        self._remember_delayed_choice_return(run)
        relic_key, relic_messages = self._grant_random_relic(run)
        run.meta.pop("we_meet_again", None)
        run.push_log(f"Event resolved: We Meet Again - {option_id}.")
        run.event = None
        if run.phase not in {"remove", "reward", "shop", "combat"}:
            self._advance_after_noncombat(run)
        suffix = f" {' '.join(relic_messages)}" if relic_messages else ""
        return f"You hand over {offered} and receive {RELIC_LIBRARY[relic_key].name}.{suffix}"

    def _resolve_standard_event_option(self, run: RunState, option_id: str) -> str:
        event = run.event
        if event is None:
            raise ValueError("No event is active.")
        event_def = EVENT_LIBRARY[event.key]
        option = next((entry for entry in event_def.options if entry.key == option_id), None)
        if option is None:
            raise ValueError("Invalid event option.")
        messages: list[str] = []
        pending_selection: str | None = None
        for effect in option.effects:
            effect_type = effect["type"]
            if effect_type == "heal":
                healed = self._heal_run(run, int(effect["value"]))
                messages.append(f"Healed {healed} HP.")
            elif effect_type == "gain_gold":
                gained = self._gain_gold(run, int(effect["value"]))
                messages.append(
                    f"Gained {gained} gold." if gained > 0 else "Ectoplasm prevents you from gaining gold."
                )
            elif effect_type == "gain_gold_range":
                amount = self.rng.randint(int(effect["min"]), int(effect["max"]))
                gained = self._gain_gold(run, amount)
                messages.append(
                    f"Gained {gained} gold." if gained > 0 else "Ectoplasm prevents you from gaining gold."
                )
            elif effect_type == "lose_gold":
                run.gold = max(0, run.gold - int(effect["value"]))
                messages.append(f"Lost {int(effect['value'])} gold.")
            elif effect_type == "lose_hp":
                run.hp = max(0, run.hp - int(effect["value"]))
                messages.append(f"Lost {int(effect['value'])} HP.")
            elif effect_type == "lose_percent_hp":
                loss = max(1, (run.max_hp * int(effect["value"])) // 100)
                run.hp = max(0, run.hp - loss)
                messages.append(f"Lost {loss} HP.")
            elif effect_type == "heal_percent_max_hp":
                amount = max(1, (run.max_hp * int(effect["value"])) // 100)
                healed = self._heal_run(run, amount)
                messages.append(f"Healed {healed} HP.")
            elif effect_type == "gain_max_hp":
                self._increase_max_hp(run, int(effect["value"]))
                messages.append(f"Max HP increased by {int(effect['value'])}.")
            elif effect_type == "lose_max_hp":
                loss = int(effect["value"])
                run.max_hp = max(1, run.max_hp - loss)
                run.hp = min(run.hp, run.max_hp)
                messages.append(f"Max HP decreased by {loss}.")
            elif effect_type == "lose_percent_max_hp":
                loss = max(1, (run.max_hp * int(effect["value"])) // 100)
                run.max_hp = max(1, run.max_hp - loss)
                run.hp = min(run.hp, run.max_hp)
                messages.append(f"Max HP decreased by {loss}.")
            elif effect_type == "gain_card":
                card_key = str(effect["key"])
                card = self.create_card_instance(run, card_key, upgraded=bool(effect.get("upgraded", False)))
                extra_messages = self._add_card_to_deck(run, card)
                messages.append(f"Gained card: {self.card_name(card)}.")
                messages.extend(extra_messages)
            elif effect_type == "upgrade_random_card":
                candidates = [card for card in run.deck if not card.upgraded]
                if candidates:
                    upgraded = self.rng.choice(candidates)
                    upgraded.upgraded = True
                    messages.append(f"{self.card_name(upgraded)} was upgraded.")
            elif effect_type == "remove_random_card":
                candidates = [card for card in run.deck if CARD_LIBRARY[card.key].rarity != "starter"]
                if not candidates:
                    candidates = list(run.deck)
                if candidates:
                    removed = self.rng.choice(candidates)
                    run.deck = [card for card in run.deck if card.instance_id != removed.instance_id]
                    messages.append(f"Removed {self.card_name(removed)} from your deck.")
            elif effect_type == "gain_random_potions":
                gained = self._grant_random_potions(run, int(effect["value"]))
                if gained:
                    messages.append(
                        "Potions gained: " + ", ".join(POTION_LIBRARY[key].name for key in gained)
                    )
            elif effect_type == "begin_remove":
                pending_selection = "remove"
            elif effect_type == "begin_upgrade":
                pending_selection = "upgrade"
            elif effect_type == "begin_transform":
                count = int(effect.get("count", 1))
                pending_selection = "transform" if count <= 1 else f"transform:{count}"
            elif effect_type == "begin_duplicate":
                pending_selection = "duplicate"
            elif effect_type == "lose_relic":
                relic_key = str(effect["key"])
                if self._remove_relic(run, relic_key):
                    messages.append(f"Lost relic: {RELIC_LIBRARY[relic_key].name}.")
            elif effect_type == "gain_relic":
                relic_key = str(effect.get("key", "random"))
                self._remember_delayed_choice_return(run)
                if relic_key == "random":
                    gained_key, gained_messages = self._grant_random_relic(run)
                else:
                    gained_key = relic_key
                    gained_messages = self._obtain_relic(run, relic_key)
                messages.append(f"Gained relic: {RELIC_LIBRARY[gained_key].name}.")
                messages.extend(gained_messages)
        if run.hp <= 0:
            run.phase = "defeat"
            run.event = None
            return "The event kills you."
        run.push_log(f"Event resolved: {event.name} - {option.label}.")
        if pending_selection == "remove":
            run.event = None
            run.phase = "remove"
            run.selection_context = "event"
            return " ".join(messages + ["Choose a card to remove."]).strip()
        if pending_selection == "upgrade":
            run.event = None
            self.begin_upgrade(run, "event")
            return " ".join(messages + ["Choose a card to upgrade."]).strip()
        if pending_selection == "transform" or (pending_selection or "").startswith("transform:"):
            run.event = None
            run.phase = "remove"
            run.selection_context = pending_selection
            return " ".join(messages + ["Choose a card to transform."]).strip()
        if pending_selection == "duplicate":
            run.event = None
            run.phase = "remove"
            run.selection_context = "duplicator"
            return " ".join(messages + ["Choose a card to duplicate."]).strip()
        if run.phase in {"remove", "reward", "shop", "combat"}:
            run.event = None
            return " ".join(messages) if messages else "You move on."
        run.event = None
        self._advance_after_noncombat(run)
        return " ".join(messages) if messages else "You move on."

    def choose_neow_option(self, run: RunState, option_id: str) -> str:
        if run.phase != "neow" or run.event is None or run.event.key != "neow":
            raise ValueError("Neow is not waiting.")
        run.event = None
        if option_id == "remove_card":
            run.phase = "remove"
            run.selection_context = "neow_remove:1"
            return "Choose a card to remove."
        if option_id == "upgrade_card":
            self.begin_upgrade(run, "neow")
            return "Choose a card to upgrade."
        if option_id == "choose_class_card":
            run.reward = RewardState(
                source="neow",
                gold=0,
                card_choices=self._roll_neow_card_choices(run, pool="class"),
            )
            run.phase = "reward"
            return "Choose a card to obtain."
        if option_id == "random_rare_card":
            card_key = self.rng.choice(self._neow_character_cards(run, rarity="rare"))
            extras = self._add_card_to_deck(run, self.create_card_instance(run, card_key))
            suffix = f" {' '.join(extras)}" if extras else ""
            return self._finish_neow(run, f"You obtain {CARD_LIBRARY[card_key].name}.{suffix}")
        if option_id == "max_hp_bonus":
            bonus = self._neow_max_hp_bonus(run)
            self._increase_max_hp(run, bonus)
            return self._finish_neow(run, f"You gain {bonus} Max HP.")
        if option_id == "common_relic":
            relic_key = self.rng.choice(self._neow_relic_pool("common", run))
            _, details = self._grant_specific_relic(run, relic_key)
            suffix = f" {' '.join(details)}" if details else ""
            return self._finish_neow(run, f"You obtain {RELIC_LIBRARY[relic_key].name}.{suffix}")
        if option_id == "gold_100":
            gained = self._gain_gold(run, 100)
            return self._finish_neow(
                run,
                f"You gain {gained} Gold." if gained > 0 else "Ectoplasm prevents you from gaining Gold.",
            )
        if option_id == "potions_3":
            gained = self._grant_random_potions(run, 3)
            names = ", ".join(POTION_LIBRARY[key].name for key in gained) or "no potions"
            return self._finish_neow(run, f"You obtain {names}.")
        if option_id == "neows_lament":
            run.meta["neows_lament"] = 3
            return self._finish_neow(run, "Neow's Lament will weaken your next 3 combats.")
        if option_id == "lose_max_hp_gain_250":
            loss = self._neow_max_hp_cost(run)
            run.max_hp = max(1, run.max_hp - loss)
            run.hp = min(run.hp, run.max_hp)
            gained = self._gain_gold(run, 250)
            return self._finish_neow(
                run,
                f"You lose {loss} Max HP and gain {gained} Gold."
                if gained > 0
                else f"You lose {loss} Max HP. Ectoplasm prevents the Gold.",
            )
        if option_id == "damage_rare_relic":
            loss = max(1, (run.hp * 30) // 100)
            run.hp = max(1, run.hp - loss)
            relic_key = self.rng.choice(self._neow_relic_pool("rare", run))
            _, details = self._grant_specific_relic(run, relic_key)
            suffix = f" {' '.join(details)}" if details else ""
            return self._finish_neow(run, f"You lose {loss} HP and obtain {RELIC_LIBRARY[relic_key].name}.{suffix}")
        if option_id == "curse_remove_2":
            curse_key = self._random_neow_curse()
            self._add_card_to_deck(run, self.create_card_instance(run, curse_key))
            run.meta["neow_pending_removals"] = 2
            run.phase = "remove"
            run.selection_context = "neow_remove:2"
            return f"You obtain {CARD_LIBRARY[curse_key].name}. Choose a card to remove."
        if option_id == "lose_gold_rare_card":
            run.gold = 0
            run.reward = RewardState(
                source="neow",
                gold=0,
                card_choices=self._roll_neow_card_choices(run, pool="rare"),
            )
            run.phase = "reward"
            return "Choose a Rare card to obtain."
        if option_id == "replace_starter_boss":
            relic_key = self.rng.choice(BOSS_RELIC_POOL)
            self._queue_pending_transition(run, act_advance=False)
            _, details = self._grant_specific_relic(run, relic_key)
            suffix = f" {' '.join(details)}" if details else ""
            message = f"You replace your starter relic with {RELIC_LIBRARY[relic_key].name}.{suffix}"
            run.push_log(f"Neow: {message}")
            if run.phase == "neow":
                self._complete_pending_transition(run)
            return message
        raise ValueError("Unknown Neow option.")

    def _finish_neow(self, run: RunState, message: str) -> str:
        run.selection_context = None
        run.event = None
        run.reward = None
        self._prepare_map_choices(run)
        run.phase = "map"
        run.push_log(f"Neow: {message}")
        return message

    def _neow_character_cards(self, run: RunState, *, rarity: str | None = None) -> list[str]:
        pool = list(CHARACTER_LIBRARY[run.character]["card_pool"])
        if rarity is not None:
            pool = [key for key in pool if CARD_LIBRARY[key].rarity == rarity]
        return pool

    def _neow_relic_pool(self, rarity: str, run: RunState) -> list[str]:
        pool = self._eligible_relic_candidates(run, TREASURE_RELIC_POOL, rarities={rarity})
        return pool or self._eligible_relic_candidates(run, TREASURE_RELIC_POOL)

    def _roll_neow_card_choices(self, run: RunState, *, pool: str) -> list[str]:
        if pool == "rare":
            choices = self._neow_character_cards(run, rarity="rare")
        else:
            choices = self._neow_character_cards(run)
        self.rng.shuffle(choices)
        return choices[:3]

    def _random_neow_curse(self) -> str:
        curses = [
            key
            for key, card in CARD_LIBRARY.items()
            if card.rarity == "curse" and key not in {"ascenders_bane", "necronomicurse", "curse_of_the_bell"}
        ]
        return self.rng.choice(curses)

    def play_card(
        self,
        run: RunState,
        instance_id: str,
        target_enemy_id: str | None = None,
    ) -> str:
        combat = self._require_combat(run)
        card = self._find_card(combat.hand, instance_id)
        if card is None:
            raise ValueError("Card is not in hand.")

        card_def = CARD_LIBRARY[card.key]
        blue_candle_curse = (
            card_def.card_type == "curse"
            and "blue_candle" in run.relics
        )
        medical_kit_status = (
            card_def.card_type == "status"
            and "medical_kit" in run.relics
        )
        if not card_def.playable and not blue_candle_curse and not medical_kit_status:
            raise ValueError("That card is unplayable.")
        if "velvet_choker" in run.relics and combat.player_statuses.get("cards_played_turn", 0) >= 6:
            raise ValueError("Velvet Choker prevents playing more than 6 cards this turn.")
        target_enemy = self._select_target_enemy(run, card_def.target, target_enemy_id)
        cost = 0 if blue_candle_curse or medical_kit_status else self.card_cost(card, combat)
        if cost >= 0 and cost > combat.energy:
            raise ValueError("Not enough energy.")
        spent_energy = combat.energy if cost < 0 else cost
        if cost < 0 and "chemical_x" in run.relics:
            spent_energy += 2
        if cost < 0:
            combat.energy = 0
        else:
            combat.energy -= cost
        if self.card_is_ethereal(card, combat) and combat.player_statuses.get("next_ethereal_free", 0) > 0 and cost == 0:
            combat.player_statuses["next_ethereal_free"] -= 1
            if combat.player_statuses["next_ethereal_free"] <= 0:
                combat.player_statuses.pop("next_ethereal_free", None)
        if card_def.card_type == "attack" and combat.player_statuses.get("swivel", 0) > 0:
            combat.player_statuses["swivel"] -= 1
            if combat.player_statuses["swivel"] <= 0:
                combat.player_statuses.pop("swivel", None)
        combat.hand = [entry for entry in combat.hand if entry.instance_id != instance_id]
        combat.player_statuses["cards_played_turn"] = (
            combat.player_statuses.get("cards_played_turn", 0) + 1
        )
        combat.active_card_key = card.key
        combat.last_target_enemy_id = target_enemy.enemy_id if target_enemy is not None else None
        combat.player_meta["active_card_instance_id"] = card.instance_id
        combat.player_meta["active_card_misc"] = card.misc
        combat.player_meta["active_card_upgraded"] = card.upgraded
        combat.player_meta["played_card_cost"] = spent_energy if cost < 0 else cost
        played_card_keys = {
            str(key): int(value)
            for key, value in dict(combat.player_meta.get("played_card_keys_turn", {})).items()
        }
        played_card_keys[card.key] = played_card_keys.get(card.key, 0) + 1
        combat.player_meta["played_card_keys_turn"] = played_card_keys
        if card_def.card_type == "attack" and cost == 0 and "wrist_blade" in run.relics:
            combat.player_meta["wrist_blade_bonus"] = 4
        if card_def.card_type == "attack" and "pen_nib" in run.relics:
            if combat.player_statuses.get("pen_nib_counter", 0) >= 9:
                combat.player_meta["double_attack_damage_card"] = (
                    int(combat.player_meta.get("double_attack_damage_card", 0)) + 1
                )
                combat.player_statuses["pen_nib_counter"] = 0
                messages = ["Pen Nib doubles this attack."]
            else:
                messages = []
        else:
            messages = []
        if cost >= 0 and int(dict(combat.player_meta.get("free_play_counts", {})).get(card.instance_id, 0)) > 0:
            self._consume_free_play(combat, card.instance_id)
        messages.append(f"You play {self.card_name(card)}.")
        if combat.player_statuses.get("akabeko_pending", 0) > 0 and card_def.card_type == "attack":
            combat.player_statuses["first_attack_bonus"] = combat.player_statuses.pop(
                "akabeko_pending",
                0,
            )
        if card_def.card_type == "skill":
            for enemy in combat.enemies:
                if enemy.meta.get("enrage"):
                    enemy.statuses["strength"] = enemy.statuses.get("strength", 0) + int(
                        enemy.meta["enrage"]
                    )
                    messages.append(f"{enemy.name} enrages and gains Strength.")
        if blue_candle_curse:
            hp_loss = 1
            if "tungsten_rod" in run.relics:
                hp_loss = max(0, hp_loss - 1)
            if hp_loss > 0:
                run.hp = max(0, run.hp - hp_loss)
                messages.append(f"Blue Candle burns you for {hp_loss} HP.")
                self._trigger_combat_hp_loss_relics(run, combat, hp_loss, messages)

        for action in self._actions_for_card(card):
            messages.extend(
                self._resolve_player_action(
                    run,
                    combat,
                    action,
                    target_enemy=target_enemy,
                    spent_energy=spent_energy,
                )
            )
            if run.hp <= 0:
                combat.log.extend(messages)
                combat.log = combat.log[-12:]
                return self._resolve_player_defeat(run, messages)
            if not self._has_remaining_enemies(combat):
                break
        repeat_count = 0
        if card_def.card_type == "skill" and card.key != "burst" and combat.player_statuses.get("burst", 0) > 0:
            combat.player_statuses["burst"] -= 1
            if combat.player_statuses["burst"] <= 0:
                combat.player_statuses.pop("burst", None)
            repeat_count += 1
        if card_def.card_type == "power" and card.key != "amplify" and combat.player_statuses.get("amplify", 0) > 0:
            combat.player_statuses["amplify"] -= 1
            if combat.player_statuses["amplify"] <= 0:
                combat.player_statuses.pop("amplify", None)
            repeat_count += 1
        if combat.player_statuses.get("echo_form", 0) > 0 and not combat.player_meta.get("echo_form_used_turn"):
            combat.player_meta["echo_form_used_turn"] = True
            repeat_count += 1
        replay_counts = {
            str(key): int(value)
            for key, value in dict(combat.player_meta.get("replay_counts", {})).items()
        }
        replay_count = replay_counts.pop(card.instance_id, 0)
        if replay_counts:
            combat.player_meta["replay_counts"] = replay_counts
        else:
            combat.player_meta.pop("replay_counts", None)
        for index in range(repeat_count):
            source = "Burst" if index == 0 and card_def.card_type == "skill" else "Echo Form"
            if card_def.card_type == "power" and combat.player_statuses.get("amplify", 0) >= 0:
                source = "Amplify" if source != "Burst" and card_def.card_type == "power" and repeat_count == 1 else source
            messages.append(f"{self.card_name(card)} is played again by {source}.")
            for action in self._actions_for_card(card):
                messages.extend(
                    self._resolve_player_action(
                        run,
                        combat,
                        action,
                        target_enemy=target_enemy,
                        spent_energy=spent_energy,
                    )
                )
                if run.hp <= 0:
                    combat.log.extend(messages)
                    combat.log = combat.log[-12:]
                    return self._resolve_player_defeat(run, messages)
                if not self._has_remaining_enemies(combat):
                    break
        for _ in range(replay_count):
            messages.append(f"{self.card_name(card)} replays itself.")
            for action in self._actions_for_card(card):
                messages.extend(
                    self._resolve_player_action(
                        run,
                        combat,
                        action,
                        target_enemy=target_enemy,
                        spent_energy=spent_energy,
                    )
                )
                if run.hp <= 0:
                    combat.log.extend(messages)
                    combat.log = combat.log[-12:]
                    return self._resolve_player_defeat(run, messages)
                if not self._has_remaining_enemies(combat):
                    break

        card.misc = int(combat.player_meta.get("active_card_misc", card.misc))
        if blue_candle_curse:
            messages.extend(self._exhaust_card(run, combat, card))
        elif self.card_exhausts(card, combat):
            if card_def.card_type != "power" and "strange_spoon" in run.relics and self.rng.random() < 0.5:
                combat.discard_pile.append(card)
                messages.append(f"Strange Spoon spares {self.card_name(card)} from Exhaust.")
            else:
                messages.extend(self._exhaust_card(run, combat, card))
        elif card_def.card_type == "power":
            combat.exhaust_pile.append(card)
        else:
            combat.discard_pile.append(card)
        if card.key != "rebound" and combat.player_statuses.get("rebound", 0) > 0:
            combat.player_statuses["rebound"] -= 1
            if combat.player_statuses["rebound"] <= 0:
                combat.player_statuses.pop("rebound", None)
            if card in combat.discard_pile:
                combat.discard_pile.remove(card)
                combat.draw_pile.append(card)
                messages.append(f"Rebound places {self.card_name(card)} on top of your draw pile.")
        if card.key == "streamline":
            card.cost_adjustment -= 1
        if card_def.card_type != "attack" and combat.player_statuses.get("hex", 0) > 0:
            messages.extend(
                self._create_cards_in_combat(
                    run,
                    combat,
                    key="dazed",
                    location="draw",
                    count=combat.player_statuses.get("hex", 0),
                )
            )
        combat.active_card_key = None
        messages.extend(self._handle_card_play_triggers(run, combat, card_def))
        combat.last_target_enemy_id = None
        combat.player_meta.pop("active_card_instance_id", None)
        combat.player_meta.pop("active_card_misc", None)
        combat.player_meta.pop("active_card_upgraded", None)
        combat.player_meta.pop("wrist_blade_bonus", None)
        combat.player_meta.pop("played_card_cost", None)
        combat.player_meta.pop("double_attack_damage_card", None)
        if run.hp <= 0:
            combat.log.extend(messages)
            combat.log = combat.log[-12:]
            return self._resolve_player_defeat(run, messages)
        if not self._has_remaining_enemies(combat):
            combat.log.extend(messages)
            combat.log = combat.log[-12:]
            return self._resolve_victory(run)
        post_messages, forced_end = self._handle_post_card_play(run, combat)
        messages.extend(post_messages)
        combat.log.extend(messages)
        combat.log = combat.log[-12:]
        if run.hp <= 0:
            return self._resolve_player_defeat(run, messages)
        if not self._has_remaining_enemies(combat):
            return self._resolve_victory(run)
        if forced_end:
            end_message = self._complete_end_turn(run)
            return " ".join(messages + [end_message]).strip()
        return " ".join(messages)

    def use_potion(
        self,
        run: RunState,
        potion_key: str,
        target_enemy_id: str | None = None,
    ) -> str:
        combat = self._require_combat(run)
        if potion_key not in run.potions:
            raise ValueError("Potion not found.")
        potion = POTION_LIBRARY[potion_key]
        target_enemy = self._select_target_enemy(run, potion.target, target_enemy_id)
        run.potions.remove(potion_key)
        messages = [f"You use {potion.name}."]
        if "toy_ornithopter" in run.relics:
            healed = self._heal_run(run, 5)
            self._sync_player_hp_relics(run, combat, messages)
            if healed > 0:
                messages.append(f"Toy Ornithopter heals {healed} HP.")
        actions = list(potion.actions)
        if "sacred_bark" in run.relics:
            actions = actions + list(potion.actions)
        for action in actions:
            messages.extend(
                self._resolve_player_action(
                    run,
                    combat,
                    action,
                    target_enemy=target_enemy,
                    from_potion=True,
                )
            )
            if run.hp <= 0:
                combat.log.extend(messages)
                combat.log = combat.log[-12:]
                return self._resolve_player_defeat(run, messages)
        combat.log.extend(messages)
        combat.log = combat.log[-12:]
        if not self._has_remaining_enemies(combat):
            return self._resolve_victory(run)
        return " ".join(messages)

    def discard_gambling_chip_card(self, run: RunState, instance_id: str) -> str:
        combat = self._require_combat(run)
        if run.selection_context != "gambling_chip":
            raise ValueError("Gambling Chip is not active.")
        card = self._find_card(combat.hand, instance_id)
        if card is None:
            raise ValueError("Card is not in hand.")
        combat.hand.remove(card)
        messages = self._discard_card(run, combat, card)
        combat.player_meta["gambling_chip_discards"] = int(
            combat.player_meta.get("gambling_chip_discards", 0)
        ) + 1
        return " ".join(["Gambling Chip discards the card."] + messages)

    def finish_gambling_chip(self, run: RunState) -> str:
        combat = self._require_combat(run)
        if run.selection_context != "gambling_chip":
            raise ValueError("Gambling Chip is not active.")
        draw_count = int(combat.player_meta.pop("gambling_chip_discards", 0))
        run.selection_context = None
        if draw_count > 0:
            self._draw_cards(run, combat, draw_count)
            return f"Gambling Chip redraws {draw_count} card(s)."
        return "You keep your opening hand."

    def end_turn(self, run: RunState) -> str:
        if run.selection_context == "gambling_chip":
            raise ValueError("Resolve Gambling Chip before ending your turn.")
        return self._complete_end_turn(run)

    def _finish_card_reward(self, run: RunState, reward: RewardState) -> None:
        source = reward.source
        if source == "boss" and reward.relic_choices:
            run.reward = RewardState(
                source="boss_relic",
                gold=0,
                relic_choices=list(reward.relic_choices),
            )
            run.phase = "boss_relic"
            return
        if source == "toolbox":
            run.reward = None
            run.phase = "combat"
            if "gambling_chip" in run.relics and run.combat is not None and run.combat.hand:
                run.selection_context = "gambling_chip"
            return
        if source == "orrery":
            remaining = max(0, int(run.meta.get("orrery_remaining", 1)) - 1)
            if remaining > 0:
                run.meta["orrery_remaining"] = remaining
                run.reward = RewardState(
                    source="orrery",
                    gold=0,
                    card_choices=self._roll_reward_cards(run, source="combat"),
                )
                run.phase = "reward"
                return
            run.meta.pop("orrery_remaining", None)
            run.reward = None
            self._resume_after_delayed_choice(run)
            return
        if source == "sensory_stone":
            remaining = max(0, int(run.meta.get("sensory_stone_remaining", 1)) - 1)
            if remaining > 0:
                run.meta["sensory_stone_remaining"] = remaining
                run.reward = RewardState(
                    source="sensory_stone",
                    gold=0,
                    card_choices=self._roll_sensory_stone_cards(run),
                )
                run.phase = "reward"
                return
            run.meta.pop("sensory_stone_remaining", None)
            run.reward = None
            self._prepare_map_choices(run)
            run.phase = "map"
            return
        if source in {"combat", "elite", "prayer_wheel"}:
            pending = int(run.meta.get("prayer_wheel_rewards", 0))
            if pending > 0:
                run.meta["prayer_wheel_rewards"] = pending - 1
                run.reward = RewardState(
                    source="prayer_wheel",
                    gold=0,
                    card_choices=self._roll_reward_cards(run, source="combat"),
                )
                run.phase = "reward"
                return
            run.meta.pop("prayer_wheel_rewards", None)
        if source == "neow":
            run.reward = None
            self._prepare_map_choices(run)
            run.phase = "map"
            return
        if source == "tiny_house":
            run.reward = None
            if not self._complete_pending_transition(run):
                self._prepare_map_choices(run)
                run.phase = "map"
            return
        run.reward = None
        self._prepare_map_choices(run)
        run.phase = "map"

    def choose_reward_card(self, run: RunState, index: int | None) -> str:
        if run.phase != "reward" or run.reward is None:
            raise ValueError("No reward is waiting.")
        reward = run.reward
        if reward.source in {"neow", "event_forced", "tiny_house", "toolbox", "orrery"} and index is None:
            raise ValueError("You must choose a reward.")
        if index is None:
            chosen = None
        else:
            if index < 0 or index >= len(reward.card_choices):
                raise ValueError("Invalid reward choice.")
            chosen = reward.card_choices[index]

        if chosen:
            if reward.source == "toolbox":
                combat = run.combat
                if combat is None:
                    raise ValueError("No combat is active.")
                card = self.create_card_instance(run, chosen)
                combat.hand.append(card)
                message = f"{CARD_LIBRARY[chosen].name} joins your hand."
            else:
                card = self.create_card_instance(run, chosen)
                extras = self._add_card_to_deck(run, card)
                message = f"{CARD_LIBRARY[chosen].name} joins your deck."
                if extras:
                    message = f"{message} {' '.join(extras)}"
        else:
            message = "You skip the card reward."
        self._finish_card_reward(run, reward)
        run.push_log(message)
        return message

    def take_singing_bowl(self, run: RunState) -> str:
        if run.phase != "reward" or run.reward is None:
            raise ValueError("No reward is waiting.")
        if run.reward.source in {"event_forced", "toolbox"}:
            raise ValueError("Singing Bowl is not available here.")
        self._increase_max_hp(run, 2, heal_current=False)
        reward = run.reward
        self._finish_card_reward(run, reward)
        message = "Singing Bowl grants 2 Max HP."
        run.push_log(message)
        return message

    def choose_boss_relic(self, run: RunState, index: int) -> str:
        if run.phase != "boss_relic" or run.reward is None:
            raise ValueError("No boss relic reward is waiting.")
        if index < 0 or index >= len(run.reward.relic_choices):
            raise ValueError("Invalid boss relic choice.")
        relic_key = run.reward.relic_choices[index]
        run.reward = None
        self._queue_pending_transition(run, act_advance=True)
        details = self._obtain_relic(run, relic_key)
        if run.phase == "boss_relic":
            self._complete_pending_transition(run)
        message = f"You claim {RELIC_LIBRARY[relic_key].name}."
        if details:
            message = f"{message} {' '.join(details)}"
        run.push_log(f"Boss relic claimed: {RELIC_LIBRARY[relic_key].name}.")
        return message

    def choose_treasure_relic(self, run: RunState) -> str:
        if run.phase != "treasure" or run.reward is None or not run.reward.relic_choices:
            raise ValueError("No treasure chest is open.")
        relic_key = run.reward.relic_choices[0]
        _, details = self._grant_specific_relic(run, relic_key)
        run.reward = None
        if run.phase == "treasure":
            self._advance_after_noncombat(run)
        suffix = f" {' '.join(details)}" if details else ""
        return f"You claim {RELIC_LIBRARY[relic_key].name}.{suffix}"

    def choose_sapphire_key(self, run: RunState) -> str:
        if run.phase != "treasure":
            raise ValueError("No treasure chest is open.")
        if self.has_key(run, "sapphire"):
            raise ValueError("You already have the Sapphire Key.")
        run.keys.append("sapphire")
        run.reward = None
        self._advance_after_noncombat(run)
        run.push_log("Sapphire Key claimed from a chest.")
        return "You forgo the relic and take the Sapphire Key."

    def buy_shop_offer(self, run: RunState, offer_id: str) -> str:
        if run.phase != "shop" or run.shop is None:
            raise ValueError("No shop is open.")
        offer = next((entry for entry in run.shop.offers if entry.offer_id == offer_id), None)
        if offer is None:
            raise ValueError("Offer not found.")
        if run.gold < offer.cost:
            raise ValueError("Not enough gold.")
        if offer.kind == "potion" and len(run.potions) >= self._max_potion_slots(run):
            raise ValueError("Your potion belt is full.")
        if offer.kind == "potion" and "sozu" in run.relics:
            raise ValueError("Sozu prevents obtaining potions.")

        had_courier = "courier" in run.relics
        if offer.cost > 0:
            run.meta["maw_bank_broken"] = 1
        run.gold -= offer.cost
        if offer.kind == "card":
            extras = self._add_card_to_deck(run, self.create_card_instance(run, offer.key))
            suffix = f" {' '.join(extras)}" if extras else ""
            result = f"Purchased {CARD_LIBRARY[offer.key].name}.{suffix}"
        elif offer.kind == "relic":
            details = self._obtain_relic(run, offer.key)
            suffix = f" {' '.join(details)}" if details else ""
            result = f"Purchased {RELIC_LIBRARY[offer.key].name}.{suffix}"
        elif offer.kind == "potion":
            run.potions.append(offer.key)
            result = f"Purchased {POTION_LIBRARY[offer.key].name}."
        else:
            raise ValueError("Unsupported shop offer.")

        if run.shop is not None:
            offer_index = next(
                index
                for index, entry in enumerate(run.shop.offers)
                if entry.offer_id == offer_id
            )
            replacement = None
            if had_courier:
                replacement = self._restock_shop_offer(run, offer)
            if replacement is None:
                run.shop.offers = [
                    entry for entry in run.shop.offers if entry.offer_id != offer_id
                ]
            else:
                run.shop.offers[offer_index] = replacement
            self._refresh_shop_prices(run)
        return result

    def begin_shop_remove(self, run: RunState) -> None:
        if run.phase != "shop" or run.shop is None:
            raise ValueError("No shop is open.")
        if run.shop.remove_used:
            raise ValueError("Card removal has already been used.")
        if run.gold < run.shop.remove_cost:
            raise ValueError("Not enough gold.")
        run.phase = "remove"
        run.selection_context = "shop"

    def leave_shop(self, run: RunState) -> str:
        if run.phase != "shop":
            raise ValueError("No shop is open.")
        self._advance_after_noncombat(run)
        return "You leave the merchant behind."

    def abandon_run(self, run: RunState) -> str:
        run.phase = "defeat"
        run.combat = None
        run.reward = None
        run.shop = None
        run.event = None
        return "Run abandoned."

    def card_name(self, card: CardInstance) -> str:
        base = CARD_LIBRARY[card.key].name
        return f"{base}+" if card.upgraded else base

    def _persistent_card(self, run: RunState, card: CardInstance) -> CardInstance | None:
        return self._find_card(run.deck, card.instance_id)

    def _add_card_to_deck(self, run: RunState, card: CardInstance) -> list[str]:
        card_def = CARD_LIBRARY[card.key]
        messages: list[str] = []
        ignore_omamori = bool(run.meta.pop("ignore_omamori_once", 0))
        if card_def.rarity == "curse":
            omamori_charges = int(run.meta.get("omamori_charges", 0))
            if "omamori" in run.relics and omamori_charges > 0 and not ignore_omamori:
                omamori_charges -= 1
                run.meta["omamori_charges"] = omamori_charges
                if omamori_charges <= 0:
                    run.meta.pop("omamori_charges", None)
                return ["Omamori negates the Curse."]
            if "darkstone_periapt" in run.relics:
                self._increase_max_hp(run, 6)
                messages.append("Darkstone Periapt increases your Max HP by 6.")
            if "du_vu_doll" in run.relics:
                messages.append("Du-Vu Doll will grant extra Strength in combat.")
        if card_def.card_type == "attack" and "molten_egg" in run.relics:
            card.upgraded = True
        if card_def.card_type == "skill" and "toxic_egg" in run.relics:
            card.upgraded = True
        if card_def.card_type == "power" and "frozen_egg" in run.relics:
            card.upgraded = True
        run.deck.append(card)
        if "ceramic_fish" in run.relics:
            if self._gain_gold(run, 9) > 0:
                messages.append("Ceramic Fish grants 9 Gold.")
            else:
                messages.append("Ectoplasm prevents Ceramic Fish from granting Gold.")
        return messages

    def _transform_card(self, run: RunState, target: CardInstance) -> str:
        replacement_key = self._roll_transform_card_key(run, target)
        if replacement_key is None:
            raise ValueError("No valid transform result is available for that card.")
        run.deck = [card for card in run.deck if card.instance_id != target.instance_id]
        self._clear_bound_relic_card(run, target.instance_id)
        replacement = self.create_card_instance(run, replacement_key)
        extras = self._add_card_to_deck(run, replacement)
        message = f"{self.card_name(target)} transforms into {CARD_LIBRARY[replacement_key].name}."
        if extras:
            message = f"{message} {' '.join(extras)}"
        context = run.selection_context or ""
        if context.startswith("transform:"):
            remaining = max(0, int(context.split(":", 1)[1]) - 1)
            if remaining > 0:
                run.selection_context = f"transform:{remaining}"
                run.phase = "remove"
                run.event = None
                return f"{message} Choose another card to transform."
        if not self._complete_pending_transition(run):
            self._advance_after_noncombat(run)
        return message

    def _astrolabe_transform_card(self, run: RunState, target: CardInstance) -> str:
        replacement_key = self._roll_transform_card_key(run, target)
        if replacement_key is None:
            raise ValueError("No valid Astrolabe transform result is available for that card.")
        run.deck = [card for card in run.deck if card.instance_id != target.instance_id]
        self._clear_bound_relic_card(run, target.instance_id)
        replacement = self.create_card_instance(run, replacement_key, upgraded=True)
        extras = self._add_card_to_deck(run, replacement)
        remaining = max(0, int((run.selection_context or "astrolabe:1").split(":", 1)[1]) - 1)
        message = (
            f"{self.card_name(target)} transforms into {self.card_name(replacement)}."
        )
        if extras:
            message = f"{message} {' '.join(extras)}"
        if remaining > 0:
            run.selection_context = f"astrolabe:{remaining}"
            run.phase = "remove"
            run.event = None
            return f"{message} Choose another card to transform."
        run.selection_context = None
        run.event = None
        if not self._complete_pending_transition(run):
            self._advance_after_noncombat(run)
        return message

    def _roll_transform_card_key(self, run: RunState, target: CardInstance) -> str | None:
        target_def = CARD_LIBRARY[target.key]
        rarity = target_def.rarity
        if rarity == "status":
            return None
        character_cards = set(CHARACTER_LIBRARY[run.character]["card_pool"])
        if target_def.rarity == "curse":
            pool = [
                key
                for key, card in CARD_LIBRARY.items()
                if card.rarity == "curse" and key != target.key
            ]
        elif target.key in character_cards:
            pool = [
                key
                for key in CHARACTER_LIBRARY[run.character]["card_pool"]
                if CARD_LIBRARY[key].rarity == rarity and key != target.key
            ]
        else:
            pool = [
                key
                for key, card in CARD_LIBRARY.items()
                if key not in character_cards
                and card.rarity == rarity
                and card.rarity not in {"starter", "status", "curse"}
                and key != target.key
            ]
        if not pool:
            return None
        return self.rng.choice(pool)

    def _offer_bonfire_card(self, run: RunState, target: CardInstance) -> str:
        target_def = CARD_LIBRARY[target.key]
        run.deck = [card for card in run.deck if card.instance_id != target.instance_id]
        messages = [f"You offer {self.card_name(target)} to the bonfire spirits."]
        if target_def.rarity == "curse":
            _, relic_messages = self._grant_specific_relic(run, "spirit_poop")
            messages.append("The spirits recoil and leave behind Spirit Poop.")
            messages.extend(relic_messages)
        elif target_def.rarity in {"common", "special", "status"}:
            healed = self._heal_run(run, 5)
            messages.append(f"The spirits restore {healed} HP.")
        elif target_def.rarity == "uncommon":
            healed = self._heal_run(run, run.max_hp)
            messages.append(f"The spirits restore {healed} HP.")
        elif target_def.rarity == "rare":
            self._increase_max_hp(run, 10)
            healed = self._heal_run(run, run.max_hp)
            messages.append("The spirits increase your Max HP by 10.")
            messages.append(f"The spirits restore {healed} HP.")
        else:
            messages.append("The spirits accept the offering, but nothing else happens.")
        self._advance_after_noncombat(run)
        return " ".join(message for message in messages if message)

    def _set_card_cost(self, card: CardInstance, new_cost: int) -> None:
        card_def = CARD_LIBRARY[card.key]
        if card.upgraded and card_def.upgraded_cost is not None:
            base = card_def.upgraded_cost
        else:
            base = card_def.cost
        if base < 0:
            return
        card.cost_adjustment = max(0, new_cost) - base

    def card_retain(self, card: CardInstance) -> bool:
        card_def = CARD_LIBRARY[card.key]
        if card.upgraded and card_def.upgraded_retain is not None:
            return card_def.upgraded_retain
        return card_def.retain

    def card_innate(self, card: CardInstance) -> bool:
        card_def = CARD_LIBRARY[card.key]
        if card.upgraded and card_def.upgraded_innate is not None:
            return card_def.upgraded_innate
        return card_def.innate

    def card_is_ethereal(self, card: CardInstance, combat: CombatState | None = None) -> bool:
        if CARD_LIBRARY[card.key].ethereal:
            return True
        if combat is None:
            return False
        granted = {str(entry) for entry in list(combat.player_meta.get("granted_ethereal", []))}
        return card.instance_id in granted

    def _meta_id_set(self, combat: CombatState, key: str) -> set[str]:
        return {str(entry) for entry in list(combat.player_meta.get(key, []))}

    def _store_meta_id_set(self, combat: CombatState, key: str, values: set[str]) -> None:
        if values:
            combat.player_meta[key] = sorted(values)
        else:
            combat.player_meta.pop(key, None)

    def _osty_hp(self, combat: CombatState) -> int:
        return max(0, int(combat.player_meta.get("osty_hp", 0)))

    def _osty_max_hp(self, combat: CombatState) -> int:
        return max(0, int(combat.player_meta.get("osty_max_hp", 0)))

    def _osty_alive(self, combat: CombatState) -> bool:
        return self._osty_hp(combat) > 0

    def _summon_osty(self, combat: CombatState, amount: int) -> int:
        amount = max(0, int(amount))
        if amount <= 0:
            return 0
        combat.player_meta["osty_hp"] = self._osty_hp(combat) + amount
        combat.player_meta["osty_max_hp"] = self._osty_max_hp(combat) + amount
        return amount

    def _heal_osty(self, combat: CombatState, amount: int) -> int:
        amount = max(0, int(amount))
        if amount <= 0 or self._osty_max_hp(combat) <= 0:
            return 0
        healed = min(self._osty_max_hp(combat), self._osty_hp(combat) + amount) - self._osty_hp(combat)
        if healed > 0:
            combat.player_meta["osty_hp"] = self._osty_hp(combat) + healed
        return healed

    def _register_combat_death(self, combat: CombatState) -> None:
        for pile in (combat.hand, combat.draw_pile, combat.discard_pile, combat.exhaust_pile):
            for card in pile:
                if card.key == "melancholy":
                    card.cost_adjustment -= 1

    def _damage_osty(
        self,
        run: RunState,
        combat: CombatState,
        damage: int,
        messages: list[str],
        *,
        source: str = "",
    ) -> int:
        damage = max(0, int(damage))
        if damage <= 0 or not self._osty_alive(combat):
            return 0
        current = self._osty_hp(combat)
        lost = min(current, damage)
        combat.player_meta["osty_hp"] = current - lost
        if combat.player_statuses.get("necro_mastery", 0) > 0 and lost > 0:
            for enemy in list(combat.enemies):
                dealt, extra_messages = self._deal_damage_to_enemy(run, combat, enemy, lost)
                messages.append(f"Necro Mastery deals {dealt} damage to {enemy.name}.")
                messages.extend(extra_messages)
            combat.enemies = self._prune_enemies(combat.enemies)
        if self._osty_hp(combat) <= 0:
            combat.player_meta["osty_hp"] = 0
            combat.player_statuses["skip_player_turn"] = combat.player_statuses.get("skip_player_turn", 0) + 1
            prefix = f"{source} " if source else ""
            messages.append(f"{prefix}Osty dies. You lose your next turn.")
            self._register_combat_death(combat)
        return lost

    def _record_osty_attack(self, run: RunState, combat: CombatState, messages: list[str]) -> None:
        combat.player_meta["osty_attacks_turn"] = int(combat.player_meta.get("osty_attacks_turn", 0)) + 1
        combat.player_meta["osty_attacks_combat"] = int(combat.player_meta.get("osty_attacks_combat", 0)) + 1
        if "bone_flute" in run.relics:
            self._gain_player_block(run, combat, 2, messages, message="Bone Flute grants {gained} Block.")

    def _apply_enemy_vulnerable_multiplier(
        self,
        damage: int,
        attacker_statuses: dict[str, int],
        defender_statuses: dict[str, int],
    ) -> int:
        if defender_statuses.get("vulnerable", 0) <= 0:
            return max(0, damage)
        if attacker_statuses.get("paper_frog", 0) > 0:
            multiplier = 10 if defender_statuses.get("debilitate", 0) > 0 else 7
            return max(0, (damage * multiplier) // 4)
        if defender_statuses.get("debilitate", 0) > 0:
            return max(0, damage * 2)
        return max(0, (damage * 3) // 2)

    def _osty_hit_enemy(
        self,
        run: RunState,
        combat: CombatState,
        enemy: EnemyState,
        base_damage: int,
    ) -> list[str]:
        damage = max(0, int(base_damage) + combat.player_statuses.get("calcify", 0))
        damage = self._apply_enemy_vulnerable_multiplier(
            damage,
            combat.player_statuses,
            enemy.statuses,
        )
        dealt, extra_messages = self._deal_damage_to_enemy(run, combat, enemy, damage)
        messages = [f"Osty deals {dealt} damage to {enemy.name}."]
        messages.extend(extra_messages)
        sic_em_targets = {
            str(key): int(value)
            for key, value in dict(combat.player_meta.get("sic_em_targets", {})).items()
        }
        summon_gain = sic_em_targets.get(enemy.enemy_id, 0)
        if summon_gain > 0 and dealt > 0:
            gained = self._summon_osty(combat, summon_gain)
            messages.append(f"Sic 'Em summons {gained}.")
        if combat.player_statuses.get("reaper_form", 0) > 0 and dealt > 0:
            messages.extend(self._apply_status_from_action(run, combat, target="enemy", status="doom", value=dealt, target_enemy=enemy))
        return messages

    def _osty_attack_target(
        self,
        run: RunState,
        combat: CombatState,
        enemy: EnemyState | None,
        base_damage: int,
    ) -> list[str]:
        if not self._osty_alive(combat):
            return ["Osty is not alive."]
        target = enemy or self._default_target_enemy(combat)
        if target is None:
            return []
        messages: list[str] = []
        self._record_osty_attack(run, combat, messages)
        messages.extend(self._osty_hit_enemy(run, combat, target, base_damage))
        if target.hp <= 0:
            messages.append(f"{target.name} is defeated.")
            combat.enemies = self._prune_enemies(combat.enemies)
        return messages

    def _osty_attack_all_targets(
        self,
        run: RunState,
        combat: CombatState,
        base_damage: int,
    ) -> list[str]:
        if not self._osty_alive(combat):
            return ["Osty is not alive."]
        messages: list[str] = []
        self._record_osty_attack(run, combat, messages)
        for enemy in list(combat.enemies):
            messages.extend(self._osty_hit_enemy(run, combat, enemy, base_damage))
            if enemy.hp <= 0:
                messages.append(f"{enemy.name} is defeated.")
        combat.enemies = self._prune_enemies(combat.enemies)
        return messages

    def _adjust_enemy_attack_damage(self, run: RunState, enemy: EnemyState, damage: int) -> int:
        adjusted = max(0, int(damage))
        if "undying_sigil" in run.relics and enemy.hp > 0 and enemy.statuses.get("doom", 0) >= enemy.hp:
            adjusted //= 2
        return adjusted

    def _add_random_ethereal_cards(self, run: RunState, combat: CombatState, count: int) -> list[str]:
        candidates = [
            key
            for key in CHARACTER_LIBRARY[run.character]["card_pool"]
            if CARD_LIBRARY[key].ethereal
        ]
        if not candidates:
            return []
        messages: list[str] = []
        for _ in range(count):
            key = self.rng.choice(candidates)
            card = self.create_card_instance(run, key)
            combat.hand.append(card)
            messages.append(f"{self.card_name(card)} is added to your hand.")
        return messages

    def _apply_necrobinder_opening_effects(self, run: RunState, combat: CombatState) -> None:
        if "phylactery_unbound" in run.relics:
            gained = self._summon_osty(combat, 5)
            if gained > 0:
                combat.log.append(f"Phylactery Unbound summons {gained}.")
        if "funerary_mask" in run.relics:
            combat.log.extend(self._create_cards_in_combat(run, combat, key="soul", location="draw", count=3))
        if "big_hat" in run.relics:
            combat.log.extend(self._add_random_ethereal_cards(run, combat, 2))

    def _apply_necrobinder_turn_start_effects(self, run: RunState, combat: CombatState) -> None:
        summon_amount = 0
        if "bound_phylactery" in run.relics:
            summon_amount += 1
        if "phylactery_unbound" in run.relics:
            summon_amount += 2
        summon_amount += combat.player_statuses.pop("next_turn_summon", 0)
        if summon_amount > 0:
            gained = self._summon_osty(combat, summon_amount)
            combat.log.append(f"Osty is summoned for {gained}.")
        countdown = combat.player_statuses.get("countdown", 0)
        if countdown > 0:
            alive = [enemy for enemy in combat.enemies if enemy.hp > 0]
            if alive:
                target = self.rng.choice(alive)
                combat.log.extend(
                    self._apply_status_from_action(
                        run,
                        combat,
                        target="enemy",
                        status="doom",
                        value=countdown,
                        target_enemy=target,
                    )
                )
        friendship = combat.player_statuses.get("friendship", 0)
        if friendship > 0:
            combat.energy += friendship
            combat.log.append(f"Friendship grants {friendship} Energy.")
        demesne = combat.player_statuses.get("demesne", 0)
        if demesne > 0:
            combat.energy += demesne
            self._draw_cards(run, combat, demesne)
            combat.log.append(f"Demesne grants {demesne} Energy and draws {demesne} card(s).")
        call_of_the_void = combat.player_statuses.get("call_of_the_void", 0)
        for _ in range(call_of_the_void):
            candidates = list(CHARACTER_LIBRARY[run.character]["card_pool"])
            if not candidates:
                break
            card = self.create_card_instance(run, self.rng.choice(candidates))
            combat.hand.append(card)
            granted = self._meta_id_set(combat, "granted_ethereal")
            granted.add(card.instance_id)
            self._store_meta_id_set(combat, "granted_ethereal", granted)
            combat.log.append(f"{self.card_name(card)} is added to your hand and gains Ethereal.")
        sentry_mode = combat.player_statuses.get("sentry_mode", 0)
        for _ in range(sentry_mode):
            combat.log.extend(
                self._create_cards_in_combat(
                    run,
                    combat,
                    key="sweeping_gaze",
                    location="hand",
                    count=1,
                    upgraded=sentry_mode > 1,
                )
            )
        self_doom = combat.player_statuses.get("neurosurge", 0)
        if self_doom > 0:
            _, messages = self._apply_status_to_player(combat, "doom", self_doom)
            combat.log.extend(messages)

    def _resolve_player_doom(self, run: RunState, combat: CombatState) -> bool:
        doom = combat.player_statuses.get("doom", 0)
        if doom <= 0 or doom < run.hp:
            return False
        run.hp = 0
        combat.log.append("Doom consumes you.")
        return True

    def _resolve_enemy_doom(self, run: RunState, combat: CombatState, enemy: EnemyState, messages: list[str]) -> bool:
        doom = enemy.statuses.get("doom", 0)
        if enemy.hp <= 0 or doom <= 0 or doom < enemy.hp:
            return False
        enemy.hp = 0
        enemy.meta["death_by_doom"] = 1
        messages.append(f"{enemy.name} is consumed by Doom.")
        messages.extend(self._handle_enemy_damage_trigger(run, combat, enemy, 0))
        combat.enemies = self._prune_enemies(combat.enemies)
        return True

    def _find_card_in_combat(
        self,
        combat: CombatState,
        instance_id: str,
    ) -> CardInstance | None:
        for pile in (
            combat.hand,
            combat.draw_pile,
            combat.discard_pile,
            combat.exhaust_pile,
        ):
            found = self._find_card(pile, instance_id)
            if found is not None:
                return found
        return None

    def _grant_free_plays(
        self,
        combat: CombatState,
        instance_id: str,
        count: int = 1,
    ) -> None:
        free_plays = {
            str(key): int(value)
            for key, value in dict(combat.player_meta.get("free_play_counts", {})).items()
        }
        free_plays[instance_id] = free_plays.get(instance_id, 0) + count
        combat.player_meta["free_play_counts"] = free_plays

    def _consume_free_play(
        self,
        combat: CombatState,
        instance_id: str,
    ) -> None:
        free_plays = {
            str(key): int(value)
            for key, value in dict(combat.player_meta.get("free_play_counts", {})).items()
        }
        remaining = free_plays.get(instance_id, 0) - 1
        if remaining > 0:
            free_plays[instance_id] = remaining
        else:
            free_plays.pop(instance_id, None)
        if free_plays:
            combat.player_meta["free_play_counts"] = free_plays
        else:
            combat.player_meta.pop("free_play_counts", None)

    def _choose_highest_cost_card(
        self,
        cards: list[CardInstance],
        combat: CombatState,
        *,
        playable_only: bool = False,
    ) -> CardInstance | None:
        candidates = [
            card
            for card in cards
            if not playable_only or CARD_LIBRARY[card.key].playable
        ]
        if not candidates:
            return None
        candidates.sort(
            key=lambda card: (
                self.card_cost(card, combat) if self.card_cost(card, combat) >= 0 else combat.energy,
                1 if CARD_LIBRARY[card.key].card_type == "power" else 0,
                1 if card.upgraded else 0,
            ),
            reverse=True,
        )
        return candidates[0]

    def _gain_player_block(
        self,
        run: RunState | None,
        combat: CombatState,
        amount: int,
        messages: list[str],
        *,
        already_scaled: bool = False,
        message: str | None = None,
    ) -> int:
        gained = amount if already_scaled else self._compute_block_gain(amount, combat.player_statuses)
        if gained <= 0:
            return 0
        combat.player_block += gained
        messages.append(message.format(gained=gained) if message is not None else f"You gain {gained} Block.")
        wave = combat.player_statuses.get("wave_of_the_hand", 0)
        if wave > 0:
            for enemy in combat.enemies:
                _, weak_messages = self._apply_status_to_enemy(enemy, "weak", wave)
                messages.extend(weak_messages)
        return gained

    def card_cost(self, card: CardInstance, combat: CombatState | None = None) -> int:
        card_def = CARD_LIBRARY[card.key]
        if combat is not None and card_def.card_type == "curse" and combat.player_statuses.get("blue_candle", 0) > 0:
            return 0
        if combat is not None and card_def.card_type == "status" and combat.player_statuses.get("medical_kit", 0) > 0:
            return 0
        if card.upgraded and card_def.upgraded_cost is not None:
            cost = card_def.upgraded_cost
        else:
            cost = card_def.cost
        if (
            combat is not None
            and cost >= 0
            and int(dict(combat.player_meta.get("free_play_counts", {})).get(card.instance_id, 0)) > 0
        ):
            return 0
        if cost >= 0:
            cost = max(0, cost + card.cost_adjustment)
        if combat is not None and combat.player_statuses.get("bullet_time", 0) > 0:
            return 0
        if combat is not None and card_def.card_type == "skill" and combat.player_statuses.get("corruption", 0) > 0:
            return 0
        if (
            combat is not None
            and card_def.card_type == "attack"
            and combat.player_statuses.get("swivel", 0) > 0
            and cost >= 0
        ):
            return 0
        if combat is not None and card.key == "flatten":
            if int(combat.player_meta.get("osty_attacks_turn", 0)) > 0:
                return 0
        if combat is not None and card.key == "banshees_cry" and cost >= 0:
            cost = max(0, cost - (2 * combat.player_statuses.get("ethereal_played_combat", 0)))
        if combat is not None and self.card_is_ethereal(card, combat) and combat.player_statuses.get("next_ethereal_free", 0) > 0:
            return 0
        if combat is not None and card.key == "force_field" and cost >= 0:
            cost = max(0, cost - combat.player_statuses.get("powers_played_combat", 0))
        return cost

    def card_cost_label(self, card: CardInstance, combat: CombatState | None = None) -> str:
        if combat is not None and CARD_LIBRARY[card.key].card_type == "curse" and combat.player_statuses.get("blue_candle", 0) > 0:
            return "HP"
        cost = self.card_cost(card, combat)
        return "X" if cost < 0 else str(cost)

    def card_is_playable(
        self,
        run: RunState,
        card: CardInstance,
        combat: CombatState | None = None,
    ) -> bool:
        card_def = CARD_LIBRARY[card.key]
        if card_def.playable:
            return True
        return (
            combat is not None
            and (
                (card_def.card_type == "curse" and "blue_candle" in run.relics)
                or (card_def.card_type == "status" and "medical_kit" in run.relics)
            )
        )

    def card_description(self, card: CardInstance) -> str:
        card_def = CARD_LIBRARY[card.key]
        if card.upgraded and card_def.upgraded_description:
            return card_def.upgraded_description
        return card_def.description

    def card_damage_value(self, card: CardInstance) -> int:
        actions = self._actions_for_card(card)
        values = [
            int(action.get("value", 0))
            for action in actions
            if action.get("type") in {"attack", "attack_all"}
        ]
        return max(values) if values else 0

    def card_exhausts(self, card: CardInstance, combat: CombatState | None = None) -> bool:
        card_def = CARD_LIBRARY[card.key]
        if card.upgraded and card_def.upgraded_exhaust is not None:
            exhausts = card_def.upgraded_exhaust
        else:
            exhausts = card_def.exhaust
        if combat is not None and card_def.card_type == "status" and combat.player_statuses.get("medical_kit", 0) > 0:
            return True
        if combat is not None and card_def.card_type == "skill" and combat.player_statuses.get("corruption", 0) > 0:
            return True
        return exhausts

    def floor_limit_reached(self, run: RunState) -> bool:
        return run.act > 4 or run.floor >= self.MAX_FLOORS

    def has_key(self, run: RunState, key: str) -> bool:
        return key in run.keys

    def has_all_keys(self, run: RunState) -> bool:
        return all(key in run.keys for key in ("ruby", "emerald", "sapphire"))

    def _resolve_player_action(
        self,
        run: RunState,
        combat: CombatState,
        action: dict[str, object],
        *,
        target_enemy: EnemyState | None = None,
        from_potion: bool = False,
        spent_energy: int = 0,
    ) -> list[str]:
        action_type = str(action["type"])
        messages: list[str] = []

        if action_type == "attack":
            target = target_enemy or self._default_target_enemy(combat)
            if target is None:
                return messages
            hits = int(action.get("hits", 1))
            for _ in range(hits):
                base_damage = int(action["value"])
                if combat.active_card_key == "shiv":
                    base_damage += combat.player_statuses.get("shiv_bonus", 0)
                damage = self._compute_player_attack_damage(
                    combat,
                    base_damage,
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
                    break
                if run.hp <= 0:
                    break
        elif action_type == "attack_all":
            hits = int(action.get("hits", 1))
            for enemy in list(combat.enemies):
                for _ in range(hits):
                    damage = self._compute_player_attack_damage(
                        combat,
                        int(action["value"]),
                        combat.player_statuses,
                        enemy.statuses,
                    )
                    dealt, extra_messages = self._resolve_player_attack_hit(
                        run,
                        combat,
                        enemy,
                        damage,
                        triggers_thorns=not from_potion,
                    )
                    messages.append(f"{enemy.name} takes {dealt} damage.")
                    messages.extend(extra_messages)
                    if enemy.hp <= 0:
                        messages.append(f"{enemy.name} is defeated.")
                        break
                    if run.hp <= 0:
                        break
                if run.hp <= 0:
                    break
            combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "block":
            self._gain_player_block(run, combat, int(action["value"]), messages)
        elif action_type == "scry":
            self._scry(run, combat, int(action["value"]), messages=messages)
        elif action_type == "block_per_hand_size":
            self._gain_player_block(
                run,
                combat,
                len(combat.hand) * int(action["value"]),
                messages,
            )
        elif action_type == "draw":
            self._draw_cards(run, combat, int(action["value"]))
            messages.append(f"You draw {int(action['value'])} card(s).")
        elif action_type == "draw_up_to":
            limit = int(action["limit"])
            amount = max(0, limit - len(combat.hand))
            if amount > 0:
                self._draw_cards(run, combat, amount)
            messages.append(f"You draw {amount} card(s).")
        elif action_type == "gain_energy":
            combat.energy += int(action["value"])
            messages.append(f"You gain {int(action['value'])} Energy.")
        elif action_type == "gain_gold":
            amount = int(action["value"])
            gained = self._gain_gold(run, amount)
            if gained > 0:
                messages.append(f"You gain {gained} gold.")
            else:
                messages.append("Ectoplasm prevents you from gaining gold.")
        elif action_type == "gain_energy_from_draw_pile":
            gained = len(combat.draw_pile) // max(1, int(action.get("divisor", 4)))
            combat.energy += gained
            messages.append(f"You gain {gained} Energy.")
        elif action_type == "double_energy":
            gained = combat.energy + int(action.get("value", 0))
            combat.energy += gained
            messages.append(f"You gain {gained} Energy.")
        elif action_type == "lose_hp":
            value = int(action["value"])
            old_hp = run.hp
            run.hp = max(1, run.hp - value)
            messages.append(f"You lose {old_hp - run.hp} HP.")
            self._trigger_combat_hp_loss_relics(run, combat, old_hp - run.hp, messages)
        elif action_type == "apply_status":
            target = str(action["target"])
            status = str(action["status"])
            value = int(action["value"])
            messages.extend(
                self._apply_status_from_action(
                    run,
                    combat,
                    target=target,
                    status=status,
                    value=value,
                    target_enemy=target_enemy,
                )
            )
        elif action_type == "apply_status_if_last_skill":
            if combat.player_statuses.get("last_card_skill", 0) > 0:
                messages.extend(
                    self._apply_status_from_action(
                        run,
                        combat,
                        target="enemy",
                        status=str(action["status"]),
                        value=int(action["value"]),
                        target_enemy=target_enemy,
                    )
                )
        elif action_type == "mark":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                target.statuses["mark"] = target.statuses.get("mark", 0) + int(action["value"])
                messages.append(f"{target.name} gains {int(action['value'])} Mark.")
        elif action_type == "modify_status":
            target = str(action["target"])
            status = str(action["status"])
            value = int(action["value"])
            temporary = bool(action.get("temporary", False))
            if target == "enemy":
                enemy = target_enemy or self._default_target_enemy(combat)
                if enemy is not None:
                    delta, blocked = self._modify_status(
                        enemy.statuses,
                        status,
                        value,
                        use_artifact=True,
                        temporary=temporary,
                    )
                    if blocked:
                        messages.append(f"{enemy.name}'s Artifact negates {self._status_label(status)}.")
                    elif delta != 0:
                        verb = "gains" if delta > 0 else "loses"
                        messages.append(f"{enemy.name} {verb} {abs(delta)} {self._status_label(status)}.")
            elif target == "all_enemies":
                for enemy in combat.enemies:
                    delta, blocked = self._modify_status(
                        enemy.statuses,
                        status,
                        value,
                        use_artifact=True,
                        temporary=temporary,
                    )
                    if blocked:
                        messages.append(f"{enemy.name}'s Artifact negates {self._status_label(status)}.")
                    elif delta != 0:
                        verb = "gains" if delta > 0 else "loses"
                        messages.append(f"{enemy.name} {verb} {abs(delta)} {self._status_label(status)}.")
            elif target in {"self", "player"}:
                delta, blocked = self._modify_status(
                    combat.player_statuses,
                    status,
                    value,
                    use_artifact=True,
                    temporary=temporary,
                )
                if blocked:
                    messages.append(f"Artifact negates {self._status_label(status)}.")
                elif delta != 0:
                    verb = "gain" if delta > 0 else "lose"
                    messages.append(f"You {verb} {abs(delta)} {self._status_label(status)}.")
        elif action_type == "random_enemy_status":
            hits = int(action.get("hits", 1))
            status = str(action["status"])
            value = int(action["value"])
            for _ in range(hits):
                alive = [enemy for enemy in combat.enemies if enemy.hp > 0]
                if not alive:
                    break
                enemy = self.rng.choice(alive)
                applied, status_messages = self._apply_status_to_enemy(enemy, status, value)
                messages.extend(status_messages)
        elif action_type == "multiply_status":
            status = str(action["status"])
            factor = int(action["factor"])
            target = str(action["target"])
            messages.extend(
                self._multiply_status(
                    combat,
                    target=target,
                    status=status,
                    factor=factor,
                    target_enemy=target_enemy,
                )
            )
        elif action_type == "create_card":
            messages.extend(
                self._create_cards_in_combat(
                    run,
                    combat,
                    key=str(action["key"]),
                    location=str(action["location"]),
                    count=int(action.get("count", 1)),
                    upgraded=bool(action.get("upgraded", False)),
                )
            )
        elif action_type == "summon_osty":
            gained = self._summon_osty(combat, int(action["value"]))
            messages.append(f"Osty gains {gained} HP.")
        elif action_type == "summon_osty_next_turn":
            combat.player_statuses["next_turn_summon"] = (
                combat.player_statuses.get("next_turn_summon", 0) + int(action["value"])
            )
            messages.append(f"Osty will be summoned for {int(action['value'])} next turn.")
        elif action_type == "osty_attack":
            target = target_enemy or self._default_target_enemy(combat)
            hits = int(action.get("hits", 1))
            for _ in range(hits):
                messages.extend(self._osty_attack_target(run, combat, target, int(action["value"])))
                if target is not None and target.hp <= 0:
                    break
        elif action_type == "osty_attack_random":
            alive = [enemy for enemy in combat.enemies if enemy.hp > 0]
            if alive:
                messages.extend(
                    self._osty_attack_target(
                        run,
                        combat,
                        self.rng.choice(alive),
                        int(action["value"]),
                    )
                )
            elif not self._osty_alive(combat):
                messages.append("Osty is not alive.")
        elif action_type == "osty_attack_all":
            messages.extend(self._osty_attack_all_targets(run, combat, int(action["value"])))
        elif action_type == "kill_osty":
            if self._osty_alive(combat):
                self._damage_osty(run, combat, self._osty_hp(combat), messages)
        elif action_type == "unleash_attack":
            target = target_enemy or self._default_target_enemy(combat)
            bonus = self._osty_hp(combat)
            messages.extend(self._osty_attack_target(run, combat, target, int(action["value"]) + bonus))
        elif action_type == "blight_strike":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                damage = self._compute_player_attack_damage(
                    combat,
                    int(action["value"]),
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                if dealt > 0 and target.hp > 0:
                    messages.extend(
                        self._apply_status_from_action(
                            run,
                            combat,
                            target="enemy",
                            status="doom",
                            value=dealt,
                            target_enemy=target,
                        )
                    )
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "debilitate":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                damage = self._compute_player_attack_damage(
                    combat,
                    int(action["value"]),
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                if target.hp > 0:
                    messages.extend(
                        self._apply_status_from_action(
                            run,
                            combat,
                            target="enemy",
                            status="debilitate",
                            value=int(action.get("turns", 3)),
                            target_enemy=target,
                        )
                    )
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "return_discard_to_hand":
            for _ in range(int(action.get("count", 1))):
                chosen = self._choose_highest_cost_card(combat.discard_pile, combat)
                if chosen is None:
                    break
                combat.discard_pile.remove(chosen)
                combat.hand.append(chosen)
                messages.append(f"{self.card_name(chosen)} returns to your hand.")
        elif action_type == "add_retain_to_hand":
            chosen = self._choose_highest_cost_card(combat.hand, combat)
            if chosen is not None:
                granted = self._meta_id_set(combat, "granted_retain")
                granted.add(chosen.instance_id)
                self._store_meta_id_set(combat, "granted_retain", granted)
                messages.append(f"{self.card_name(chosen)} gains Retain.")
        elif action_type == "add_ethereal_to_hand":
            chosen = self._choose_highest_cost_card(combat.hand, combat)
            if chosen is not None:
                granted = self._meta_id_set(combat, "granted_ethereal")
                granted.add(chosen.instance_id)
                self._store_meta_id_set(combat, "granted_ethereal", granted)
                messages.append(f"{self.card_name(chosen)} gains Ethereal.")
        elif action_type == "exhaust_from_draw":
            for _ in range(int(action.get("count", 1))):
                if not combat.draw_pile:
                    break
                chosen = combat.draw_pile.pop()
                messages.extend(self._exhaust_card(run, combat, chosen))
        elif action_type == "lose_enemy_hp":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                lost = min(target.hp, int(action["value"]))
                target.hp = max(0, target.hp - lost)
                messages.append(f"{target.name} loses {lost} HP.")
                if target.hp <= 0:
                    messages.extend(self._handle_enemy_damage_trigger(run, combat, target, lost))
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "dirge":
            repeats = spent_energy
            summon_value = int(action["value"])
            if repeats > 0:
                gained = self._summon_osty(combat, summon_value * repeats)
                messages.append(f"Dirge summons {gained}.")
                messages.extend(
                    self._create_cards_in_combat(
                        run,
                        combat,
                        key="soul",
                        location="draw",
                        count=repeats,
                        upgraded=bool(action.get("upgraded_souls", False)),
                    )
                )
        elif action_type == "if_first_play_draw":
            played_counts = {
                str(key): int(value)
                for key, value in dict(combat.player_meta.get("played_card_keys_turn", {})).items()
            }
            if played_counts.get(str(combat.active_card_key), 0) == 1:
                self._draw_cards(run, combat, int(action["value"]))
                messages.append(f"You draw {int(action['value'])} card(s).")
        elif action_type == "no_escape":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                existing = target.statuses.get("doom", 0)
                extra = (existing // max(1, int(action.get("divisor", 10)))) * int(action.get("step", 5))
                messages.extend(
                    self._apply_status_from_action(
                        run,
                        combat,
                        target="enemy",
                        status="doom",
                        value=int(action["value"]) + extra,
                        target_enemy=target,
                    )
                )
        elif action_type == "protector_attack":
            target = target_enemy or self._default_target_enemy(combat)
            bonus = self._osty_max_hp(combat)
            messages.extend(
                self._osty_attack_target(
                    run,
                    combat,
                    target,
                    int(action["value"]) + bonus,
                )
            )
        elif action_type == "pull_from_below":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                ethereal_count = combat.player_statuses.get("ethereal_played_combat", 0)
                damage = self._compute_player_attack_damage(
                    combat,
                    int(action["value"]) * ethereal_count,
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "hang_attack":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                multiplier = max(1, int(target.meta.get("hang_multiplier", 1)))
                damage = self._compute_player_attack_damage(
                    combat,
                    int(action["value"]) * multiplier,
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                target.meta["hang_multiplier"] = multiplier * 2
                messages.append(f"Hang damage against {target.name} doubles.")
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "misery":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                copied_debuffs = {
                    status: value
                    for status, value in target.statuses.items()
                    if value > 0 and self._status_is_debuff(status)
                }
                damage = self._compute_player_attack_damage(
                    combat,
                    int(action["value"]),
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                for enemy in combat.enemies:
                    if enemy.enemy_id == target.enemy_id or enemy.hp <= 0:
                        continue
                    for status, value in copied_debuffs.items():
                        applied, status_messages = self._apply_status_to_enemy(enemy, status, value)
                        if applied > 0:
                            messages.append(f"Misery spreads {applied} {self._status_label(status)} to {enemy.name}.")
                        else:
                            messages.extend(status_messages)
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "rattle":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None and self._osty_alive(combat):
                extra_hits = int(combat.player_meta.get("osty_attacks_turn", 0))
                self._record_osty_attack(run, combat, messages)
                for _ in range(1 + extra_hits):
                    messages.extend(self._osty_hit_enemy(run, combat, target, int(action["value"])))
                    if target.hp <= 0:
                        messages.append(f"{target.name} is defeated.")
                        combat.enemies = self._prune_enemies(combat.enemies)
                        break
        elif action_type == "sic_em":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                sic_em_targets = {
                    str(key): int(value)
                    for key, value in dict(combat.player_meta.get("sic_em_targets", {})).items()
                }
                sic_em_targets[target.enemy_id] = int(action["summon"])
                combat.player_meta["sic_em_targets"] = sic_em_targets
                messages.extend(self._osty_attack_target(run, combat, target, int(action["value"])))
        elif action_type == "severance":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                damage = self._compute_player_attack_damage(
                    combat,
                    int(action["value"]),
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                messages.extend(self._create_cards_in_combat(run, combat, key="soul", location="draw", count=1))
                messages.extend(self._create_cards_in_combat(run, combat, key="soul", location="hand", count=1))
                messages.extend(self._create_cards_in_combat(run, combat, key="soul", location="discard", count=1))
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "osty_heal":
            healed = self._heal_osty(combat, int(action["value"]))
            messages.append(f"Osty heals {healed} HP.")
        elif action_type == "call_of_the_void":
            combat.player_statuses["call_of_the_void"] = combat.player_statuses.get("call_of_the_void", 0) + 1
            messages.append("Call Of The Void begins whispering.")
        elif action_type == "forbidden_grimoire":
            combat.player_statuses["forbidden_grimoire"] = combat.player_statuses.get("forbidden_grimoire", 0) + 1
            messages.append("Forbidden Grimoire will let you remove a card after combat.")
        elif action_type == "exhaust_hand_threshold_intangible":
            victims = list(combat.hand)
            combat.hand = []
            for victim in victims:
                messages.extend(self._exhaust_card(run, combat, victim))
            if len(victims) >= int(action.get("threshold", 9)):
                messages.extend(
                    self._apply_status_from_action(
                        run,
                        combat,
                        target="self",
                        status="intangible",
                        value=int(action.get("intangible", 1)),
                    )
                )
        elif action_type == "end_of_days":
            messages.extend(self._apply_status_from_action(run, combat, target="all_enemies", status="doom", value=int(action["value"])))
            for enemy in list(combat.enemies):
                self._resolve_enemy_doom(run, combat, enemy, messages)
        elif action_type == "transform_draw_to_soul":
            chosen = self._choose_highest_cost_card(combat.draw_pile, combat)
            if chosen is not None:
                combat.draw_pile.remove(chosen)
                combat.draw_pile.append(self.create_card_instance(run, "soul", upgraded=bool(action.get("upgraded", False))))
                messages.append(f"{self.card_name(chosen)} becomes Soul.")
        elif action_type == "soul_storm":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                soul_count = sum(1 for card in combat.exhaust_pile if card.key == "soul")
                damage = self._compute_player_attack_damage(
                    combat,
                    int(action["value"]) + (soul_count * int(action.get("per_soul", 2))),
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "squeeze":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None and self._osty_alive(combat):
                bonus = max(0, int(combat.player_meta.get("osty_attacks_combat", 0))) * int(action.get("per_attack", 5))
                self._record_osty_attack(run, combat, messages)
                messages.extend(self._osty_hit_enemy(run, combat, target, int(action["value"]) + bonus))
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "scythe_attack":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                active_misc = int(combat.player_meta.get("active_card_misc", 0))
                damage = self._compute_player_attack_damage(
                    combat,
                    int(action["value"]) + active_misc,
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                growth = int(action.get("growth", 3))
                active_id = str(combat.player_meta.get("active_card_instance_id", ""))
                persistent = self._find_card(run.deck, active_id)
                if persistent is not None:
                    persistent.misc += growth
                    combat.player_meta["active_card_misc"] = persistent.misc
                else:
                    combat.player_meta["active_card_misc"] = active_misc + growth
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "transfigure":
            chosen = self._choose_highest_cost_card(combat.hand, combat)
            if chosen is not None:
                chosen.cost_adjustment += int(action.get("extra_cost", 1))
                replay_counts = {
                    str(key): int(value)
                    for key, value in dict(combat.player_meta.get("replay_counts", {})).items()
                }
                replay_counts[chosen.instance_id] = replay_counts.get(chosen.instance_id, 0) + 1
                combat.player_meta["replay_counts"] = replay_counts
                messages.append(f"{self.card_name(chosen)} gains Replay and costs 1 more.")
        elif action_type == "create_self_copy":
            active_key = str(combat.active_card_key or "")
            if active_key:
                duplicate = self.create_card_instance(
                    run,
                    active_key,
                    upgraded=bool(combat.player_meta.get("active_card_upgraded", False)),
                    misc=int(combat.player_meta.get("active_card_misc", 0)),
                )
                if str(action.get("location", "discard")) == "hand":
                    combat.hand.append(duplicate)
                else:
                    combat.discard_pile.append(duplicate)
                messages.append(f"{self.card_name(duplicate)} is copied.")
        elif action_type == "upgrade_random_discard":
            candidates = [card for card in combat.discard_pile if not card.upgraded]
            self.rng.shuffle(candidates)
            for chosen in candidates[: int(action.get("count", 1))]:
                chosen.upgraded = True
                messages.append(f"{self.card_name(chosen)} is upgraded.")
        elif action_type == "death_march":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                damage = self._compute_player_attack_damage(
                    combat,
                    int(action["value"]) + (combat.player_meta.get("cards_drawn_turn", 0) * int(action.get("per_draw", 3))),
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "attack_enemy_doom":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                dealt, extra_messages = self._deal_damage_to_enemy(run, combat, target, target.statuses.get("doom", 0))
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "sacrifice_osty":
            if self._osty_alive(combat):
                gain = self._osty_max_hp(combat) * 2
                self._damage_osty(run, combat, self._osty_hp(combat), messages, source="Sacrifice.")
                self._gain_player_block(run, combat, gain, messages)
        elif action_type == "genetic_algorithm":
            active_misc = int(combat.player_meta.get("active_card_misc", 0))
            self._gain_player_block(
                run,
                combat,
                int(action["value"]) + active_misc,
                messages,
            )
            active_id = str(combat.player_meta.get("active_card_instance_id", ""))
            persistent = self._find_card(run.deck, active_id)
            growth = int(action.get("gain", 2))
            if persistent is not None:
                persistent.misc += growth
                combat.player_meta["active_card_misc"] = persistent.misc
            else:
                combat.player_meta["active_card_misc"] = active_misc + growth
            messages.append(f"Genetic Algorithm permanently gains {growth} Block.")
        elif action_type == "create_random_card":
            messages.extend(
                self._create_random_cards_in_combat(
                    run,
                    combat,
                    pool=str(action["pool"]),
                    location=str(action.get("location", "hand")),
                    count=int(action.get("count", 1)),
                    card_type=str(action["card_type"]) if action.get("card_type") else None,
                )
            )
        elif action_type == "x_create_random_card":
            messages.extend(
                self._create_random_cards_in_combat(
                    run,
                    combat,
                    pool=str(action["pool"]),
                    location=str(action.get("location", "hand")),
                    count=spent_energy,
                )
            )
        elif action_type == "metamorphosis":
            count = int(action.get("count", 3))
            excluded = {"feed", "lesson_learned", "reaper"}
            candidates = [
                key
                for key in CHARACTER_LIBRARY[run.character]["card_pool"]
                if CARD_LIBRARY[key].card_type == "attack" and key not in excluded
            ]
            for _ in range(count):
                if not candidates:
                    break
                key = self.rng.choice(candidates)
                upgraded = combat.player_statuses.get("master_reality", 0) > 0
                new_card = self.create_card_instance(run, key, upgraded=upgraded)
                self._set_card_cost(new_card, 0)
                combat.draw_pile.append(new_card)
                messages.append(f"{self.card_name(new_card)} is created in your draw.")
            if count > 0:
                self.rng.shuffle(combat.draw_pile)
        elif action_type == "setup_random_card":
            if combat.hand:
                chosen = self._choose_highest_cost_card(combat.hand, combat) or self.rng.choice(combat.hand)
                combat.hand.remove(chosen)
                combat.draw_pile.append(chosen)
                self._grant_free_plays(combat, chosen.instance_id)
                messages.append(f"{self.card_name(chosen)} is placed on top of your draw pile and now costs 0.")
        elif action_type == "nightmare_random":
            if combat.hand:
                chosen = self.rng.choice(combat.hand)
                queue = list(combat.player_meta.get("nightmare", []))
                queue.append(
                    {
                        "key": chosen.key,
                        "upgraded": chosen.upgraded,
                        "count": int(action.get("copies", 3)),
                    }
                )
                combat.player_meta["nightmare"] = queue
                messages.append(f"Nightmare will copy {self.card_name(chosen)} next turn.")
        elif action_type == "madness_random":
            if combat.hand:
                chosen = self.rng.choice(combat.hand)
                self._set_card_cost(chosen, 0)
                messages.append(f"Madness reduces {self.card_name(chosen)} to 0 cost.")
        elif action_type == "enlightenment":
            permanent = bool(action.get("permanent", False))
            temporary_costs = {
                str(key): int(value)
                for key, value in dict(combat.player_meta.get("temporary_costs", {})).items()
            }
            affected = 0
            for chosen in combat.hand:
                if self.card_cost(chosen, combat) > 1:
                    if not permanent and chosen.instance_id not in temporary_costs:
                        temporary_costs[chosen.instance_id] = chosen.cost_adjustment
                    self._set_card_cost(chosen, 1)
                    affected += 1
            if temporary_costs:
                combat.player_meta["temporary_costs"] = temporary_costs
            if affected > 0:
                duration = "this combat" if permanent else "this turn"
                messages.append(f"Enlightenment reduces {affected} card(s) to cost 1 {duration}.")
        elif action_type == "forethought":
            all_cards = bool(action.get("all_cards", False))
            if combat.hand:
                chosen_cards = sorted(
                    list(combat.hand),
                    key=lambda card: (
                        self.card_cost(card, combat) if self.card_cost(card, combat) >= 0 else combat.energy,
                        1 if CARD_LIBRARY[card.key].card_type == "power" else 0,
                    ),
                    reverse=True,
                )
                if all_cards:
                    chosen_cards = [card for card in chosen_cards if self.card_cost(card, combat) > 0]
                else:
                    chosen_cards = chosen_cards[: int(action.get("count", 1))]
                for chosen in chosen_cards:
                    if chosen not in combat.hand:
                        continue
                    combat.hand.remove(chosen)
                    combat.draw_pile.insert(0, chosen)
                    self._grant_free_plays(combat, chosen.instance_id)
                    messages.append(f"{self.card_name(chosen)} is tucked into your draw pile and will cost 0.")
        elif action_type == "thinking_ahead_random":
            self._draw_cards(run, combat, int(action.get("draw", 2)))
            messages.append(f"You draw {int(action.get('draw', 2))} card(s).")
            if combat.hand:
                chosen = self.rng.choice(combat.hand)
                combat.hand.remove(chosen)
                combat.draw_pile.append(chosen)
                messages.append(f"{self.card_name(chosen)} is returned to the top of your draw pile.")
        elif action_type == "the_bomb":
            bombs = list(combat.player_meta.get("bombs", []))
            bombs.append({"timer": int(action.get("timer", 3)), "damage": int(action.get("damage", 40))})
            combat.player_meta["bombs"] = bombs
            messages.append("The Bomb is set.")
        elif action_type == "add_random_potion":
            gained = self._grant_random_potions(run, int(action.get("count", 1)))
            if gained:
                messages.append(
                    "Potions gained: " + ", ".join(POTION_LIBRARY[key].name for key in gained)
                )
        elif action_type == "upgrade_all_cards":
            for card in run.deck:
                card.upgraded = True
            for pile in (combat.hand, combat.draw_pile, combat.discard_pile, combat.exhaust_pile):
                for card in pile:
                    card.upgraded = True
            messages.append("All cards are upgraded.")
        elif action_type == "temp_strength":
            value = int(action["value"])
            combat.player_statuses["strength"] = combat.player_statuses.get("strength", 0) + value
            combat.player_statuses["temp_strength_loss"] = (
                combat.player_statuses.get("temp_strength_loss", 0) + value
            )
            messages.append(f"You gain {value} Strength this turn.")
        elif action_type == "attack_bonus_if_enemy_status":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                base = int(action["value"])
                if target.statuses.get(str(action["status"]), 0) > 0:
                    base += int(action.get("bonus", 0))
                damage = self._compute_player_attack_damage(
                    combat,
                    base,
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "attack_per_status_count":
            target_mode = str(action.get("target", "enemy"))
            count = combat.player_statuses.get(str(action["status"]), 0)
            if target_mode == "all_enemies":
                for enemy in list(combat.enemies):
                    damage = self._compute_player_attack_damage(
                        combat,
                        int(action["value"]) * count,
                        combat.player_statuses,
                        enemy.statuses,
                    )
                    dealt, extra_messages = self._resolve_player_attack_hit(
                        run,
                        combat,
                        enemy,
                        damage,
                        triggers_thorns=not from_potion,
                    )
                    messages.append(f"{enemy.name} takes {dealt} damage.")
                    messages.extend(extra_messages)
                    if enemy.hp <= 0:
                        messages.append(f"{enemy.name} is defeated.")
                combat.enemies = self._prune_enemies(combat.enemies)
            else:
                target = target_enemy or self._default_target_enemy(combat)
                if target is not None:
                    damage = self._compute_player_attack_damage(
                        combat,
                        int(action["value"]) * count,
                        combat.player_statuses,
                        target.statuses,
                    )
                    dealt, extra_messages = self._resolve_player_attack_hit(
                        run,
                        combat,
                        target,
                        damage,
                        triggers_thorns=not from_potion,
                    )
                    messages.append(f"{target.name} takes {dealt} damage.")
                    messages.extend(extra_messages)
                    if target.hp <= 0:
                        messages.append(f"{target.name} is defeated.")
                        combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "attack_per_hand_type":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                count = sum(
                    1
                    for card in combat.hand
                    if CARD_LIBRARY[card.key].card_type == str(action["card_type"])
                )
                for _ in range(count):
                    damage = self._compute_player_attack_damage(
                        combat,
                        int(action["value"]),
                        combat.player_statuses,
                        target.statuses,
                    )
                    dealt, extra_messages = self._resolve_player_attack_hit(
                        run,
                        combat,
                        target,
                        damage,
                        triggers_thorns=not from_potion,
                    )
                    messages.append(f"{target.name} takes {dealt} damage.")
                    messages.extend(extra_messages)
                    if target.hp <= 0:
                        messages.append(f"{target.name} is defeated.")
                        combat.enemies = self._prune_enemies(combat.enemies)
                        break
        elif action_type == "attack_per_orb":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                for _ in range(len(combat.orbs)):
                    damage = self._compute_player_attack_damage(
                        combat,
                        int(action["value"]),
                        combat.player_statuses,
                        target.statuses,
                    )
                    dealt, extra_messages = self._resolve_player_attack_hit(
                        run,
                        combat,
                        target,
                        damage,
                        triggers_thorns=not from_potion,
                    )
                    messages.append(f"{target.name} takes {dealt} damage.")
                    messages.extend(extra_messages)
                    if target.hp <= 0:
                        messages.append(f"{target.name} is defeated.")
                        combat.enemies = self._prune_enemies(combat.enemies)
                        break
        elif action_type == "attack_per_enemy":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                damage = self._compute_player_attack_damage(
                    combat,
                    int(action["value"]) * len([enemy for enemy in combat.enemies if enemy.hp > 0]),
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "attack_if_draw_pile_empty":
            if combat.draw_pile:
                messages.append("Your draw pile is not empty.")
            else:
                target_mode = str(action.get("target", "all_enemies"))
                if target_mode == "all_enemies":
                    for enemy in list(combat.enemies):
                        damage = self._compute_player_attack_damage(
                            combat,
                            int(action["value"]),
                            combat.player_statuses,
                            enemy.statuses,
                        )
                        dealt, extra_messages = self._resolve_player_attack_hit(
                            run,
                            combat,
                            enemy,
                            damage,
                            triggers_thorns=not from_potion,
                        )
                        messages.append(f"{enemy.name} takes {dealt} damage.")
                        messages.extend(extra_messages)
                        if enemy.hp <= 0:
                            messages.append(f"{enemy.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "body_slam":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                damage = self._compute_player_attack_damage(
                    combat,
                    combat.player_block,
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"Body Slam deals {dealt} damage.")
                messages.extend(extra_messages)
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "exhaust_random":
            count = min(int(action["value"]), len(combat.hand))
            for _ in range(count):
                victim = self.rng.choice(combat.hand)
                combat.hand.remove(victim)
                messages.extend(self._exhaust_card(run, combat, victim))
        elif action_type == "discard_random":
            messages.extend(self._discard_random_cards(combat, int(action["value"]), run=run))
        elif action_type == "discard_hand_draw_same":
            count = len(combat.hand)
            while combat.hand:
                victim = combat.hand.pop()
                messages.extend(self._discard_card(run, combat, victim))
            self._draw_cards(run, combat, count)
            messages.append(f"You draw {count} card(s).")
        elif action_type == "discard_hand_draw_count":
            while combat.hand:
                victim = combat.hand.pop()
                messages.extend(self._discard_card(run, combat, victim))
            draw_count = int(action["draw"])
            self._draw_cards(run, combat, draw_count)
            messages.append(f"You draw {draw_count} card(s).")
        elif action_type == "discard_for_energy":
            discard_count = int(action["discard_count"])
            messages.extend(self._discard_random_cards(combat, discard_count, run=run))
            combat.energy += int(action["energy"])
            messages.append(f"You gain {int(action['energy'])} Energy.")
        elif action_type == "discard_hand_create":
            count = len(combat.hand)
            while combat.hand:
                victim = combat.hand.pop()
                messages.extend(self._discard_card(run, combat, victim))
            if count > 0:
                messages.extend(
                    self._create_cards_in_combat(
                        run,
                        combat,
                        key=str(action["key"]),
                        location=str(action.get("location", "hand")),
                        count=count * int(action.get("count_per_card", 1)),
                        upgraded=bool(action.get("upgraded", False)),
                    )
                )
        elif action_type == "discard_hand":
            while combat.hand:
                victim = combat.hand.pop()
                messages.extend(self._discard_card(run, combat, victim))
        elif action_type == "recycle":
            chosen = self._choose_highest_cost_card(combat.hand, combat)
            if chosen is None:
                messages.append("No card can be recycled.")
            else:
                combat.hand.remove(chosen)
                gained = self.card_cost(chosen, combat)
                if gained < 0:
                    gained = combat.energy
                combat.energy += max(0, gained)
                messages.extend(self._exhaust_card(run, combat, chosen))
                messages.append(f"Recycle grants {max(0, gained)} Energy from {self.card_name(chosen)}.")
        elif action_type == "return_random_discard_to_hand":
            chosen = self._move_random_card_from_pile(combat.discard_pile, combat.hand)
            if chosen is not None:
                messages.append(f"{self.card_name(chosen)} returns to your hand.")
        elif action_type == "meditate_random":
            count = int(action.get("count", 1))
            retained_ids = list(combat.player_meta.get("temporary_retain", []))
            for _ in range(count):
                chosen = self._move_random_card_from_pile(combat.discard_pile, combat.hand)
                if chosen is not None:
                    retained_ids.append(chosen.instance_id)
                    messages.append(f"{self.card_name(chosen)} returns to your hand.")
            if retained_ids:
                combat.player_meta["temporary_retain"] = retained_ids
        elif action_type == "return_random_draw_to_hand":
            source = combat.draw_pile
            if action.get("card_type"):
                candidates = [
                    card for card in combat.draw_pile if CARD_LIBRARY[card.key].card_type == str(action["card_type"])
                ]
                if candidates:
                    chosen = self.rng.choice(candidates)
                    combat.draw_pile.remove(chosen)
                    combat.hand.append(chosen)
                    messages.append(f"{self.card_name(chosen)} is pulled into your hand.")
            else:
                chosen = self._move_random_card_from_pile(source, combat.hand)
                if chosen is not None:
                    messages.append(f"{self.card_name(chosen)} is pulled into your hand.")
        elif action_type == "shuffle_discard_draw":
            combat.draw_pile.extend(combat.discard_pile)
            combat.discard_pile = []
            self.rng.shuffle(combat.draw_pile)
            self._draw_cards(run, combat, int(action["draw"]))
            messages.append(f"You draw {int(action['draw'])} card(s).")
        elif action_type == "return_discard_to_draw":
            if combat.discard_pile:
                chosen = self.rng.choice(combat.discard_pile)
                combat.discard_pile.remove(chosen)
                combat.draw_pile.append(chosen)
                messages.append(f"{self.card_name(chosen)} is placed on top of your draw pile.")
        elif action_type == "channel_orb":
            count = int(action.get("count", 1))
            orb_name = str(action["orb"])
            for _ in range(count):
                evoke_messages = self._channel_orb(combat, orb_name)
                messages.extend(evoke_messages)
                messages.append(f"{orb_name.title()} orb is channeled.")
        elif action_type == "trigger_dark_passive":
            gain = max(0, 6 + combat.player_statuses.get("focus", 0))
            for index, orb in enumerate(list(combat.orbs)):
                if self._orb_kind(orb) == "dark":
                    value = self._orb_value(orb) + gain
                    self._set_orb_value(combat, index, "dark", value)
                    messages.append(f"Darkness empowers a Dark orb to {value} damage.")
        elif action_type == "channel_random_orb":
            count = int(action.get("count", 1))
            options = [str(entry) for entry in action.get("orbs", ["lightning", "frost"])]
            for _ in range(count):
                orb_name = self.rng.choice(options)
                evoke_messages = self._channel_orb(combat, orb_name)
                messages.extend(evoke_messages)
                messages.append(f"{orb_name.title()} orb is channeled.")
        elif action_type == "evoke_orb":
            count = int(action.get("count", 1))
            if count <= 0:
                return messages
            if count == 1:
                messages.extend(self._evoke_leftmost_orb(run, combat))
            elif combat.orbs:
                orb = combat.orbs.pop(0)
                for _ in range(count):
                    messages.extend(self._resolve_orb_evoke(run, combat, orb))
            else:
                messages.append("No orb is available to evoke.")
        elif action_type == "evoke_all_orbs":
            orb_count = len(combat.orbs)
            while combat.orbs:
                messages.extend(self._evoke_leftmost_orb(run, combat))
            draw_per_orb = int(action.get("draw_per_orb", 0))
            if draw_per_orb > 0 and orb_count > 0:
                total_draw = orb_count * draw_per_orb
                self._draw_cards(run, combat, total_draw)
                messages.append(f"You draw {total_draw} card(s).")
        elif action_type == "x_evoke_leftmost":
            if not combat.orbs:
                messages.append("No orb is available to evoke.")
            else:
                orb = combat.orbs.pop(0)
                for _ in range(spent_energy):
                    messages.extend(self._resolve_orb_evoke(run, combat, orb))
        elif action_type == "change_stance":
            new_stance = str(action["stance"])
            messages.append(self._change_stance(run, combat, new_stance))
        elif action_type == "exit_stance":
            messages.append(self._change_stance(run, combat, "neutral"))
        elif action_type == "gain_orb_slots":
            amount = int(action["value"])
            combat.orb_slots = max(0, combat.orb_slots + amount)
            while len(combat.orbs) > combat.orb_slots:
                combat.orbs.pop()
            if amount >= 0:
                messages.append(f"You gain {amount} Orb slot(s).")
            else:
                messages.append(f"You lose {abs(amount)} Orb slot(s).")
        elif action_type == "block_if_no_block":
            if combat.player_block <= 0:
                gained = self._compute_block_gain(int(action["value"]), combat.player_statuses)
                combat.player_block += gained
                messages.append(f"You gain {gained} Block.")
            else:
                messages.append("You already have Block.")
        elif action_type == "double_block":
            gained = combat.player_block
            combat.player_block += gained
            messages.append(f"Your Block doubles to {combat.player_block}.")
        elif action_type == "x_attack":
            base = int(action["value"])
            target_mode = str(action.get("target", "enemy"))
            if target_mode == "all_enemies":
                for enemy in list(combat.enemies):
                    for _ in range(spent_energy):
                        damage = self._compute_player_attack_damage(
                            combat,
                            base,
                            combat.player_statuses,
                            enemy.statuses,
                        )
                        dealt, extra_messages = self._resolve_player_attack_hit(
                            run,
                            combat,
                            enemy,
                            damage,
                            triggers_thorns=not from_potion,
                        )
                        messages.append(f"{enemy.name} takes {dealt} damage.")
                        messages.extend(extra_messages)
                        if enemy.hp <= 0:
                            messages.append(f"{enemy.name} is defeated.")
                            break
                        if run.hp <= 0:
                            break
                    if run.hp <= 0:
                        break
                combat.enemies = self._prune_enemies(combat.enemies)
            else:
                target = target_enemy or self._default_target_enemy(combat)
                if target is not None:
                    for _ in range(spent_energy):
                        damage = self._compute_player_attack_damage(
                            combat,
                            base,
                            combat.player_statuses,
                            target.statuses,
                        )
                        dealt, extra_messages = self._resolve_player_attack_hit(
                            run,
                            combat,
                            target,
                            damage,
                            triggers_thorns=not from_potion,
                        )
                        messages.append(f"{target.name} takes {dealt} damage.")
                        messages.extend(extra_messages)
                        if target.hp <= 0:
                            messages.append(f"{target.name} is defeated.")
                            combat.enemies = self._prune_enemies(combat.enemies)
                            break
                        if run.hp <= 0:
                            break
        elif action_type == "x_block":
            for _ in range(spent_energy):
                self._gain_player_block(run, combat, int(action["value"]), messages)
        elif action_type == "x_channel_orb":
            orb_name = str(action["orb"])
            for _ in range(spent_energy):
                evoke_messages = self._channel_orb(combat, orb_name)
                messages.extend(evoke_messages)
                messages.append(f"{orb_name.title()} orb is channeled.")
        elif action_type == "drain_all":
            total_heal = 0
            for enemy in list(combat.enemies):
                damage = self._compute_player_attack_damage(
                    combat,
                    int(action["value"]),
                    combat.player_statuses,
                    enemy.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    enemy,
                    damage,
                    triggers_thorns=not from_potion,
                )
                total_heal += dealt
                messages.append(f"{enemy.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                if enemy.hp <= 0:
                    messages.append(f"{enemy.name} is defeated.")
                if run.hp <= 0:
                    break
            combat.enemies = self._prune_enemies(combat.enemies)
            if total_heal > 0:
                healed = self._heal_run(run, total_heal)
                self._sync_player_hp_relics(run, combat, messages)
                messages.append(f"You heal {healed} HP.")
        elif action_type == "wallop":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                damage = self._compute_player_attack_damage(
                    combat,
                    int(action["value"]),
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                if dealt > 0:
                    self._gain_player_block(run, combat, dealt, messages, already_scaled=True)
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "feed":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                damage = self._compute_player_attack_damage(
                    combat,
                    int(action["value"]),
                    combat.player_statuses,
                    target.statuses,
                )
                was_alive = target.hp > 0
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                if was_alive and target.hp <= 0:
                    gain = int(action.get("max_hp_gain", 3))
                    self._increase_max_hp(run, gain)
                    self._sync_player_hp_relics(run, combat, messages)
                    messages.append(f"Feed raises your Max HP by {gain}.")
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "heal_player":
            healed = self._heal_run(run, int(action["value"]))
            self._sync_player_hp_relics(run, combat, messages)
            messages.append(f"You heal {healed} HP.")
        elif action_type == "heavy_blade":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                bonus_multiplier = int(action.get("multiplier", 3)) - 1
                base = int(action["value"]) + combat.player_statuses.get("strength", 0) * bonus_multiplier
                damage = self._compute_player_attack_damage(
                    combat,
                    base,
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "dropkick":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                vulnerable = target.statuses.get("vulnerable", 0) > 0
                damage = self._compute_player_attack_damage(
                    combat,
                    int(action["value"]),
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                if vulnerable:
                    combat.energy += int(action.get("energy", 1))
                    self._draw_cards(run, combat, int(action.get("draw", 1)))
                    messages.append(f"You gain {int(action.get('energy', 1))} Energy and draw {int(action.get('draw', 1))} card(s).")
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "sneaky_strike":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                damage = self._compute_player_attack_damage(
                    combat,
                    int(action["value"]),
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                if combat.player_statuses.get("cards_discarded_turn", 0) > 0:
                    combat.energy += int(action.get("energy", 2))
                    messages.append(f"You gain {int(action.get('energy', 2))} Energy.")
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "attack_random":
            hits = int(action.get("hits", 1))
            for _ in range(hits):
                alive = [enemy for enemy in combat.enemies if enemy.hp > 0]
                if not alive:
                    break
                target = self.rng.choice(alive)
                damage = self._compute_player_attack_damage(
                    combat,
                    int(action["value"]),
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
                if run.hp <= 0:
                    break
        elif action_type == "windmill_strike":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                damage = self._compute_player_attack_damage(
                    combat,
                    int(action["value"]) + int(combat.player_meta.get("active_card_misc", 0)),
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "brilliance":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                mantra_damage = combat.player_statuses.get("mantra_gained_combat", 0) * int(action.get("per_mantra", 4))
                damage = self._compute_player_attack_damage(
                    combat,
                    int(action["value"]) + mantra_damage,
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "expunger":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                hits = int(combat.player_meta.get("active_card_misc", 0))
                for _ in range(hits):
                    damage = self._compute_player_attack_damage(
                        combat,
                        int(action["value"]),
                        combat.player_statuses,
                        target.statuses,
                    )
                    dealt, extra_messages = self._resolve_player_attack_hit(
                        run,
                        combat,
                        target,
                        damage,
                        triggers_thorns=not from_potion,
                    )
                    messages.append(f"{target.name} takes {dealt} damage.")
                    messages.extend(extra_messages)
                    if target.hp <= 0:
                        messages.append(f"{target.name} is defeated.")
                        combat.enemies = self._prune_enemies(combat.enemies)
                        break
                    if run.hp <= 0:
                        break
        elif action_type == "attack_random_per_status_count":
            hits = combat.player_statuses.get(str(action["status"]), 0)
            for _ in range(hits):
                alive = [enemy for enemy in combat.enemies if enemy.hp > 0]
                if not alive:
                    break
                target = self.rng.choice(alive)
                damage = self._compute_player_attack_damage(
                    combat,
                    int(action["value"]),
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
                if run.hp <= 0:
                    break
        elif action_type == "draw_next_turn":
            combat.player_statuses["next_turn_draw"] = (
                combat.player_statuses.get("next_turn_draw", 0) + int(action["value"])
            )
            messages.append(f"You will draw {int(action['value'])} extra card(s) next turn.")
        elif action_type == "x_next_turn":
            draw_gain = spent_energy * int(action.get("draw_per_energy", 1)) + int(action.get("flat_bonus", 0))
            energy_gain = spent_energy * int(action.get("energy_per_energy", 1)) + int(action.get("flat_bonus", 0))
            if draw_gain > 0:
                combat.player_statuses["next_turn_draw"] = (
                    combat.player_statuses.get("next_turn_draw", 0) + draw_gain
                )
            if energy_gain > 0:
                combat.player_statuses["next_turn_energy"] = (
                    combat.player_statuses.get("next_turn_energy", 0) + energy_gain
                )
            messages.append("You prepare your next turn.")
        elif action_type == "x_malaise":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None and spent_energy > 0:
                weakened = spent_energy + int(action.get("extra_weak", 0))
                target.statuses["weak"] = target.statuses.get("weak", 0) + weakened
                self._modify_status(target.statuses, "strength", -spent_energy, use_artifact=True, temporary=True)
                messages.append(f"{target.name} is weakened and loses Strength.")
        elif action_type == "gain_energy_next_turn":
            combat.player_statuses["next_turn_energy"] = (
                combat.player_statuses.get("next_turn_energy", 0) + int(action["value"])
            )
            messages.append(f"You will gain {int(action['value'])} Energy next turn.")
        elif action_type == "gain_block_next_turn":
            combat.player_statuses["next_turn_block"] = (
                combat.player_statuses.get("next_turn_block", 0) + int(action["value"])
            )
            messages.append(f"You will gain {int(action['value'])} Block next turn.")
        elif action_type == "x_collect":
            turns = spent_energy + int(action.get("flat_bonus", 0))
            if turns > 0:
                combat.player_statuses["collect"] = combat.player_statuses.get("collect", 0) + turns
                messages.append(f"Collect will add Miracle+ for {turns} turn(s).")
        elif action_type == "conjure_blade":
            hits = spent_energy + int(action.get("bonus_hits", 0))
            messages.extend(
                self._create_cards_in_combat(
                    run,
                    combat,
                    key="expunger",
                    location="draw",
                    count=1,
                    misc=hits,
                )
            )
            self.rng.shuffle(combat.draw_pile)
        elif action_type == "channel_per_enemy":
            alive = [enemy for enemy in combat.enemies if enemy.hp > 0]
            copies = max(1, len(alive)) * int(action.get("count", 1))
            orb_name = str(action["orb"])
            for _ in range(copies):
                evoke_messages = self._channel_orb(combat, orb_name)
                messages.extend(evoke_messages)
                messages.append(f"{orb_name.title()} orb is channeled.")
        elif action_type == "draw_per_orb_types":
            draw_count = len(set(combat.orbs))
            if draw_count > 0:
                self._draw_cards(run, combat, draw_count)
            messages.append(f"You draw {draw_count} card(s).")
        elif action_type == "draw_if_stance":
            if combat.stance == str(action["stance"]):
                self._draw_cards(run, combat, int(action["value"]))
                messages.append(f"You draw {int(action['value'])} card(s).")
        elif action_type == "perseverance":
            self._gain_player_block(
                run,
                combat,
                int(action["value"]) + int(combat.player_meta.get("active_card_misc", 0)),
                messages,
            )
        elif action_type == "draw_if_no_attacks":
            if not any(CARD_LIBRARY[card.key].card_type == "attack" for card in combat.hand):
                self._draw_cards(run, combat, int(action["value"]))
                messages.append(f"You draw {int(action['value'])} card(s).")
        elif action_type == "force_end_turn":
            combat.player_meta["force_end_turn"] = True
        elif action_type == "remove_block_attack":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                target.block = 0
                damage = self._compute_player_attack_damage(
                    combat,
                    int(action["value"]),
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "judgment":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                threshold = int(action["value"])
                if target.hp <= threshold:
                    target.hp = 0
                    messages.append(f"{target.name} is judged and dies.")
                    messages.extend(self._handle_enemy_damage_trigger(run, combat, target, threshold))
                    combat.enemies = self._prune_enemies(combat.enemies)
                else:
                    messages.append(f"{target.name} resists Judgment.")
        elif action_type == "attack_mark":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                marked = target.statuses.get("mark", 0)
                dealt, extra_messages = self._deal_damage_to_enemy(run, combat, target, marked)
                messages.append(f"{target.name} takes {dealt} damage from Mark.")
                messages.extend(extra_messages)
        elif action_type == "attack_if_enemy_intends_change_stance":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                damage = self._compute_player_attack_damage(
                    combat,
                    int(action["value"]),
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                if self._enemy_intends_attack(target):
                    messages.append(self._change_stance(run, combat, str(action["stance"])))
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "conditional_wrath_block":
            gained = int(action["value"])
            if combat.stance == "wrath":
                gained += int(action.get("wrath_bonus", 0))
            self._gain_player_block(run, combat, gained, messages)
        elif action_type == "draw_if_cards_played_below":
            limit = int(action["limit"])
            if combat.player_statuses.get("cards_played_turn", 0) <= limit:
                self._draw_cards(run, combat, int(action["value"]))
                messages.append(f"You draw {int(action['value'])} card(s).")
        elif action_type == "second_wind":
            exhausted, exhaust_messages = self._exhaust_hand_matching(
                run,
                combat,
                exclude_types={"attack"},
            )
            messages.extend(exhaust_messages)
            if exhausted > 0:
                self._gain_player_block(
                    run,
                    combat,
                    exhausted * int(action["value"]),
                    messages,
                )
        elif action_type == "sever_soul":
            exhausted, exhaust_messages = self._exhaust_hand_matching(
                run,
                combat,
                exclude_types={"attack"},
            )
            messages.extend(exhaust_messages)
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                damage = self._compute_player_attack_damage(
                    combat,
                    int(action["value"]),
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "attack_per_strike":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                strike_count = self._count_cards_by_key(run, combat, "strike")
                base = int(action["value"]) + strike_count * int(action.get("per", 2))
                damage = self._compute_player_attack_damage(
                    combat,
                    base,
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "fiend_fire":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                victims = list(combat.hand)
                combat.hand = []
                for victim in victims:
                    messages.extend(self._exhaust_card(run, combat, victim))
                    damage = self._compute_player_attack_damage(
                        combat,
                        int(action["value"]),
                        combat.player_statuses,
                        target.statuses,
                    )
                    dealt, extra_messages = self._resolve_player_attack_hit(
                        run,
                        combat,
                        target,
                        damage,
                        triggers_thorns=not from_potion,
                    )
                    messages.append(f"{target.name} takes {dealt} damage.")
                    messages.extend(extra_messages)
                    if target.hp <= 0:
                        messages.append(f"{target.name} is defeated.")
                        combat.enemies = self._prune_enemies(combat.enemies)
                        break
        elif action_type == "gain_strength_if_enemy_intends_attack":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None and self._enemy_intends_attack(target):
                combat.player_statuses["strength"] = (
                    combat.player_statuses.get("strength", 0) + int(action["value"])
                )
                messages.append(f"You gain {int(action['value'])} Strength.")
            else:
                messages.append("No opening appears.")
        elif action_type == "claw_attack":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                bonus = combat.player_statuses.get("claw_bonus", 0)
                damage = self._compute_player_attack_damage(
                    combat,
                    int(action["value"]) + bonus,
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                combat.player_statuses["claw_bonus"] = bonus + int(action.get("bonus", 2))
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "stack_block":
            self._gain_player_block(
                run,
                combat,
                len(combat.discard_pile) * int(action.get("per", 1)),
                messages,
            )
        elif action_type == "inner_peace":
            if combat.stance == "calm":
                self._draw_cards(run, combat, int(action["draw"]))
                messages.append(f"You draw {int(action['draw'])} card(s).")
            else:
                messages.append(self._change_stance(run, combat, "calm"))
        elif action_type == "follow_up":
            if combat.player_statuses.get("last_card_attack", 0) > 0:
                energy = int(action.get("energy", 0))
                draw_amount = int(action.get("draw", 0))
                if energy > 0:
                    combat.energy += energy
                    messages.append(f"You gain {energy} Energy.")
                if draw_amount > 0:
                    self._draw_cards(run, combat, draw_amount)
                    messages.append(f"You draw {draw_amount} card(s).")
        elif action_type == "heel_hook":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                weak = target.statuses.get("weak", 0) > 0
                damage = self._compute_player_attack_damage(
                    combat,
                    int(action["value"]),
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                if weak:
                    combat.energy += int(action.get("energy", 1))
                    self._draw_cards(run, combat, int(action.get("draw", 1)))
                    messages.append("Heel Hook refunds itself.")
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "all_for_one":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                damage = self._compute_player_attack_damage(
                    combat,
                    int(action["value"]),
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                zero_costs = [card for card in list(combat.discard_pile) if self.card_cost(card, combat) == 0]
                for card in zero_costs:
                    combat.discard_pile.remove(card)
                    combat.hand.append(card)
                    messages.append(f"{self.card_name(card)} returns to your hand.")
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "omniscience":
            chosen = self._choose_highest_cost_card(combat.draw_pile, combat, playable_only=True)
            if chosen is None:
                messages.append("No card is available for Omniscience.")
            else:
                combat.draw_pile.remove(chosen)
                start_turn = combat.turn
                for index in range(2):
                    if run.phase != "combat" or run.combat is not combat:
                        break
                    combat.hand.append(chosen)
                    self._grant_free_plays(combat, chosen.instance_id)
                    messages.append(f"Omniscience plays {self.card_name(chosen)}.")
                    messages.append(self.play_card(run, chosen.instance_id))
                    if run.phase != "combat" or run.combat is not combat or combat.turn != start_turn:
                        break
                    if index == 1:
                        continue
                    next_card = self._find_card_in_combat(combat, chosen.instance_id)
                    if next_card is None:
                        break
                    chosen = next_card
                    for pile in (combat.discard_pile, combat.exhaust_pile, combat.draw_pile):
                        found = self._find_card(pile, chosen.instance_id)
                        if found is not None:
                            pile.remove(found)
                            chosen = found
                            break
                if run.phase == "combat" and run.combat is combat:
                    final_card = self._find_card_in_combat(combat, chosen.instance_id)
                    if final_card is not None and final_card not in combat.exhaust_pile:
                        for pile in (combat.hand, combat.draw_pile, combat.discard_pile):
                            found = self._find_card(pile, final_card.instance_id)
                            if found is not None:
                                pile.remove(found)
                                combat.exhaust_pile.append(found)
                                messages.append(f"{self.card_name(found)} is exhausted by Omniscience.")
                                break
        elif action_type == "attack_and_gold_on_kill":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                was_alive = target.hp > 0
                damage = self._compute_player_attack_damage(
                    combat,
                    int(action["value"]),
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                if was_alive and target.hp <= 0:
                    gained = self._gain_gold(run, int(action["gold"]))
                    if gained > 0:
                        messages.append(f"You gain {gained} gold.")
                    else:
                        messages.append("Ectoplasm prevents you from gaining gold.")
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "attack_and_gain_energy_on_kill":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                was_alive = target.hp > 0
                damage = self._compute_player_attack_damage(
                    combat,
                    int(action["value"]),
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                if was_alive and target.hp <= 0:
                    combat.energy += int(action["energy"])
                    messages.append(f"You gain {int(action['energy'])} Energy.")
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "attack_and_upgrade_on_kill":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                was_alive = target.hp > 0
                damage = self._compute_player_attack_damage(
                    combat,
                    int(action["value"]),
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                if was_alive and target.hp <= 0:
                    upgrades = self._upgrade_random_cards(run, "attack", 1) or self._upgrade_random_cards(run, "skill", 1)
                    messages.extend(upgrades)
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "attack_heal":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                damage = self._compute_player_attack_damage(
                    combat,
                    int(action["value"]),
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                healed = self._heal_run(run, int(action["heal"]))
                self._sync_player_hp_relics(run, combat, messages)
                if healed > 0:
                    messages.append(f"You heal {healed} HP.")
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "ritual_dagger":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                active_id = str(combat.player_meta.get("active_card_instance_id", ""))
                persistent = self._find_card(run.deck, active_id)
                base = int(action["value"]) + (persistent.misc if persistent is not None else 0)
                damage = self._compute_player_attack_damage(
                    combat,
                    base,
                    combat.player_statuses,
                    target.statuses,
                )
                was_alive = target.hp > 0
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                if was_alive and target.hp <= 0 and persistent is not None:
                    persistent.misc += int(action.get("gain", 3))
                    messages.append(f"Ritual Dagger permanently gains {int(action.get('gain', 3))} damage.")
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        elif action_type == "wish_random":
            choice = self.rng.choice(["become_almighty", "fame_and_fortune", "live_forever"])
            if choice == "become_almighty":
                amount = int(action.get("strength", 3))
                combat.player_statuses["strength"] = combat.player_statuses.get("strength", 0) + amount
                messages.append(f"Wish grants {amount} Strength.")
            elif choice == "fame_and_fortune":
                amount = int(action.get("gold", 25))
                gained = self._gain_gold(run, amount)
                messages.append(
                    f"Wish grants {gained} gold." if gained > 0 else "Ectoplasm prevents Wish from granting gold."
                )
            else:
                amount = int(action.get("plated", 6))
                combat.player_statuses["plated_armor"] = combat.player_statuses.get("plated_armor", 0) + amount
                messages.append(f"Wish grants {amount} Plated Armor.")
        elif action_type == "attack_per_deck_size":
            target = target_enemy or self._default_target_enemy(combat)
            if target is not None:
                damage = self._compute_player_attack_damage(
                    combat,
                    len(run.deck) * int(action["value"]),
                    combat.player_statuses,
                    target.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    target,
                    damage,
                    triggers_thorns=not from_potion,
                )
                messages.append(f"{target.name} takes {dealt} damage.")
                messages.extend(extra_messages)
                if target.hp <= 0:
                    messages.append(f"{target.name} is defeated.")
                    combat.enemies = self._prune_enemies(combat.enemies)
        return messages

    def _apply_status_from_action(
        self,
        run: RunState,
        combat: CombatState,
        *,
        target: str,
        status: str,
        value: int,
        target_enemy: EnemyState | None = None,
    ) -> list[str]:
        total_value = value
        if status == "poison" and combat.player_statuses.get("poison_bonus", 0) > 0:
            total_value += combat.player_statuses["poison_bonus"]
        messages: list[str] = []
        if target == "enemy":
            enemy = target_enemy or self._default_target_enemy(combat)
            if enemy is not None:
                applied, status_messages = self._apply_status_to_enemy(
                    enemy,
                    status,
                    total_value,
                )
                messages.extend(status_messages)
                if applied > 0 and self._status_is_debuff(status):
                    sadistic = combat.player_statuses.get("sadistic_nature", 0)
                    if sadistic > 0:
                        dealt, extra_messages = self._deal_damage_to_enemy(run, combat, enemy, sadistic)
                        messages.append(f"Sadistic Nature deals {dealt} damage to {enemy.name}.")
                        messages.extend(extra_messages)
                    sleight = combat.player_statuses.get("sleight_of_flesh", 0)
                    if sleight > 0:
                        dealt, extra_messages = self._deal_damage_to_enemy(run, combat, enemy, sleight)
                        messages.append(f"Sleight Of Flesh deals {dealt} damage to {enemy.name}.")
                        messages.extend(extra_messages)
                if applied > 0 and status == "doom" and combat.player_statuses.get("shroud", 0) > 0:
                    self._gain_player_block(
                        run,
                        combat,
                        combat.player_statuses["shroud"],
                        messages,
                        message="Shroud grants {gained} Block.",
                    )
                if (
                    applied > 0
                    and status == "vulnerable"
                    and combat.player_statuses.get("champion_belt", 0) > 0
                ):
                    _, belt_messages = self._apply_status_to_enemy(enemy, "weak", 1)
                    messages.extend(
                        message.replace(
                            f"{enemy.name} gains 1 Weak.",
                            f"Champion Belt applies 1 Weak to {enemy.name}.",
                        )
                        for message in belt_messages
                    )
        elif target == "all_enemies":
            for enemy in combat.enemies:
                applied, status_messages = self._apply_status_to_enemy(
                    enemy,
                    status,
                    total_value,
                )
                messages.extend(status_messages)
                if applied > 0 and self._status_is_debuff(status):
                    sadistic = combat.player_statuses.get("sadistic_nature", 0)
                    if sadistic > 0:
                        dealt, extra_messages = self._deal_damage_to_enemy(run, combat, enemy, sadistic)
                        messages.append(f"Sadistic Nature deals {dealt} damage to {enemy.name}.")
                        messages.extend(extra_messages)
                    sleight = combat.player_statuses.get("sleight_of_flesh", 0)
                    if sleight > 0:
                        dealt, extra_messages = self._deal_damage_to_enemy(run, combat, enemy, sleight)
                        messages.append(f"Sleight Of Flesh deals {dealt} damage to {enemy.name}.")
                        messages.extend(extra_messages)
                if applied > 0 and status == "doom" and combat.player_statuses.get("shroud", 0) > 0:
                    self._gain_player_block(
                        run,
                        combat,
                        combat.player_statuses["shroud"],
                        messages,
                        message="Shroud grants {gained} Block.",
                    )
                if (
                    applied > 0
                    and status == "vulnerable"
                    and combat.player_statuses.get("champion_belt", 0) > 0
                ):
                    _, belt_messages = self._apply_status_to_enemy(enemy, "weak", 1)
                    messages.extend(
                        message.replace(
                            f"{enemy.name} gains 1 Weak.",
                            f"Champion Belt applies 1 Weak to {enemy.name}.",
                        )
                        for message in belt_messages
                    )
        elif target in {"self", "player"}:
            _, status_messages = self._apply_status_to_player(combat, status, value)
            messages.extend(status_messages)
        return messages

    def _multiply_status(
        self,
        combat: CombatState,
        *,
        target: str,
        status: str,
        factor: int,
        target_enemy: EnemyState | None = None,
    ) -> list[str]:
        messages: list[str] = []
        if target == "enemy":
            enemy = target_enemy or self._default_target_enemy(combat)
            if enemy is None:
                return messages
            current = enemy.statuses.get(status, 0)
            enemy.statuses[status] = current * factor
            messages.append(f"{enemy.name}'s {status} becomes {enemy.statuses[status]}.")
        elif target in {"self", "player"}:
            current = combat.player_statuses.get(status, 0)
            combat.player_statuses[status] = current * factor
            messages.append(f"Your {status} becomes {combat.player_statuses[status]}.")
        return messages

    def _run_enemy_turn(self, run: RunState) -> str:
        combat = self._require_combat(run)
        messages: list[str] = []
        combat.player_meta["enemy_turn_active"] = True
        for enemy in combat.enemies:
            if enemy.hp > 0 and enemy.statuses.get("barricade", 0) <= 0:
                enemy.block = 0
            if enemy.meta.pop("rebirth_invulnerable", 0):
                enemy.statuses.pop("intangible", None)
        for enemy in list(combat.enemies):
            if enemy.hp <= 0:
                if enemy.key == "darkling" and int(enemy.meta.get("revive_pending", 0)) > 0:
                    if not self._other_living_darkling_exists(combat, enemy.enemy_id):
                        enemy.meta.pop("revive_pending", None)
                        continue
                    intent = self._current_intent(enemy)
                    messages.append(f"{enemy.name} uses {intent.name}.")
                    remaining = int(enemy.meta.get("revive_pending", 0)) - 1
                    if remaining <= 0:
                        enemy.meta.pop("revive_pending", None)
                        enemy.block = 0
                        enemy.statuses = {}
                        enemy.hp = max(1, enemy.max_hp // 2)
                        enemy.current_intent_index = self._choose_darkling_intent(enemy, opening=True)
                        messages.append(f"{enemy.name} reincarnates with {enemy.hp} HP.")
                    else:
                        enemy.meta["revive_pending"] = remaining
                        enemy.current_intent_index = 4
                continue
            if enemy.asleep_turns > 0:
                enemy.asleep_turns -= 1
                if self._current_intent(enemy).name == "Asleep":
                    self._advance_enemy_intent(enemy, combat)
                messages.append(f"{enemy.name} remains dormant.")
                continue
            if enemy.meta.get("malleable_base"):
                enemy.meta["malleable_current"] = int(enemy.meta["malleable_base"])
            intent = self._current_intent(enemy)
            messages.append(f"{enemy.name} uses {intent.name}.")
            for action in intent.actions:
                messages.extend(self._resolve_enemy_action(run, combat, enemy, action))
                if run.hp <= 0:
                    run.phase = "defeat"
                    run.combat = None
                    messages.append("You are slain.")
                    combat.player_meta.pop("enemy_turn_active", None)
                    return " ".join(messages)
                if enemy.hp <= 0:
                    break
            if enemy.hp <= 0:
                continue
            if enemy.key == "the_champ" and enemy.current_intent_index == 0:
                enemy.meta["champ_defensive_uses"] = int(enemy.meta.get("champ_defensive_uses", 0)) + 1
            self._advance_enemy_intent(enemy, combat)
            if enemy.key == "nemesis":
                toggle = enemy.meta.get("intangible_toggle", 0) + 1
                enemy.meta["intangible_toggle"] = toggle
                if toggle % 2 == 1:
                    enemy.statuses["intangible"] = 2
                    messages.append(f"{enemy.name} fades into Intangible.")
                else:
                    enemy.statuses.pop("intangible", None)
            self._tick_statuses(enemy.statuses, messages, enemy.name)
            if enemy.statuses.get("poison", 0) > 0:
                poison = enemy.statuses["poison"]
                dealt, extra_messages = self._deal_damage_to_enemy(run, combat, enemy, poison)
                messages.append(f"{enemy.name} takes {dealt} poison damage.")
                messages.extend(extra_messages)
                enemy.statuses["poison"] = max(0, poison - 1)
                if enemy.statuses["poison"] <= 0:
                    enemy.statuses.pop("poison", None)
            ritual = enemy.statuses.get("ritual", 0)
            if ritual > 0:
                enemy.statuses["strength"] = enemy.statuses.get("strength", 0) + ritual
                messages.append(f"{enemy.name}'s Ritual grants {ritual} Strength.")
            plated = enemy.statuses.get("plated_armor", 0)
            if plated > 0:
                enemy.block += plated
                messages.append(f"{enemy.name}'s Plated Armor grants {plated} Block.")
            metallicize = enemy.statuses.get("metallicize", 0)
            if metallicize > 0:
                enemy.block += metallicize
                messages.append(f"{enemy.name}'s Metallicize grants {metallicize} Block.")
            regeneration = enemy.statuses.get("regeneration", 0)
            if regeneration > 0:
                healed = min(enemy.max_hp, enemy.hp + regeneration) - enemy.hp
                enemy.hp += healed
                if healed > 0:
                    messages.append(f"{enemy.name} regenerates {healed} HP.")
                enemy.statuses["regeneration"] = regeneration - 1
                if enemy.statuses["regeneration"] <= 0:
                    enemy.statuses.pop("regeneration", None)
            if enemy.statuses.get("intangible", 0) > 0:
                enemy.statuses["intangible"] -= 1
                if enemy.statuses["intangible"] <= 0:
                    enemy.statuses.pop("intangible", None)
            flight_base = int(enemy.meta.get("flight_base", 0))
            if (
                enemy.hp > 0
                and flight_base > 0
                and not enemy.meta.get("grounded")
                and 0 < enemy.statuses.get("flight", 0) < flight_base
            ):
                enemy.statuses["flight"] = flight_base
                messages.append(f"{enemy.name} regains Flight.")
            explode_damage = int(enemy.meta.pop("explode_pending", 0))
            if explode_damage > 0 and enemy.hp > 0:
                dealt = self._damage_player(run, combat, explode_damage, from_attack=True)
                messages.append(f"{enemy.name} explodes for {dealt} damage.")
                if enemy.hp > 0:
                    messages.extend(self._retaliate_with_player_thorns(run, combat, enemy))
                if enemy.hp > 0:
                    enemy.hp = 0
                    messages.extend(self._handle_enemy_damage_trigger(run, combat, enemy, 0))
                if run.hp <= 0:
                    run.phase = "defeat"
                    run.combat = None
                    messages.append("You are slain.")
                    combat.player_meta.pop("enemy_turn_active", None)
                    return " ".join(messages)
            elif enemy.hp > 0 and enemy.statuses.get("explosive", 0) > 0:
                enemy.statuses["explosive"] -= 1
                if enemy.statuses["explosive"] <= 0:
                    enemy.statuses.pop("explosive", None)
            if enemy.hp > 0 and enemy.statuses.get("fading", 0) > 0:
                enemy.statuses["fading"] -= 1
                if enemy.statuses["fading"] <= 0:
                    enemy.statuses.pop("fading", None)
                    enemy.hp = 0
                    messages.append(f"{enemy.name} fades away.")
                    messages.extend(self._handle_enemy_damage_trigger(run, combat, enemy, 0))
            if enemy.hp > 0 and enemy.meta.get("strength_up", 0) > 0:
                enemy.statuses["strength"] = enemy.statuses.get("strength", 0) + int(enemy.meta["strength_up"])
                messages.append(f"{enemy.name} gains {int(enemy.meta['strength_up'])} Strength.")
            if enemy.hp > 0 and self._resolve_enemy_doom(run, combat, enemy, messages):
                continue
        combat.enemies = self._prune_enemies(combat.enemies)
        combat.log.extend(messages)
        combat.log = combat.log[-12:]
        combat.player_meta.pop("enemy_turn_active", None)
        return " ".join(messages)

    def _resolve_enemy_action(
        self,
        run: RunState,
        combat: CombatState,
        enemy: EnemyState,
        action: dict[str, object],
    ) -> list[str]:
        action_type = str(action["type"])
        messages: list[str] = []
        if action_type == "attack":
            hits = int(action.get("hits", 1))
            for _ in range(hits):
                damage = self._compute_enemy_attack_damage(
                    combat,
                    int(action["value"]),
                    enemy.statuses,
                    combat.player_statuses,
                )
                damage = self._adjust_enemy_attack_damage(run, enemy, damage)
                dealt = self._damage_player(run, combat, damage, from_attack=True)
                messages.append(f"You take {dealt} damage.")
                messages.extend(self._retaliate_with_player_thorns(run, combat, enemy))
                messages.extend(self._after_enemy_attack_hit(run, combat, enemy, dealt))
                if enemy.hp <= 0 or run.hp <= 0:
                    break
        elif action_type == "attack_turn_scaled_hits":
            hits = max(
                int(action.get("minimum_hits", 1)),
                (combat.turn + int(action.get("turn_divisor", 2)) - 1)
                // max(1, int(action.get("turn_divisor", 2))),
            )
            for _ in range(hits):
                damage = self._compute_enemy_attack_damage(
                    combat,
                    int(action["value"]),
                    enemy.statuses,
                    combat.player_statuses,
                )
                damage = self._adjust_enemy_attack_damage(run, enemy, damage)
                dealt = self._damage_player(run, combat, damage, from_attack=True)
                messages.append(f"You take {dealt} damage.")
                messages.extend(self._retaliate_with_player_thorns(run, combat, enemy))
                messages.extend(self._after_enemy_attack_hit(run, combat, enemy, dealt))
                if enemy.hp <= 0 or run.hp <= 0:
                    break
        elif action_type == "attack_hexaghost_divider":
            current_hp = max(0, run.hp)
            base = max(
                int(action.get("minimum", 1)),
                min(
                    int(action.get("maximum", 6)),
                    (current_hp // max(1, int(action.get("divisor", 12)))) + 1,
                ),
            )
            for _ in range(int(action.get("hits", 6))):
                damage = self._compute_enemy_attack_damage(
                    combat,
                    base,
                    enemy.statuses,
                    combat.player_statuses,
                )
                damage = self._adjust_enemy_attack_damage(run, enemy, damage)
                dealt = self._damage_player(run, combat, damage, from_attack=True)
                messages.append(f"You take {dealt} damage.")
                messages.extend(self._retaliate_with_player_thorns(run, combat, enemy))
                messages.extend(self._after_enemy_attack_hit(run, combat, enemy, dealt))
                if enemy.hp <= 0 or run.hp <= 0:
                    break
        elif action_type == "block":
            gained = self._compute_block_gain(int(action["value"]), enemy.statuses)
            enemy.block += gained
            messages.append(f"{enemy.name} gains {gained} Block.")
        elif action_type == "block_target":
            target_key = action.get("target_key")
            if target_key is None:
                target_enemy = enemy
            else:
                target_enemy = next(
                    (
                        entry
                        for entry in combat.enemies
                        if entry.key == str(target_key) and entry.hp > 0
                    ),
                    enemy,
                )
            gained = self._compute_block_gain(int(action["value"]), target_enemy.statuses)
            target_enemy.block += gained
            messages.append(f"{target_enemy.name} gains {gained} Block.")
        elif action_type == "draw_next_turn":
            value = int(action["value"])
            combat.player_statuses["next_turn_draw"] = (
                combat.player_statuses.get("next_turn_draw", 0) + value
            )
            if value >= 0:
                messages.append(f"You will draw {value} extra card(s) next turn.")
            else:
                messages.append(f"You will draw {abs(value)} fewer card(s) next turn.")
        elif action_type == "apply_status":
            status = str(action["status"])
            value = int(action["value"])
            target = str(action["target"])
            if target == "player":
                _, status_messages = self._apply_status_to_player(combat, status, value)
                messages.extend(status_messages)
            elif target == "self":
                self._apply_status_value(enemy.statuses, status, value)
                if status == "enrage":
                    enemy.meta["enrage"] = value
                messages.append(f"{enemy.name} gains {value} {self._status_label(status)}.")
        elif action_type == "modify_status":
            status = str(action["status"])
            value = int(action["value"])
            target = str(action["target"])
            temporary = bool(action.get("temporary", False))
            if target == "player":
                delta, blocked = self._modify_status(
                    combat.player_statuses,
                    status,
                    value,
                    use_artifact=True,
                    temporary=temporary,
                )
                if blocked:
                    messages.append(f"Artifact negates {self._status_label(status)}.")
                elif delta != 0:
                    verb = "gain" if delta > 0 else "lose"
                    messages.append(f"You {verb} {abs(delta)} {self._status_label(status)}.")
            elif target == "self":
                delta, _ = self._modify_status(
                    enemy.statuses,
                    status,
                    value,
                    temporary=temporary,
                )
                if delta != 0:
                    verb = "gains" if delta > 0 else "loses"
                    messages.append(f"{enemy.name} {verb} {abs(delta)} {self._status_label(status)}.")
        elif action_type == "attack_scaling":
            meta_key = str(action.get("meta_key", f"{enemy.key}_attack"))
            base = int(enemy.meta.get(meta_key, int(action["value"])))
            hits = int(action.get("hits", 1))
            for _ in range(hits):
                damage = self._compute_enemy_attack_damage(
                    combat,
                    base,
                    enemy.statuses,
                    combat.player_statuses,
                )
                damage = self._adjust_enemy_attack_damage(run, enemy, damage)
                dealt = self._damage_player(run, combat, damage, from_attack=True)
                messages.append(f"You take {dealt} damage.")
                messages.extend(self._retaliate_with_player_thorns(run, combat, enemy))
                messages.extend(self._after_enemy_attack_hit(run, combat, enemy, dealt))
                if enemy.hp <= 0 or run.hp <= 0:
                    break
            enemy.meta[meta_key] = base + int(action.get("increment", 0))
        elif action_type == "hexaghost_sear":
            damage = self._compute_enemy_attack_damage(
                combat,
                int(action.get("damage", 6)),
                enemy.statuses,
                combat.player_statuses,
            )
            damage = self._adjust_enemy_attack_damage(run, enemy, damage)
            dealt = self._damage_player(run, combat, damage, from_attack=True)
            messages.append(f"You take {dealt} damage.")
            messages.extend(self._retaliate_with_player_thorns(run, combat, enemy))
            messages.extend(self._after_enemy_attack_hit(run, combat, enemy, dealt))
            messages.extend(
                self._create_cards_in_combat(
                    run,
                    combat,
                    key="burn",
                    location="discard",
                    upgraded=bool(enemy.meta.get("hexaghost_burn_plus")),
                )
            )
        elif action_type == "hexaghost_inferno":
            hits = int(action.get("hits", 6))
            for _ in range(hits):
                damage = self._compute_enemy_attack_damage(
                    combat,
                    int(action.get("damage", 2)),
                    enemy.statuses,
                    combat.player_statuses,
                )
                damage = self._adjust_enemy_attack_damage(run, enemy, damage)
                dealt = self._damage_player(run, combat, damage, from_attack=True)
                messages.append(f"You take {dealt} damage.")
                messages.extend(self._retaliate_with_player_thorns(run, combat, enemy))
                messages.extend(self._after_enemy_attack_hit(run, combat, enemy, dealt))
                if enemy.hp <= 0 or run.hp <= 0:
                    break
            messages.extend(
                self._create_cards_in_combat(
                    run,
                    combat,
                    key="burn",
                    location="discard",
                    count=int(action.get("burns", 3)),
                    upgraded=True,
                )
            )
            enemy.meta["hexaghost_burn_plus"] = 1
            self._upgrade_burn_cards_in_combat(combat)
        elif action_type == "heart_buff":
            buff_count = int(enemy.meta.get("heart_buff_count", 0)) + 1
            enemy.meta["heart_buff_count"] = buff_count
            if enemy.statuses.get("strength", 0) < 0:
                enemy.statuses["strength"] = 0
            strength_gain = 2
            if buff_count == 1:
                enemy.statuses["artifact"] = enemy.statuses.get("artifact", 0) + 2
                messages.append(f"{enemy.name} gains 2 Artifact.")
            elif buff_count == 2:
                enemy.statuses["beat_of_death"] = enemy.statuses.get("beat_of_death", 0) + 1
                messages.append(f"{enemy.name}'s Beat Of Death grows stronger.")
            elif buff_count == 3:
                enemy.statuses["painful_stabs"] = enemy.statuses.get("painful_stabs", 0) + 1
                messages.append(f"{enemy.name} gains Painful Stabs.")
            elif buff_count == 4:
                strength_gain += 10
            elif buff_count >= 5:
                strength_gain += 50
            enemy.statuses["strength"] = enemy.statuses.get("strength", 0) + strength_gain
            messages.append(f"{enemy.name} gains {strength_gain} Strength.")
        elif action_type == "create_card":
            messages.extend(
                self._create_cards_in_combat(
                    run,
                    combat,
                    key=str(action["key"]),
                    location=str(action["location"]),
                    count=int(action.get("count", 1)),
                    upgraded=bool(action.get("upgraded", False)),
                )
            )
        elif action_type == "summon":
            messages.extend(
                self._summon_enemies(
                    run,
                    combat,
                    [str(key) for key in action.get("keys", [])],
                    max_enemies=int(action.get("max_enemies", 5)),
                )
            )
        elif action_type == "buff_all_enemies":
            status = str(action["status"])
            value = int(action["value"])
            for target_enemy in combat.enemies:
                self._apply_status_value(target_enemy.statuses, status, value)
                messages.append(f"{target_enemy.name} gains {value} {self._status_label(status)}.")
        elif action_type == "heal_self":
            value = int(action["value"])
            healed = min(enemy.max_hp, enemy.hp + value) - enemy.hp
            enemy.hp += healed
            messages.append(f"{enemy.name} heals {healed} HP.")
        elif action_type == "heal_to_half":
            target_hp = max(enemy.hp, enemy.max_hp // 2)
            healed = max(0, target_hp - enemy.hp)
            enemy.hp = max(enemy.hp, target_hp)
            messages.append(f"{enemy.name} heals {healed} HP.")
        elif action_type == "clear_debuffs":
            self._clear_debuffs(enemy.statuses)
            messages.append(f"{enemy.name} clears its debuffs.")
        elif action_type == "heal_all_enemies":
            value = int(action["value"])
            for target_enemy in combat.enemies:
                if target_enemy.hp <= 0:
                    continue
                healed = min(target_enemy.max_hp, target_enemy.hp + value) - target_enemy.hp
                target_enemy.hp += healed
                messages.append(f"{target_enemy.name} heals {healed} HP.")
        elif action_type == "steal_gold":
            amount = min(run.gold, int(action["value"]))
            run.gold -= amount
            enemy.meta["stolen_gold"] = int(enemy.meta.get("stolen_gold", 0)) + amount
            messages.append(f"{enemy.name} steals {amount} Gold.")
        elif action_type == "escape":
            enemy.meta["escaped"] = 1
            combat.reward_gold = max(0, combat.reward_gold - int(enemy.meta.get("reward_gold", 0)))
            enemy.hp = 0
            enemy.block = 0
            messages.append(f"{enemy.name} escapes with its loot.")
        elif action_type == "add_card_to_deck":
            for _ in range(int(action.get("count", 1))):
                card = self.create_card_instance(
                    run,
                    str(action["key"]),
                    upgraded=bool(action.get("upgraded", False)),
                )
                messages.extend(self._add_card_to_deck(run, card))
                messages.append(f"{self.card_name(card)} is added to your deck.")
        elif action_type == "explode":
            enemy.meta["explode_pending"] = int(action["value"])
        return messages

    def _start_next_turn(self, run: RunState) -> None:
        combat = self._require_combat(run)
        combat.turn += 1
        retained_energy = combat.energy if "ice_cream" in run.relics else 0
        combat.energy = combat.max_energy + retained_energy + combat.player_statuses.pop("next_turn_energy", 0)
        if combat.player_statuses.get("blur", 0) <= 0 and combat.player_statuses.get("barricade", 0) <= 0:
            if "calipers" in run.relics:
                combat.player_block = max(0, combat.player_block - 15)
            else:
                combat.player_block = 0
        else:
            if combat.player_statuses.get("blur", 0) > 0:
                combat.player_statuses["blur"] -= 1
                if combat.player_statuses["blur"] <= 0:
                    combat.player_statuses.pop("blur", None)
        combat.player_statuses["attacks_played_turn"] = 0
        combat.player_statuses["skills_played_turn"] = 0
        combat.player_statuses["cards_played_turn"] = 0
        combat.player_statuses["cards_discarded_turn"] = 0
        combat.player_statuses["last_card_attack"] = 0
        combat.player_statuses["last_card_skill"] = 0
        combat.player_meta["cards_drawn_turn"] = 0
        combat.player_meta["osty_attacks_turn"] = 0
        combat.player_meta["played_card_keys_turn"] = {}
        combat.player_meta.pop("sic_em_targets", None)
        combat.player_statuses.pop("orange_pellets_attack", None)
        combat.player_statuses.pop("orange_pellets_skill", None)
        combat.player_statuses.pop("orange_pellets_power", None)
        combat.player_statuses.pop("orange_pellets_used_turn", None)
        combat.player_meta["echo_form_used_turn"] = False
        combat.player_statuses.pop("bullet_time", None)
        combat.player_statuses.pop("no_draw", None)
        if "brimstone" in run.relics:
            combat.player_statuses["strength"] = combat.player_statuses.get("strength", 0) + 2
            for enemy in combat.enemies:
                if enemy.hp > 0:
                    enemy.statuses["strength"] = enemy.statuses.get("strength", 0) + 1
            combat.log.append("Brimstone grants you 2 Strength and all enemies 1 Strength.")
        if "horn_cleat" in run.relics and combat.turn == 2:
            combat.player_block += 14
            combat.log.append("Horn Cleat grants 14 Block.")
        if "happy_flower" in run.relics:
            counter = combat.player_statuses.get("happy_flower_counter", 0) + 1
            if counter >= 3:
                counter = 0
                combat.energy += 1
                combat.log.append("Happy Flower grants 1 Energy.")
            combat.player_statuses["happy_flower_counter"] = counter
        if "incense_burner" in run.relics:
            counter = combat.player_statuses.get("incense_burner_counter", 0) + 1
            if counter >= 6:
                counter = 0
                combat.player_statuses["intangible"] = (
                    combat.player_statuses.get("intangible", 0) + 1
                )
                combat.log.append("Incense Burner grants 1 Intangible.")
            combat.player_statuses["incense_burner_counter"] = counter
        if "damaru" in run.relics:
            _, messages = self._apply_status_to_player(combat, "mantra", 1)
            combat.log.extend(
                message.replace("You gain 1 Mantra.", "Damaru grants 1 Mantra.")
                for message in messages
            )
        if run.character == "necrobinder":
            self._apply_necrobinder_turn_start_effects(run, combat)
        if "inserter" in run.relics and combat.turn % 2 == 0:
            combat.orb_slots += 1
            combat.log.append("Inserter grants 1 Orb slot.")
        battle_hymn = combat.player_statuses.get("battle_hymn", 0)
        for _ in range(battle_hymn):
            combat.hand.append(self.create_card_instance(run, "smite"))
        if battle_hymn > 0:
            combat.log.append(f"Battle Hymn adds {battle_hymn} Smite.")
        infinite_blades = combat.player_statuses.get("infinite_blades", 0)
        for _ in range(infinite_blades):
            combat.hand.append(self.create_card_instance(run, "shiv"))
        if infinite_blades > 0:
            combat.log.append(f"Infinite Blades adds {infinite_blades} Shiv.")
        next_turn_block = combat.player_statuses.pop("next_turn_block", 0)
        if next_turn_block > 0:
            self._gain_player_block(
                run,
                combat,
                next_turn_block,
                combat.log,
                message="You gain {gained} Block at the start of turn.",
            )
        tools = combat.player_statuses.get("tools_of_the_trade", 0)
        if tools > 0:
            self._draw_cards(run, combat, tools)
            self._discard_random_cards(combat, tools)
            combat.log.append(f"Tools Of The Trade cycles {tools} card(s).")
        temporary_costs = {
            str(key): int(value)
            for key, value in dict(combat.player_meta.pop("temporary_costs", {})).items()
        }
        for instance_id, adjustment in temporary_costs.items():
            card = self._find_card_in_combat(combat, instance_id)
            if card is not None:
                card.cost_adjustment = adjustment
        machine_learning = combat.player_statuses.get("machine_learning", 0)
        if machine_learning > 0:
            self._draw_cards(run, combat, machine_learning)
            combat.log.append(f"Machine Learning draws {machine_learning} card(s).")
        creative_ai = combat.player_statuses.get("creative_ai", 0)
        if creative_ai > 0:
            created = self._create_random_cards_in_combat(
                run,
                combat,
                pool="character_power",
                location="hand",
                count=creative_ai,
            )
            combat.log.extend(created)
        magnetism = combat.player_statuses.get("magnetism", 0)
        if magnetism > 0:
            created = self._create_random_cards_in_combat(
                run,
                combat,
                pool="colorless",
                location="hand",
                count=magnetism,
            )
            combat.log.extend(created)
        devotion = combat.player_statuses.get("devotion", 0)
        if devotion > 0:
            _, messages = self._apply_status_to_player(combat, "mantra", devotion)
            combat.log.extend(messages)
        collect_turns = combat.player_statuses.get("collect", 0)
        if collect_turns > 0:
            combat.hand.append(self.create_card_instance(run, "miracle", upgraded=True))
            combat.player_statuses["collect"] = collect_turns - 1
            if combat.player_statuses["collect"] <= 0:
                combat.player_statuses.pop("collect", None)
            combat.log.append("Collect adds a Miracle+.")
        nightmare_queue = combat.player_meta.pop("nightmare", [])
        for payload in nightmare_queue:
            combat.log.extend(
                self._create_cards_in_combat(
                    run,
                    combat,
                    key=str(payload.get("key")),
                    location="hand",
                    count=int(payload.get("count", 3)),
                    upgraded=bool(payload.get("upgraded", False)),
                )
            )
        if combat.player_statuses.pop("phantasmal_killer", 0) > 0:
            combat.player_statuses["double_attack_damage"] = 1
            combat.log.append("Phantasmal Killer empowers your attacks this turn.")
        deva_form = combat.player_statuses.get("deva_form", 0)
        if deva_form > 0:
            combat.player_statuses["next_turn_energy"] = (
                combat.player_statuses.get("next_turn_energy", 0) + deva_form
            )
            combat.player_statuses["deva_form"] = deva_form + 1
            combat.log.append(f"Deva Form prepares {deva_form} extra Energy.")
        fasting = combat.player_statuses.get("fasting", 0)
        if fasting > 0:
            combat.energy = max(0, combat.energy - fasting)
        hello_world = combat.player_statuses.get("hello_world", 0)
        if hello_world > 0:
            created = self._create_random_cards_in_combat(
                run,
                combat,
                pool="character_common",
                location="hand",
                count=hello_world,
            )
            combat.log.extend(created)
        study = combat.player_statuses.get("study", 0)
        if study > 0:
            combat.log.extend(
                self._create_cards_in_combat(run, combat, key="insight", location="draw", count=study)
            )
        mayhem = combat.player_statuses.get("mayhem", 0)
        for _ in range(mayhem):
            if not combat.draw_pile:
                break
            auto_card = combat.draw_pile.pop()
            combat.hand.append(auto_card)
            try:
                combat.log.append(self.play_card(run, auto_card.instance_id))
            except ValueError:
                combat.hand = [card for card in combat.hand if card.instance_id != auto_card.instance_id]
                combat.discard_pile.append(auto_card)
        for enemy in combat.enemies:
            invincible_cap = enemy.meta.get("invincible_cap")
            if invincible_cap:
                enemy.statuses["invincible"] = int(invincible_cap)
        if combat.player_statuses.get("intangible", 0) > 0:
            combat.player_statuses["intangible"] -= 1
            if combat.player_statuses["intangible"] <= 0:
                combat.player_statuses.pop("intangible", None)
        brutality = combat.player_statuses.get("brutality", 0)
        if brutality > 0:
            run.hp = max(0, run.hp - brutality)
            combat.log.append(f"Brutality costs {brutality} HP.")
            self._trigger_combat_hp_loss_relics(run, combat, brutality, combat.log)
            if run.hp <= 0:
                return
            self._draw_cards(run, combat, brutality)
            combat.log.append(f"Brutality draws {brutality} card(s).")
        foresight = combat.player_statuses.get("foresight", 0)
        if foresight > 0:
            self._scry(run, combat, foresight)
        draw_count = 5 + combat.player_statuses.pop("next_turn_draw", 0)
        if "ring_of_the_serpent" in run.relics:
            draw_count += 1
        if "snecko_eye" in run.relics:
            draw_count += 2
        self._draw_cards(run, combat, draw_count)
        combat.log.append(f"Turn {combat.turn} begins.")
        combat.first_turn = False

    def _draw_cards(
        self,
        run: RunState | None,
        combat: CombatState,
        count: int,
    ) -> None:
        if combat.player_statuses.get("no_draw", 0) > 0:
            return
        while count > 0:
            if not combat.draw_pile and combat.discard_pile:
                combat.draw_pile = combat.discard_pile
                combat.discard_pile = []
                self.rng.shuffle(combat.draw_pile)
                if run is not None and "the_abacus" in run.relics:
                    self._gain_player_block(run, combat, 6, combat.log, message="The Abacus grants {gained} Block.")
                if run is not None and "sundial" in run.relics:
                    counter = combat.player_statuses.get("sundial_counter", 0) + 1
                    if counter >= 3:
                        counter = 0
                        combat.energy += 2
                        combat.log.append("Sundial grants 2 Energy.")
                    combat.player_statuses["sundial_counter"] = counter
                if run is not None and "melange" in run.relics:
                    self._scry(run, combat, 3)
            if not combat.draw_pile:
                return
            card = combat.draw_pile.pop()
            combat.hand.append(card)
            self._handle_card_drawn(run, combat, card)
            combat.player_meta["cards_drawn_turn"] = int(combat.player_meta.get("cards_drawn_turn", 0)) + 1
            count -= 1

    def _scry(
        self,
        run: RunState,
        combat: CombatState,
        count: int,
        *,
        messages: list[str] | None = None,
    ) -> None:
        if count <= 0 or not combat.draw_pile:
            return
        log = messages if messages is not None else combat.log
        inspect = list(combat.draw_pile[-min(count, len(combat.draw_pile)):])
        for card in inspect:
            discard = CARD_LIBRARY[card.key].card_type in {"status", "curse"} or not CARD_LIBRARY[card.key].playable
            if discard and card in combat.draw_pile:
                combat.draw_pile.remove(card)
                combat.discard_pile.append(card)
                log.append(f"Scry discards {self.card_name(card)}.")
        nirvana = combat.player_statuses.get("nirvana", 0)
        if nirvana > 0:
            self._gain_player_block(run, combat, nirvana, log, message="Nirvana grants {gained} Block.")
        weaves = [card for card in list(combat.discard_pile) if card.key == "weave"]
        for weave in weaves:
            combat.discard_pile.remove(weave)
            combat.hand.append(weave)
            log.append("Weave returns to your hand.")

    def _handle_card_drawn(
        self,
        run: RunState | None,
        combat: CombatState,
        card: CardInstance,
    ) -> None:
        card_def = CARD_LIBRARY[card.key]
        if combat.player_statuses.get("confused", 0) > 0 and card_def.playable:
            if card.upgraded and card_def.upgraded_cost is not None:
                base_cost = card_def.upgraded_cost
            else:
                base_cost = card_def.cost
            if base_cost >= 0:
                new_cost = self.rng.randint(0, 3)
                self._set_card_cost(card, new_cost)
                combat.log.append(f"Confusion randomizes {self.card_name(card)} to {new_cost} Energy.")
        if card.key == "void":
            combat.energy = max(0, combat.energy - 1)
            combat.log.append("Void drains 1 Energy.")
        if card.key == "endless_agony" and run is not None:
            combat.hand.append(self.create_card_instance(run, "endless_agony", upgraded=card.upgraded))
            combat.log.append("Endless Agony copies itself.")
        if card.key == "deus_ex_machina" and run is not None:
            miracles = 3 if card.upgraded else 2
            for _ in range(miracles):
                combat.hand.append(self.create_card_instance(run, "miracle"))
            combat.hand = [entry for entry in combat.hand if entry.instance_id != card.instance_id]
            combat.exhaust_pile.append(card)
            combat.log.append(f"Deus Ex Machina creates {miracles} Miracle(s).")
        if self.card_is_ethereal(card, combat) and combat.player_statuses.get("pagestorm", 0) > 0 and run is not None:
            self._draw_cards(run, combat, combat.player_statuses["pagestorm"])
            combat.log.append(f"Pagestorm draws {combat.player_statuses['pagestorm']} card(s).")
        if card_def.card_type == "status":
            evolve = combat.player_statuses.get("evolve", 0)
            if evolve > 0 and run is not None:
                self._draw_cards(run, combat, evolve)
                combat.log.append(f"Evolve draws {evolve} card(s).")
        if card_def.card_type in {"status", "curse"}:
            fire_breathing = combat.player_statuses.get("fire_breathing", 0)
            if fire_breathing > 0 and run is not None:
                for enemy in list(combat.enemies):
                    dealt, extra_messages = self._deal_damage_to_enemy(run, combat, enemy, fire_breathing)
                    combat.log.append(f"Fire Breathing deals {dealt} damage to {enemy.name}.")
                    combat.log.extend(extra_messages)
                combat.enemies = self._prune_enemies(combat.enemies)

    def _discard_hand(self, run: RunState, combat: CombatState) -> None:
        retained: list[CardInstance] = []
        retain_all = combat.player_statuses.pop("retain_all", 0) > 0
        temporary_retain = set(str(entry) for entry in combat.player_meta.pop("temporary_retain", []))
        granted_retain = self._meta_id_set(combat, "granted_retain")
        for card in combat.hand:
            card_def = CARD_LIBRARY[card.key]
            if self.card_is_ethereal(card, combat):
                self._exhaust_card(None, combat, card)
            elif (
                self.card_retain(card)
                or retain_all
                or card.instance_id in temporary_retain
                or card.instance_id in granted_retain
                or "runic_pyramid" in run.relics
            ):
                retained.append(card)
            else:
                combat.discard_pile.append(card)
        establishment = combat.player_statuses.get("establishment", 0)
        for card in retained:
            if card.key == "perseverance":
                card.misc += 3 if card.upgraded else 2
            elif card.key == "windmill_strike":
                card.misc += 5 if card.upgraded else 4
            elif card.key == "sands_of_time":
                card.cost_adjustment -= 1
            if establishment > 0:
                card.cost_adjustment -= establishment
        if retained and "bookmark" in run.relics:
            chosen = self.rng.choice(retained)
            chosen.cost_adjustment -= 1
            combat.log.append(f"Bookmark reduces {self.card_name(chosen)} by 1.")
        combat.hand = retained

    def _resolve_victory(self, run: RunState) -> str:
        combat = self._require_combat(run)
        gold = combat.reward_gold
        if combat.encounter_kind == "elite":
            gold += 10
        if "golden_idol" in run.relics:
            gold = (gold * 5) // 4
        if combat.encounter_kind == "boss":
            run.combat = None
            self._gain_gold(run, gold + 100)
            healed, effect_messages = self._apply_post_combat_run_effects(run, combat)
            if run.act == 4:
                run.phase = "victory"
                run.push_log("The final boss falls. The climb is complete.")
                if healed:
                    run.push_log(f"End-of-combat healing restores {healed} HP.")
                for message in effect_messages:
                    run.push_log(message)
                return "The final boss falls. Victory."
            if run.act == self.ACT_COUNT and self.has_all_keys(run):
                run.combat = None
                run.act = 4
                run.act_floor = 0
                run.phase = "map"
                run.selection_context = None
                self._prepare_map_choices(run)
                run.push_log("The keys resonate. The Ending opens.")
                if healed:
                    run.push_log(f"End-of-combat healing restores {healed} HP.")
                for message in effect_messages:
                    run.push_log(message)
                if self._begin_forbidden_grimoire_removal(run, combat, resume_phase="map"):
                    return "The boss falls. Choose a card to remove."
                return "The keys unlock the path to The Ending."
            if run.act >= self.ACT_COUNT:
                run.phase = "victory"
                run.push_log("The final boss falls. The climb is complete.")
                if healed:
                    run.push_log(f"End-of-combat healing restores {healed} HP.")
                for message in effect_messages:
                    run.push_log(message)
                if self._begin_forbidden_grimoire_removal(run, combat, resume_phase="victory"):
                    return "The final boss falls. Choose a card to remove."
                return "The final boss falls. Victory."
            run.reward = RewardState(
                source="boss",
                gold=gold + 100,
                card_choices=self._roll_reward_cards(run, source="boss", boss=True),
                relic_choices=self._roll_boss_relic_choices(run),
            )
            run.phase = "reward"
            run.push_log(f"Act {run.act} boss defeated.")
            if healed:
                run.push_log(f"End-of-combat healing restores {healed} HP.")
            for message in effect_messages:
                run.push_log(message)
            if self._begin_forbidden_grimoire_removal(run, combat, resume_phase="reward"):
                return "The boss falls. Choose a card to remove."
            return "The boss falls. Choose a card reward."

        colosseum_stage = int(combat.player_meta.get("colosseum_stage", 0))
        if colosseum_stage == 1:
            healed, effect_messages = self._apply_post_combat_run_effects(run, combat)
            run.combat = None
            run.phase = "event"
            run.event = EventState(
                key="colosseum",
                name="Colosseum",
                description="The crowd chants for one more fight.",
                options=[
                    EventOptionState(
                        option_id="cowardice",
                        label="Cowardice",
                        description="Take your leave.",
                    ),
                    EventOptionState(
                        option_id="victory",
                        label="VICTORY",
                        description="Fight Taskmaster and Gremlin Nob for a larger reward.",
                    ),
                ],
            )
            run.push_log("Colosseum demands a second fight.")
            if healed:
                run.push_log(f"End-of-combat healing restores {healed} HP.")
            for message in effect_messages:
                run.push_log(message)
            if self._begin_forbidden_grimoire_removal(run, combat, resume_phase="event"):
                return "The first wave falls. Choose a card to remove."
            return "The first wave falls. The crowd demands more."
        if colosseum_stage == 2:
            gold += 100
            self._gain_gold(run, gold)
            healed, effect_messages = self._apply_post_combat_run_effects(run, combat)
            reward_cards = self._roll_reward_cards(run, source="elite")
            run.reward = RewardState(
                source="elite",
                gold=gold,
                card_choices=reward_cards,
            )
            run.combat = None
            run.phase = "reward"
            run.meta.pop("colosseum_stage", None)
            for rarity in ("uncommon", "rare"):
                relic_key = self._roll_relic_from_rarity(run, rarity)
                if relic_key is None:
                    relic_key, relic_messages = self._grant_random_relic(run)
                else:
                    relic_messages = self._obtain_relic(run, relic_key)
                run.push_log(f"Colosseum grants {RELIC_LIBRARY[relic_key].name}.")
                for message in relic_messages:
                    run.push_log(message)
            run.push_log(f"Combat won. Looted {gold} gold.")
            if healed:
                run.push_log(f"End-of-combat healing restores {healed} HP.")
            for message in effect_messages:
                run.push_log(message)
            potion = self._grant_random_potions(run, 1, chance=0.45)
            if potion:
                run.push_log(f"Potion found: {POTION_LIBRARY[potion[0]].name}.")
            if self._begin_forbidden_grimoire_removal(run, combat, resume_phase="reward"):
                return "Colosseum conquered. Choose a card to remove."
            return f"Colosseum conquered. You gain {gold} gold."

        self._gain_gold(run, gold)
        healed, effect_messages = self._apply_post_combat_run_effects(run, combat)
        reward_cards = self._roll_reward_cards(run, source=combat.encounter_kind)
        run.reward = RewardState(
            source=combat.encounter_kind,
            gold=gold,
            card_choices=reward_cards,
        )
        run.combat = None
        run.phase = "reward"
        if combat.encounter_kind == "combat" and "prayer_wheel" in run.relics:
            run.meta["prayer_wheel_rewards"] = int(run.meta.get("prayer_wheel_rewards", 0)) + 1
        run.push_log(f"Combat won. Looted {gold} gold.")
        if healed:
            run.push_log(f"End-of-combat healing restores {healed} HP.")
        for message in effect_messages:
            run.push_log(message)
        if combat.encounter_kind == "elite":
            if combat.player_meta.get("emerald_key_reward"):
                if not self.has_key(run, "emerald"):
                    run.keys.append("emerald")
                    run.push_log("Emerald Key claimed from the burning elite.")
            relic_key, relic_messages = self._grant_random_relic(run)
            run.push_log(f"Elite relic found: {RELIC_LIBRARY[relic_key].name}.")
            for message in relic_messages:
                run.push_log(message)
            if "black_star" in run.relics:
                bonus_key, bonus_messages = self._grant_random_relic(run)
                run.push_log(f"Black Star grants an extra relic: {RELIC_LIBRARY[bonus_key].name}.")
                for message in bonus_messages:
                    run.push_log(message)
            dead_adventurer = dict(combat.player_meta.get("dead_adventurer", {}))
            if dead_adventurer:
                if not dead_adventurer.get("found_gold", False):
                    self._gain_gold(run, 30)
                    if run.reward is not None:
                        run.reward.gold += 30
                    run.push_log("Dead Adventurer yields an extra 30 Gold.")
                if not dead_adventurer.get("found_relic", False):
                    bonus_relic_key, bonus_messages = self._grant_random_relic(run)
                    run.push_log(
                        f"Dead Adventurer yields an extra relic: {RELIC_LIBRARY[bonus_relic_key].name}."
                    )
                    for message in bonus_messages:
                        run.push_log(message)
        if combat.player_meta.get("masked_bandits_red_mask"):
            _, relic_messages = self._grant_specific_relic(run, "red_mask")
            run.push_log("Masked Bandits yield Red Mask.")
            for message in relic_messages:
                run.push_log(message)
        colored_reward = combat.player_meta.get("colored_mushrooms_reward")
        if colored_reward == "odd_mushroom":
            _, relic_messages = self._grant_specific_relic(run, "odd_mushroom")
            run.push_log("Colored Mushrooms yield Odd Mushroom.")
            for message in relic_messages:
                run.push_log(message)
        if combat.player_meta.get("mind_bloom_war"):
            relic_key = self._roll_relic_from_rarity(run, "rare")
            if relic_key is None:
                relic_key, relic_messages = self._grant_random_relic(run)
            else:
                relic_messages = self._obtain_relic(run, relic_key)
            run.push_log(f"Mind Bloom grants a rare relic: {RELIC_LIBRARY[relic_key].name}.")
            for message in relic_messages:
                run.push_log(message)
        if self._begin_forbidden_grimoire_removal(run, combat, resume_phase="reward"):
            return "Combat won. Choose a card to remove."
        if combat.player_meta.get("mysterious_sphere_rare_relic"):
            relic_key = self._roll_relic_from_rarity(run, "rare")
            if relic_key is None:
                relic_key, relic_messages = self._grant_random_relic(run)
            else:
                relic_messages = self._obtain_relic(run, relic_key)
            run.push_log(f"Mysterious Sphere grants a rare relic: {RELIC_LIBRARY[relic_key].name}.")
            for message in relic_messages:
                run.push_log(message)
        potion_chance = 1.0 if "white_beast_statue" in run.relics else 0.45
        potion = self._grant_random_potions(run, 1, chance=potion_chance)
        if potion:
            run.push_log(f"Potion found: {POTION_LIBRARY[potion[0]].name}.")
        return f"Combat won. You gain {gold} gold."

    def _reward_card_choice_count(self, run: RunState) -> int:
        count = 3
        if "question_card" in run.relics:
            count += 1
        if "busted_crown" in run.relics:
            count -= 2
        return max(1, count)

    def _reward_rare_offset(self, run: RunState) -> int:
        return int(run.meta.get("rare_chance_offset", -5))

    def _roll_reward_card_rarity(
        self,
        run: RunState,
        *,
        source: str,
        affect_offset: bool,
    ) -> str:
        if source == "boss":
            return "rare"
        base_rare = 10 if source == "elite" else 3
        if "nloths_gift" in run.relics and source in {"combat", "elite"}:
            base_rare *= 3
        rare_chance = max(0, min(100, base_rare + self._reward_rare_offset(run)))
        if self.rng.randrange(100) < rare_chance:
            if affect_offset:
                run.meta["rare_chance_offset"] = -5
            return "rare"
        if affect_offset:
            run.meta["rare_chance_offset"] = self._reward_rare_offset(run) + 1
        return "uncommon" if self.rng.randrange(100) < 37 else "common"

    def _pick_character_card(
        self,
        run: RunState,
        *,
        rarity: str | None = None,
        card_type: str | None = None,
        exclude: set[str] | None = None,
    ) -> str | None:
        exclude_keys = exclude or set()
        if "prismatic_shard" in run.relics:
            pool = [
                key
                for character in CHARACTER_LIBRARY.values()
                for key in character["card_pool"]
                if key not in exclude_keys
            ]
        else:
            pool = [
                key
                for key in CHARACTER_LIBRARY[run.character]["card_pool"]
                if key not in exclude_keys
            ]
        ordered_filters = [
            (card_type, rarity),
            (None, rarity),
            (card_type, None),
            (None, None),
        ]
        for filter_type, filter_rarity in ordered_filters:
            filtered = pool
            if filter_type is not None:
                filtered = [
                    key for key in filtered if CARD_LIBRARY[key].card_type == filter_type
                ]
            if filter_rarity is not None:
                filtered = [
                    key for key in filtered if CARD_LIBRARY[key].rarity == filter_rarity
                ]
            if filtered:
                return self.rng.choice(filtered)
        return None

    def _pick_colorless_card(
        self,
        *,
        rarity: str,
        exclude: set[str] | None = None,
    ) -> str | None:
        exclude_keys = exclude or set()
        character_cards = {
            key
            for character in CHARACTER_LIBRARY.values()
            for key in character["card_pool"]
        }
        pool = [
            key
            for key, card in CARD_LIBRARY.items()
            if key not in character_cards
            and key not in exclude_keys
            and card.rarity not in {"starter", "special", "status", "curse"}
        ]
        matching = [key for key in pool if CARD_LIBRARY[key].rarity == rarity]
        if matching:
            return self.rng.choice(matching)
        return self.rng.choice(pool) if pool else None

    def _roll_offer_cards(
        self,
        run: RunState,
        count: int,
        *,
        source: str,
    ) -> list[str]:
        choices: list[str] = []
        used: set[str] = set()
        for _ in range(count):
            rarity = self._roll_reward_card_rarity(
                run,
                source=source,
                affect_offset=False,
            )
            card_key = self._pick_character_card(run, rarity=rarity, exclude=used)
            if card_key is None:
                break
            used.add(card_key)
            choices.append(card_key)
        return choices

    def _roll_relic_from_rarity(self, run: RunState, *rarities: str) -> str | None:
        candidates = self._eligible_relic_candidates(
            run,
            TREASURE_RELIC_POOL,
            rarities=set(rarities),
        )
        if not candidates:
            return None
        return self.rng.choice(candidates)

    def _roll_reward_cards(
        self,
        run: RunState,
        *,
        source: str,
        boss: bool = False,
    ) -> list[str]:
        choices: list[str] = []
        used: set[str] = set()
        if boss:
            source = "boss"
        for _ in range(self._reward_card_choice_count(run)):
            rarity = self._roll_reward_card_rarity(
                run,
                source=source,
                affect_offset=not boss,
            )
            card_key = self._pick_character_card(run, rarity=rarity, exclude=used)
            if card_key is None:
                break
            used.add(card_key)
            choices.append(card_key)
        return choices

    def _roll_boss_relic_choices(self, run: RunState) -> list[str]:
        character_upgrade = {
            "ironclad": ("burning_blood", "black_blood"),
            "silent": ("ring_of_the_snake", "ring_of_the_serpent"),
            "defect": ("cracked_core", "frozen_core"),
            "watcher": ("pure_water", "holy_water"),
        }
        starter_key, upgrade_key = character_upgrade[run.character]
        character_upgrades = {upgrade for _, upgrade in character_upgrade.values()}
        candidates = [
            relic_key
            for relic_key in BOSS_RELIC_POOL
            if relic_key not in run.relics and relic_key not in character_upgrades
            and self._relic_matches_character(run, relic_key)
        ]
        if starter_key in run.relics and upgrade_key not in run.relics:
            candidates.append(upgrade_key)
        self.rng.shuffle(candidates)
        if len(candidates) < 3:
            filler = self._eligible_relic_candidates(
                run,
                TREASURE_RELIC_POOL,
                exclude=set(candidates),
            )
            self.rng.shuffle(filler)
            candidates.extend(filler)
        return candidates[:3]

    def _merchant_discount_multiplier(self, run: RunState) -> float:
        multiplier = 1.0
        if "membership_card" in run.relics:
            multiplier *= 0.5
        if "courier" in run.relics:
            multiplier *= 0.8
        return multiplier

    def _shop_price_from_base(
        self,
        run: RunState,
        *,
        base_cost: int,
        sale: bool = False,
    ) -> int:
        multiplier = self._merchant_discount_multiplier(run)
        if sale:
            multiplier *= 0.5
        return max(1, int(base_cost * multiplier))

    def _current_shop_remove_cost(self, run: RunState) -> int:
        base_cost = 50 if "smiling_mask" in run.relics else 75 + 25 * int(
            run.meta.get("shop_remove_uses", 0)
        )
        return self._shop_price_from_base(run, base_cost=base_cost)

    def _shop_card_base_cost(self, card_key: str, *, colorless: bool) -> int:
        rarity = CARD_LIBRARY[card_key].rarity
        if colorless:
            price_range = {
                "uncommon": (81, 99),
                "rare": (162, 198),
            }.get(rarity, (81, 99))
        else:
            price_range = {
                "common": (50, 60),
                "uncommon": (75, 85),
                "rare": (150, 160),
            }.get(rarity, (75, 85))
        return self.rng.randint(*price_range)

    def _weighted_rarity_choice(self, weights: dict[str, int]) -> str:
        total = sum(weights.values())
        roll = self.rng.randrange(total)
        running = 0
        for rarity, weight in weights.items():
            running += weight
            if roll < running:
                return rarity
        return next(iter(weights))

    def _roll_shop_relic_key(
        self,
        run: RunState,
        *,
        shop_only: bool,
        exclude: set[str] | None = None,
    ) -> str | None:
        exclude_keys = exclude or set()
        if shop_only:
            pool = self._eligible_relic_candidates(
                run,
                SHOP_RELIC_POOL,
                exclude=exclude_keys,
            )
            return self.rng.choice(pool) if pool else None
        candidates = self._eligible_relic_candidates(
            run,
            TREASURE_RELIC_POOL,
            exclude=exclude_keys,
            rarities={"common", "uncommon", "rare"},
        )
        if not candidates:
            return None
        buckets: dict[str, list[str]] = {"common": [], "uncommon": [], "rare": []}
        for relic_key in candidates:
            buckets[RELIC_LIBRARY[relic_key].rarity].append(relic_key)
        available_weights = {
            rarity: weight
            for rarity, weight in {"common": 48, "uncommon": 33, "rare": 19}.items()
            if buckets[rarity]
        }
        chosen_rarity = self._weighted_rarity_choice(available_weights)
        return self.rng.choice(buckets[chosen_rarity])

    def _roll_shop_potion_key(self, *, exclude: set[str] | None = None) -> str:
        exclude_keys = exclude or set()
        buckets: dict[str, list[str]] = {"common": [], "uncommon": [], "rare": []}
        for potion_key, potion in POTION_LIBRARY.items():
            if potion_key in exclude_keys:
                continue
            buckets[potion.rarity].append(potion_key)
        available_weights = {
            rarity: weight
            for rarity, weight in {"common": 65, "uncommon": 25, "rare": 10}.items()
            if buckets[rarity]
        }
        chosen_rarity = self._weighted_rarity_choice(available_weights)
        return self.rng.choice(buckets[chosen_rarity])

    def _make_shop_offer(
        self,
        run: RunState,
        *,
        offer_id: str,
        kind: str,
        key: str,
        base_cost: int,
        slot: str,
        sale: bool = False,
    ) -> ShopOffer:
        return ShopOffer(
            offer_id=offer_id,
            kind=kind,
            key=key,
            cost=self._shop_price_from_base(run, base_cost=base_cost, sale=sale),
            base_cost=base_cost,
            sale=sale,
            slot=slot,
        )

    def _refresh_shop_prices(self, run: RunState) -> None:
        if run.shop is None:
            return
        for offer in run.shop.offers:
            base_cost = offer.base_cost or offer.cost
            offer.base_cost = base_cost
            offer.cost = self._shop_price_from_base(
                run,
                base_cost=base_cost,
                sale=offer.sale,
            )
        run.shop.remove_cost = self._current_shop_remove_cost(run)

    def _restock_shop_offer(self, run: RunState, offer: ShopOffer) -> ShopOffer | None:
        if run.shop is None:
            return None
        exclude = {
            entry.key
            for entry in run.shop.offers
            if entry.offer_id != offer.offer_id
        }
        if offer.slot in {"attack", "skill", "power"}:
            rarity = self._roll_reward_card_rarity(
                run,
                source="shop",
                affect_offset=False,
            )
            card_key = self._pick_character_card(
                run,
                rarity=rarity,
                card_type=offer.slot,
                exclude=exclude,
            )
            if card_key is None:
                return None
            return self._make_shop_offer(
                run,
                offer_id=offer.offer_id,
                kind="card",
                key=card_key,
                base_cost=self._shop_card_base_cost(card_key, colorless=False),
                slot=offer.slot,
                sale=offer.sale,
            )
        if offer.slot == "colorless_uncommon":
            card_key = self._pick_colorless_card(rarity="uncommon", exclude=exclude)
            if card_key is None:
                return None
            return self._make_shop_offer(
                run,
                offer_id=offer.offer_id,
                kind="card",
                key=card_key,
                base_cost=self._shop_card_base_cost(card_key, colorless=True),
                slot=offer.slot,
            )
        if offer.slot == "colorless_rare":
            card_key = self._pick_colorless_card(rarity="rare", exclude=exclude)
            if card_key is None:
                return None
            return self._make_shop_offer(
                run,
                offer_id=offer.offer_id,
                kind="card",
                key=card_key,
                base_cost=self._shop_card_base_cost(card_key, colorless=True),
                slot=offer.slot,
            )
        if offer.slot == "relic":
            relic_key = self._roll_shop_relic_key(run, shop_only=False, exclude=exclude)
            if relic_key is None:
                return None
            return self._make_shop_offer(
                run,
                offer_id=offer.offer_id,
                kind="relic",
                key=relic_key,
                base_cost=RELIC_LIBRARY[relic_key].shop_cost,
                slot=offer.slot,
            )
        if offer.slot == "shop_relic":
            relic_key = self._roll_shop_relic_key(run, shop_only=True, exclude=exclude)
            if relic_key is None:
                return None
            return self._make_shop_offer(
                run,
                offer_id=offer.offer_id,
                kind="relic",
                key=relic_key,
                base_cost=RELIC_LIBRARY[relic_key].shop_cost,
                slot=offer.slot,
            )
        if offer.slot == "potion":
            potion_key = self._roll_shop_potion_key(exclude=exclude)
            return self._make_shop_offer(
                run,
                offer_id=offer.offer_id,
                kind="potion",
                key=potion_key,
                base_cost=POTION_LIBRARY[potion_key].shop_cost,
                slot=offer.slot,
            )
        return None

    def _open_shop(self, run: RunState) -> None:
        offers: list[ShopOffer] = []
        class_offers: list[ShopOffer] = []
        used_card_keys: set[str] = set()
        for index, card_type in enumerate(
            ["attack", "attack", "skill", "skill", "power"],
            start=1,
        ):
            rarity = self._roll_reward_card_rarity(
                run,
                source="shop",
                affect_offset=False,
            )
            card_key = self._pick_character_card(
                run,
                rarity=rarity,
                card_type=card_type,
                exclude=used_card_keys,
            )
            if card_key is None:
                continue
            used_card_keys.add(card_key)
            class_offers.append(
                self._make_shop_offer(
                    run,
                    offer_id=f"class_{index}",
                    kind="card",
                    key=card_key,
                    base_cost=self._shop_card_base_cost(card_key, colorless=False),
                    slot=card_type,
                )
            )
        if class_offers:
            self.rng.choice(class_offers).sale = True
        offers.extend(class_offers)

        for index, rarity in enumerate(("uncommon", "rare"), start=1):
            colorless_key = self._pick_colorless_card(
                rarity=rarity,
                exclude=used_card_keys,
            )
            if colorless_key is None:
                continue
            used_card_keys.add(colorless_key)
            offers.append(
                self._make_shop_offer(
                    run,
                    offer_id=f"colorless_{index}",
                    kind="card",
                    key=colorless_key,
                    base_cost=self._shop_card_base_cost(colorless_key, colorless=True),
                    slot=f"colorless_{rarity}",
                )
            )

        used_relic_keys: set[str] = set()
        for index in range(1, 3):
            relic_key = self._roll_shop_relic_key(
                run,
                shop_only=False,
                exclude=used_relic_keys,
            )
            if relic_key is None:
                continue
            used_relic_keys.add(relic_key)
            offers.append(
                self._make_shop_offer(
                    run,
                    offer_id=f"relic_{index}",
                    kind="relic",
                    key=relic_key,
                    base_cost=RELIC_LIBRARY[relic_key].shop_cost,
                    slot="relic",
                )
            )
        shop_relic_key = self._roll_shop_relic_key(
            run,
            shop_only=True,
            exclude=used_relic_keys,
        )
        if shop_relic_key is not None:
            offers.append(
                self._make_shop_offer(
                    run,
                    offer_id="shop_relic_1",
                    kind="relic",
                    key=shop_relic_key,
                    base_cost=RELIC_LIBRARY[shop_relic_key].shop_cost,
                    slot="shop_relic",
                )
            )

        used_potion_keys: set[str] = set()
        for index in range(1, 4):
            potion_key = self._roll_shop_potion_key(exclude=used_potion_keys)
            used_potion_keys.add(potion_key)
            offers.append(
                self._make_shop_offer(
                    run,
                    offer_id=f"potion_{index}",
                    kind="potion",
                    key=potion_key,
                    base_cost=POTION_LIBRARY[potion_key].shop_cost,
                    slot="potion",
                )
            )
        run.shop = ShopState(
            offers=offers,
            remove_cost=self._current_shop_remove_cost(run),
        )
        self._refresh_shop_prices(run)
        run.phase = "shop"
        run.selection_context = None

    def _open_event(self, run: RunState) -> str:
        if "juzu_bracelet" not in run.relics:
            monster_chance = int(run.meta.get("question_monster_chance", 10))
            if self.rng.randrange(100) < monster_chance:
                run.meta["question_monster_chance"] = 10
                self.start_specific_combat(run, self._roll_common_encounter(run), "combat")
                run.push_log("A monster emerges from a ? room.")
                return "A lurking enemy attacks from the shadows."
            run.meta["question_monster_chance"] = min(100, monster_chance + 10)
        event_keys = [
            "augmenter",
            "big_fish",
            "bonfire_spirits",
            "colosseum",
            "council_of_ghosts",
            "dead_adventurer",
            "designer_inspire",
            "duplicator",
            "divine_fountain",
            "falling",
            "face_trader",
            "forgotten_altar",
            "golden_idol_event",
            "golden_shrine",
            "hypnotizing_colored_mushrooms",
            "knowing_skull",
            "lab",
            "living_wall",
            "masked_bandits",
            "mind_bloom",
            "mysterious_sphere",
            "moai_head",
            "nest",
            "nloth",
            "old_beggar",
            "ominous_forge",
            "pleading_vagrant",
            "purifier",
            "scrap_ooze",
            "sensory_stone",
            "secret_portal",
            "shining_light",
            "the_joust",
            "the_cleric",
            "the_library",
            "the_mausoleum",
            "the_ssssserpent",
            "the_woman_in_blue",
            "tomb_of_lord_red_mask",
            "transmogrifier",
            "upgrade_shrine",
            "we_meet_again",
            "wing_statue",
            "winding_halls",
            "world_of_goop",
        ]
        if run.gold < 50:
            event_keys = [key for key in event_keys if key != "the_woman_in_blue"]
        if run.gold < 50:
            event_keys = [key for key in event_keys if key != "the_joust"]
        if run.gold < 75:
            event_keys = [key for key in event_keys if key != "old_beggar"]
        if run.gold < 75:
            event_keys = [key for key in event_keys if key != "designer_inspire"]
        if run.hp <= 12:
            event_keys = [key for key in event_keys if key != "knowing_skull"]
        if "golden_idol" in run.relics:
            event_keys = [key for key in event_keys if key != "golden_idol_event"]
        else:
            event_keys = [key for key in event_keys if key != "moai_head"]
        if any(card.key == "ritual_dagger" for card in run.deck):
            event_keys = [key for key in event_keys if key != "nest"]
        if len(run.relics) < 2:
            event_keys = [key for key in event_keys if key != "nloth"]
        if not any(CARD_LIBRARY[card.key].rarity == "curse" for card in run.deck):
            event_keys = [key for key in event_keys if key != "divine_fountain"]
        if run.act != 1:
            event_keys = [
                key
                for key in event_keys
                if key
                not in {
                    "big_fish",
                    "dead_adventurer",
                    "golden_idol_event",
                    "golden_shrine",
                    "hypnotizing_colored_mushrooms",
                    "scrap_ooze",
                    "shining_light",
                    "wing_statue",
                    "world_of_goop",
                }
            ]
        if run.act != 2:
            event_keys = [
                key
                for key in event_keys
                if key
                not in {
                    "augmenter",
                    "colosseum",
                    "council_of_ghosts",
                    "forgotten_altar",
                    "living_wall",
                    "masked_bandits",
                    "nest",
                    "nloth",
                    "old_beggar",
                    "pleading_vagrant",
                    "the_joust",
                    "the_library",
                    "the_mausoleum",
                    "the_ssssserpent",
                    "wheel_of_change",
                    "winding_halls",
                }
            ]
        if run.act != 3:
            event_keys = [
                key
                for key in event_keys
                if key
                not in {
                    "falling",
                    "mind_bloom",
                    "mysterious_sphere",
                    "moai_head",
                    "sensory_stone",
                    "secret_portal",
                    "tomb_of_lord_red_mask",
                }
            ]
        if run.act != 2:
            event_keys = [key for key in event_keys if key != "knowing_skull"]
        if run.act not in {1, 2}:
            event_keys = [key for key in event_keys if key != "face_trader"]
        if run.act not in {2, 3}:
            event_keys = [key for key in event_keys if key != "designer_inspire"]
        if not any(CARD_LIBRARY[card.key].card_type == "power" for card in run.deck):
            event_keys = [key for key in event_keys if key != "falling"]
        event_key = self.rng.choice(event_keys or list(EVENT_LIBRARY))
        event_def = EVENT_LIBRARY[event_key]
        options = [
            EventOptionState(
                option_id=option.key,
                label=option.label,
                description=option.description,
            )
            for option in event_def.options
        ]
        if event_key == "wing_statue":
            can_pray = any(
                CARD_LIBRARY[card.key].card_type == "attack"
                and self.card_damage_value(card) >= 10
                for card in run.deck
            )
            if not can_pray:
                options = [option for option in options if option.option_id != "pray"]
        if event_key == "tomb_of_lord_red_mask":
            if "red_mask" in run.relics:
                options = [option for option in options if option.option_id in {"don", "leave"}]
            else:
                options = [option for option in options if option.option_id in {"offer", "leave"}]
        if event_key == "mind_bloom":
            if run.floor <= 40:
                options = [option for option in options if option.option_id != "healthy"]
            else:
                options = [option for option in options if option.option_id != "rich"]
        if event_key == "forgotten_altar":
            if "golden_idol" in run.relics:
                options = [option for option in options if option.option_id != "sacrifice"]
            else:
                options = [option for option in options if option.option_id != "offer_idol"]
        if event_key == "designer_inspire":
            filtered: list[EventOptionState] = []
            for option in options:
                if option.option_id == "adjustments" and run.gold < 40:
                    continue
                if option.option_id == "clean_up" and run.gold < 60:
                    continue
                if option.option_id == "full_service" and run.gold < 90:
                    continue
                filtered.append(option)
            options = filtered
        if event_key == "nloth":
            relic_candidates = [key for key in run.relics if key != "nloths_gift"]
            self.rng.shuffle(relic_candidates)
            options = [
                EventOptionState(
                    option_id=f"trade:{relic_key}",
                    label=f"Trade {RELIC_LIBRARY[relic_key].name}",
                    description="Lose this relic. Obtain N'loth's Gift.",
                )
                for relic_key in relic_candidates[:2]
            ]
            options.append(
                EventOptionState(
                    option_id="leave",
                    label="Leave",
                    description="Refuse the bargain.",
                )
            )
        if event_key == "moai_head":
            options = [option for option in options if option.option_id != "offer" or "golden_idol" in run.relics]
        if event_key == "scrap_ooze":
            state = dict(run.meta.get("scrap_ooze", {}))
            hp_loss = int(state.get("hp_loss", 3))
            chance = int(state.get("chance", 25))
            options = [
                EventOptionState(
                    option_id="reach",
                    label="Reach",
                    description=f"Lose {hp_loss} HP. {chance}% chance for a relic.",
                ),
                EventOptionState(
                    option_id="leave",
                    label="Leave",
                    description="Back away from the ooze.",
                ),
            ]
        if event_key == "knowing_skull":
            run.meta.setdefault("knowing_skull", {})
            self._refresh_knowing_skull_event(run)
            run.phase = "event"
            return "A strange room waits."
        if event_key == "we_meet_again":
            payload: dict[str, object] = {}
            options = []
            if run.potions:
                potion_key = self.rng.choice(run.potions)
                payload["potion_key"] = potion_key
                options.append(
                    EventOptionState(
                        option_id="give_potion",
                        label=f"Give {POTION_LIBRARY[potion_key].name}",
                        description="Lose the potion. Obtain a relic.",
                    )
                )
            if run.gold > 0:
                gold_cost = min(run.gold, self.rng.choice([50, 75, 100, 150]))
                payload["gold_cost"] = gold_cost
                options.append(
                    EventOptionState(
                        option_id="give_gold",
                        label=f"Give {gold_cost} Gold",
                        description="Lose the Gold. Obtain a relic.",
                    )
                )
            card_candidates = [
                card
                for card in run.deck
                if CARD_LIBRARY[card.key].rarity not in {"starter", "curse"}
            ]
            if card_candidates:
                card = self.rng.choice(card_candidates)
                payload["card_id"] = card.instance_id
                options.append(
                    EventOptionState(
                        option_id="give_card",
                        label=f"Give {self.card_name(card)}",
                        description="Lose the card. Obtain a relic.",
                    )
                )
            options.append(
                EventOptionState(
                    option_id="attack",
                    label="Attack",
                    description="Try to catch them before they vanish.",
                )
            )
            run.meta["we_meet_again"] = payload
        if event_key == "falling":
            options = []
            grouped_choices: list[tuple[str, CardInstance]] = []
            for card_type, label in (
                ("attack", "Attack"),
                ("skill", "Skill"),
                ("power", "Power"),
            ):
                candidates = [card for card in run.deck if CARD_LIBRARY[card.key].card_type == card_type]
                if not candidates:
                    continue
                chosen = self.rng.choice(candidates)
                grouped_choices.append((label, chosen))
            for label, card in grouped_choices:
                options.append(
                    EventOptionState(
                        option_id=card.instance_id,
                        label=f"Lose {self.card_name(card)}",
                        description=f"Drop a {label.lower()} card into the abyss.",
                    )
                )
        run.event = EventState(
            key=event_key,
            name=event_def.name,
            description=event_def.description,
            options=options,
        )
        run.phase = "event"
        return "A strange room waits."

    def _grant_random_relic_preview(self, run: RunState) -> tuple[str, list[str]]:
        candidates = self._eligible_relic_candidates(run, TREASURE_RELIC_POOL)
        if not candidates:
            return run.relics[0], []
        relic_key = self.rng.choice(candidates)
        return relic_key, []

    def _grant_specific_relic(self, run: RunState, relic_key: str) -> tuple[str, list[str]]:
        return relic_key, self._obtain_relic(run, relic_key)

    def _grant_random_relic(self, run: RunState) -> tuple[str, list[str]]:
        relic_key, _ = self._grant_random_relic_preview(run)
        return self._grant_specific_relic(run, relic_key)

    def _remove_relic(self, run: RunState, relic_key: str) -> bool:
        if relic_key not in run.relics:
            return False
        run.relics = [key for key in run.relics if key != relic_key]
        if relic_key == "omamori":
            run.meta.pop("omamori_charges", None)
        if relic_key in {"bottled_flame", "bottled_lightning", "bottled_tornado"}:
            run.meta.pop(f"{relic_key}_card", None)
        return True

    def _grant_random_potions(
        self,
        run: RunState,
        count: int,
        *,
        chance: float = 1.0,
    ) -> list[str]:
        if "sozu" in run.relics:
            return []
        gained: list[str] = []
        for _ in range(count):
            if len(run.potions) >= self._max_potion_slots(run) or self.rng.random() > chance:
                break
            potion_key = self.rng.choice(POTION_POOL)
            run.potions.append(potion_key)
            gained.append(potion_key)
        return gained

    def _obtain_relic(self, run: RunState, relic_key: str) -> list[str]:
        if relic_key in run.relics:
            return []
        starter_replacements = {
            "black_blood": "burning_blood",
            "ring_of_the_serpent": "ring_of_the_snake",
            "frozen_core": "cracked_core",
            "holy_water": "pure_water",
            "phylactery_unbound": "bound_phylactery",
        }
        replaced = starter_replacements.get(relic_key)
        if replaced in run.relics:
            run.relics = [key for key in run.relics if key != replaced]
        run.relics.append(relic_key)
        messages: list[str] = []
        if relic_key == "omamori":
            run.meta["omamori_charges"] = int(run.meta.get("omamori_charges", 0)) + 2
        max_hp_bonus = {
            "strawberry": 7,
            "pear": 10,
            "mango": 14,
            "lees_waffle": 7,
        }.get(relic_key, 0)
        if max_hp_bonus:
            if relic_key == "lees_waffle":
                self._increase_max_hp(run, max_hp_bonus)
                run.hp = run.max_hp if self._can_heal_run(run) else min(run.hp, run.max_hp)
            else:
                self._increase_max_hp(run, max_hp_bonus)
            messages.append(f"Max HP increases by {max_hp_bonus}.")
            if relic_key == "lees_waffle" and self._can_heal_run(run):
                messages.append("Lee's Waffle heals you to full.")
        if relic_key == "old_coin":
            gained = self._gain_gold(run, 300)
            messages.append(
                f"Old Coin grants {gained} Gold." if gained > 0 else "Ectoplasm prevents Old Coin from granting Gold."
            )
        if relic_key == "war_paint":
            messages.extend(self._upgrade_random_cards(run, "skill", 2))
        if relic_key == "whetstone":
            messages.extend(self._upgrade_random_cards(run, "attack", 2))
        if relic_key == "cauldron":
            gained = self._grant_random_potions(run, 5)
            if gained:
                names = ", ".join(POTION_LIBRARY[key].name for key in gained)
                messages.append(f"Cauldron brews {names}.")
        if relic_key == "pandoras_box":
            transformed = 0
            for target in list(run.deck):
                if target.key not in {"strike", "defend"}:
                    continue
                replacement_key = self._roll_transform_card_key(run, target)
                if replacement_key is None:
                    continue
                run.deck = [card for card in run.deck if card.instance_id != target.instance_id]
                replacement = self.create_card_instance(run, replacement_key)
                messages.extend(self._add_card_to_deck(run, replacement))
                transformed += 1
            messages.append(f"Pandora's Box transforms {transformed} card(s).")
        if relic_key == "astrolabe":
            run.phase = "remove"
            run.selection_context = "astrolabe:3"
            messages.append("Choose 3 cards to transform and upgrade.")
        if relic_key == "empty_cage":
            run.phase = "remove"
            run.selection_context = "empty_cage:2"
            messages.append("Choose 2 cards to remove.")
        if relic_key == "calling_bell":
            messages.extend(self._add_card_to_deck(run, self.create_card_instance(run, "curse_of_the_bell")))
            seen: set[str] = set()
            for rarity in ("common", "uncommon", "rare"):
                relic_options = self._eligible_relic_candidates(
                    run,
                    TREASURE_RELIC_POOL,
                    exclude=seen,
                    rarities={rarity},
                )
                if not relic_options:
                    break
                bonus_key = self.rng.choice(relic_options)
                seen.add(bonus_key)
                messages.append(f"Calling Bell grants {RELIC_LIBRARY[bonus_key].name}.")
                messages.extend(self._obtain_relic(run, bonus_key))
        if relic_key == "tiny_house":
            self._increase_max_hp(run, 5)
            gained = self._gain_gold(run, 50)
            messages.append(
                f"Tiny House grants {gained} Gold." if gained > 0 else "Ectoplasm prevents Tiny House from granting Gold."
            )
            potions = self._grant_random_potions(run, 1)
            if potions:
                messages.append(f"Tiny House grants {POTION_LIBRARY[potions[0]].name}.")
            upgrades = self._upgrade_random_unupgraded_cards(run, 1)
            messages.extend(upgrades)
            run.reward = RewardState(
                source="tiny_house",
                gold=0,
                card_choices=self._roll_reward_cards(run, source="combat"),
            )
            run.phase = "reward"
        if relic_key in {"bottled_flame", "bottled_lightning", "bottled_tornado"}:
            self._remember_delayed_choice_return(run)
            run.phase = "remove"
            run.selection_context = f"bottle:{relic_key}"
            messages.append(f"Choose a card for {RELIC_LIBRARY[relic_key].name}.")
        if relic_key == "dollys_mirror":
            self._remember_delayed_choice_return(run)
            run.phase = "remove"
            run.selection_context = "dollys_mirror"
            messages.append("Choose a card to duplicate.")
        if relic_key == "orrery":
            self._remember_delayed_choice_return(run)
            run.meta["orrery_remaining"] = 5
            run.reward = RewardState(
                source="orrery",
                gold=0,
                card_choices=self._roll_reward_cards(run, source="combat"),
            )
            run.phase = "reward"
            messages.append("Orrery offers 5 card choices.")
        return messages

    def _upgrade_random_cards(
        self,
        run: RunState,
        card_type: str,
        count: int,
    ) -> list[str]:
        candidates = [
            card
            for card in run.deck
            if not card.upgraded and CARD_LIBRARY[card.key].card_type == card_type
        ]
        if not candidates:
            return []
        self.rng.shuffle(candidates)
        upgraded_cards = candidates[:count]
        messages: list[str] = []
        for card in upgraded_cards:
            card.upgraded = True
            messages.append(f"{self.card_name(card)} is upgraded.")
        return messages

    def _upgrade_random_unupgraded_cards(self, run: RunState, count: int) -> list[str]:
        candidates = [card for card in run.deck if not card.upgraded]
        if not candidates:
            return []
        self.rng.shuffle(candidates)
        messages: list[str] = []
        for card in candidates[:count]:
            card.upgraded = True
            messages.append(f"{self.card_name(card)} is upgraded.")
        return messages

    def _resolve_mantra(
        self,
        run: RunState | None,
        combat: CombatState,
    ) -> list[str]:
        mantra = combat.player_statuses.get("mantra", 0)
        if mantra < 10 or combat.stance == "divinity":
            return []
        combat.player_statuses["mantra"] = 0
        combat.stance = "divinity"
        combat.energy += 3
        return ["You enter Divinity and gain 3 Energy."]

    def _exhaust_card(
        self,
        run: RunState | None,
        combat: CombatState,
        card: CardInstance,
        *,
        trigger_block: bool = True,
    ) -> list[str]:
        combat.exhaust_pile.append(card)
        messages = [f"{self.card_name(card)} is exhausted."]
        feel_no_pain = combat.player_statuses.get("feel_no_pain", 0)
        if trigger_block and feel_no_pain > 0:
            if run is not None:
                self._gain_player_block(
                    run,
                    combat,
                    feel_no_pain,
                    messages,
                    message="Feel No Pain grants {gained} Block.",
                )
            else:
                gained = self._compute_block_gain(feel_no_pain, combat.player_statuses)
                combat.player_block += gained
                messages.append(f"Feel No Pain grants {gained} Block.")
        dark_embrace = combat.player_statuses.get("dark_embrace", 0)
        if dark_embrace > 0:
            self._draw_cards(run, combat, dark_embrace)
            messages.append(f"Dark Embrace draws {dark_embrace} card(s).")
        if card.key == "sentinel":
            gained_energy = 3 if card.upgraded else 2
            combat.energy += gained_energy
            messages.append(f"Sentinel grants {gained_energy} Energy.")
        if run is not None and "charons_ashes" in run.relics:
            for enemy in list(combat.enemies):
                dealt, extra_messages = self._deal_damage_to_enemy(run, combat, enemy, 3)
                messages.append(f"Charon's Ashes deals {dealt} damage to {enemy.name}.")
                messages.extend(extra_messages)
            combat.enemies = self._prune_enemies(combat.enemies)
        if run is not None and "dead_branch" in run.relics:
            candidates = [
                key
                for key, card_def in CARD_LIBRARY.items()
                if card_def.rarity not in {"starter", "status", "curse", "special"}
            ]
            if candidates:
                created_key = self.rng.choice(candidates)
                messages.extend(
                    self._create_cards_in_combat(run, combat, key=created_key, location="hand", count=1)
                )
        return messages

    def _handle_card_play_triggers(
        self,
        run: RunState,
        combat: CombatState,
        card_def,
    ) -> list[str]:
        messages: list[str] = []
        if "ink_bottle" in run.relics:
            counter = combat.player_statuses.get("ink_bottle_counter", 0) + 1
            if counter >= 10:
                counter = 0
                self._draw_cards(run, combat, 1)
                messages.append("Ink Bottle draws 1 card.")
            combat.player_statuses["ink_bottle_counter"] = counter
        a_thousand_cuts = combat.player_statuses.get("a_thousand_cuts", 0)
        if a_thousand_cuts > 0:
            for enemy in list(combat.enemies):
                dealt, extra_messages = self._deal_damage_to_enemy(
                    run,
                    combat,
                    enemy,
                    a_thousand_cuts,
                )
                messages.append(f"A Thousand Cuts deals {dealt} damage to {enemy.name}.")
                messages.extend(extra_messages)
            combat.enemies = self._prune_enemies(combat.enemies)
        after_image = combat.player_statuses.get("after_image", 0)
        if after_image > 0:
            self._gain_player_block(
                run,
                combat,
                after_image,
                messages,
                message="After Image grants {gained} Block.",
            )
        panache = combat.player_statuses.get("panache", 0)
        if panache > 0 and combat.player_statuses.get("cards_played_turn", 0) % 5 == 0:
            for enemy in list(combat.enemies):
                dealt, extra_messages = self._deal_damage_to_enemy(run, combat, enemy, panache)
                messages.append(f"Panache deals {dealt} damage to {enemy.name}.")
                messages.extend(extra_messages)
            combat.enemies = self._prune_enemies(combat.enemies)
        if card_def.card_type == "attack":
            rage = combat.player_statuses.get("rage", 0)
            if rage > 0:
                self._gain_player_block(
                    run,
                    combat,
                    rage,
                    messages,
                    message="Rage grants {gained} Block.",
                )
            count = combat.player_statuses.get("attacks_played_turn", 0) + 1
            combat.player_statuses["attacks_played_turn"] = count
            if "nunchaku" in run.relics:
                nunchaku = combat.player_statuses.get("nunchaku_counter", 0) + 1
                combat.player_statuses["nunchaku_counter"] = nunchaku % 10
                if nunchaku % 10 == 0:
                    combat.energy += 1
                    messages.append("Nunchaku grants 1 Energy.")
            if "pen_nib" in run.relics and combat.player_meta.get("double_attack_damage_card") is None:
                combat.player_statuses["pen_nib_counter"] = min(
                    9,
                    combat.player_statuses.get("pen_nib_counter", 0) + 1,
                )
            if count % 3 == 0:
                if "shuriken" in run.relics:
                    combat.player_statuses["strength"] = (
                        combat.player_statuses.get("strength", 0) + 1
                    )
                    messages.append("Shuriken grants 1 Strength.")
                if "kunai" in run.relics:
                    combat.player_statuses["dexterity"] = (
                        combat.player_statuses.get("dexterity", 0) + 1
                    )
                    messages.append("Kunai grants 1 Dexterity.")
                if "ornamental_fan" in run.relics:
                    self._gain_player_block(
                        run,
                        combat,
                        4,
                        messages,
                        message="Ornamental Fan grants {gained} Block.",
                    )
        elif card_def.card_type == "skill":
            count = combat.player_statuses.get("skills_played_turn", 0) + 1
            combat.player_statuses["skills_played_turn"] = count
            if count % 3 == 0 and "letter_opener" in run.relics:
                for enemy in list(combat.enemies):
                    dealt, extra_messages = self._deal_damage_to_enemy(run, combat, enemy, 5)
                    messages.append(f"Letter Opener deals {dealt} damage to {enemy.name}.")
                    messages.extend(extra_messages)
                combat.enemies = self._prune_enemies(combat.enemies)
        elif card_def.card_type == "power":
            combat.player_statuses["powers_played_combat"] = (
                combat.player_statuses.get("powers_played_combat", 0) + 1
            )
            if "bird_faced_urn" in run.relics:
                healed = self._heal_run(run, 2)
                self._sync_player_hp_relics(run, combat, messages)
                if healed > 0:
                    messages.append(f"Bird-Faced Urn heals {healed} HP.")
            heatsinks = combat.player_statuses.get("heatsinks", 0)
            if heatsinks > 0:
                self._draw_cards(run, combat, heatsinks)
                messages.append(f"Heatsinks draws {heatsinks} card(s).")
            storm = combat.player_statuses.get("storm", 0)
            for _ in range(storm):
                messages.extend(self._channel_orb(combat, "lightning"))
                messages.append("Lightning orb is channeled.")
            if "mummified_hand" in run.relics:
                candidates = [card for card in combat.hand if self.card_cost(card, combat) > 0]
                if candidates:
                    chosen = self.rng.choice(candidates)
                    self._set_card_cost(chosen, max(0, self.card_cost(chosen, combat) - 1))
                    messages.append(f"Mummified Hand reduces {self.card_name(chosen)} by 1.")
            for enemy in combat.enemies:
                reaction = enemy.meta.get("power_reaction_strength", 0)
                if reaction > 0:
                    enemy.statuses["strength"] = enemy.statuses.get("strength", 0) + reaction
                    messages.append(f"{enemy.name} gains {reaction} Strength from your power.")
        if card_def.card_type in {"attack", "skill", "power"} and "orange_pellets" in run.relics:
            combat.player_statuses[f"orange_pellets_{card_def.card_type}"] = 1
            if (
                combat.player_statuses.get("orange_pellets_used_turn", 0) <= 0
                and all(
                    combat.player_statuses.get(f"orange_pellets_{card_type}", 0) > 0
                    for card_type in ("attack", "skill", "power")
                )
            ):
                self._clear_debuffs(combat.player_statuses)
                combat.player_statuses["orange_pellets_used_turn"] = 1
                messages.append("Orange Pellets removes your debuffs.")
        active_id = str(combat.player_meta.get("active_card_instance_id", ""))
        granted_retain = self._meta_id_set(combat, "granted_retain")
        if active_id in granted_retain:
            granted_retain.remove(active_id)
            self._store_meta_id_set(combat, "granted_retain", granted_retain)
        granted_ethereal = self._meta_id_set(combat, "granted_ethereal")
        played_ethereal = card_def.ethereal or active_id in granted_ethereal
        if active_id in granted_ethereal:
            granted_ethereal.remove(active_id)
            self._store_meta_id_set(combat, "granted_ethereal", granted_ethereal)
        played_cost = int(combat.player_meta.get("played_card_cost", 0))
        if played_ethereal:
            combat.player_statuses["ethereal_played_combat"] = combat.player_statuses.get("ethereal_played_combat", 0) + 1
            spirit = combat.player_statuses.get("spirit_of_ash", 0)
            if spirit > 0:
                self._gain_player_block(run, combat, spirit, messages, message="Spirit Of Ash grants {gained} Block.")
        if card_def.key == "soul":
            haunt = combat.player_statuses.get("haunt", 0)
            alive = [enemy for enemy in combat.enemies if enemy.hp > 0]
            if haunt > 0 and alive:
                target = self.rng.choice(alive)
                dealt, extra_messages = self._deal_damage_to_enemy(run, combat, target, haunt)
                messages.append(f"Haunt deals {dealt} damage to {target.name}.")
                messages.extend(extra_messages)
                combat.enemies = self._prune_enemies(combat.enemies)
            devour_life = combat.player_statuses.get("devour_life", 0)
            if devour_life > 0:
                gained = self._summon_osty(combat, devour_life)
                messages.append(f"Devour Life summons {gained}.")
        if played_cost >= 2 and combat.player_statuses.get("danse_macabre", 0) > 0:
            self._gain_player_block(
                run,
                combat,
                combat.player_statuses["danse_macabre"],
                messages,
                message="Danse Macabre grants {gained} Block.",
            )
        if played_cost >= 3 and "ivory_tile" in run.relics:
            combat.energy += 1
            messages.append("Ivory Tile grants 1 Energy.")
        if played_cost >= 2 and card_def.key != "right_hand_hand":
            returned = [card for card in list(combat.discard_pile) if card.key == "right_hand_hand"]
            for card in returned:
                combat.discard_pile.remove(card)
                combat.hand.append(card)
                messages.append("Right Hand Hand returns to your hand.")
        if card_def.key != "oblivion" and combat.player_statuses.get("oblivion", 0) > 0:
            target = next(
                (enemy for enemy in combat.enemies if enemy.enemy_id == combat.last_target_enemy_id and enemy.hp > 0),
                self._default_target_enemy(combat),
            )
            if target is not None:
                messages.extend(
                    self._apply_status_from_action(
                        run,
                        combat,
                        target="enemy",
                        status="doom",
                        value=combat.player_statuses["oblivion"],
                        target_enemy=target,
                    )
                )
        combat.player_statuses["last_card_attack"] = 1 if card_def.card_type == "attack" else 0
        combat.player_statuses["last_card_skill"] = 1 if card_def.card_type == "skill" else 0
        return messages

    def _create_cards_in_combat(
        self,
        run: RunState,
        combat: CombatState,
        *,
        key: str,
        location: str,
        count: int,
        upgraded: bool = False,
        misc: int = 0,
    ) -> list[str]:
        messages: list[str] = []
        for _ in range(count):
            make_upgraded = upgraded or combat.player_statuses.get("master_reality", 0) > 0
            new_card = self.create_card_instance(run, key, upgraded=make_upgraded, misc=misc)
            if location == "discard":
                combat.discard_pile.append(new_card)
            elif location == "hand":
                combat.hand.append(new_card)
            elif location == "draw":
                combat.draw_pile.append(new_card)
            else:
                raise ValueError(f"Unsupported card location: {location}")
            messages.append(f"{self.card_name(new_card)} is created in your {location}.")
        return messages

    def _create_random_cards_in_combat(
        self,
        run: RunState,
        combat: CombatState,
        *,
        pool: str,
        location: str,
        count: int = 1,
        card_type: str | None = None,
    ) -> list[str]:
        if pool == "character_common":
            candidates = [
                key
                for key in CHARACTER_LIBRARY[run.character]["card_pool"]
                if CARD_LIBRARY[key].rarity == "common"
            ]
        elif pool == "character":
            candidates = list(CHARACTER_LIBRARY[run.character]["card_pool"])
        elif pool == "colorless":
            character_cards = {
                key
                for character in CHARACTER_LIBRARY.values()
                for key in character["card_pool"]
            }
            candidates = [
                key
                for key, card in CARD_LIBRARY.items()
                if key not in character_cards
                and card.rarity not in {"starter", "special", "status", "curse"}
            ]
        elif pool == "character_power":
            candidates = [
                key
                for key in CHARACTER_LIBRARY[run.character]["card_pool"]
                if CARD_LIBRARY[key].card_type == "power"
            ]
        elif pool == "character_skill":
            candidates = [
                key
                for key in CHARACTER_LIBRARY[run.character]["card_pool"]
                if CARD_LIBRARY[key].card_type == "skill"
            ]
        elif pool == "character_attack":
            candidates = [
                key
                for key in CHARACTER_LIBRARY[run.character]["card_pool"]
                if CARD_LIBRARY[key].card_type == "attack"
            ]
        else:
            candidates = []
        if card_type is not None:
            candidates = [key for key in candidates if CARD_LIBRARY[key].card_type == card_type]
        if not candidates:
            return []
        messages: list[str] = []
        for _ in range(count):
            key = self.rng.choice(candidates)
            messages.extend(
                self._create_cards_in_combat(run, combat, key=key, location=location, count=1)
            )
        return messages

    def _discard_card(
        self,
        run: RunState | None,
        combat: CombatState,
        card: CardInstance,
    ) -> list[str]:
        combat.discard_pile.append(card)
        combat.player_statuses["cards_discarded_turn"] = (
            combat.player_statuses.get("cards_discarded_turn", 0) + 1
        )
        messages = [f"{self.card_name(card)} is discarded."]
        if card.key == "reflex" and run is not None:
            draw_count = 2 if card.upgraded else 1
            self._draw_cards(run, combat, draw_count)
            messages.append(f"Reflex draws {draw_count} card(s).")
        if card.key == "tactician":
            gained = 2 if card.upgraded else 1
            combat.energy += gained
            messages.append(f"Tactician grants {gained} Energy.")
        if run is not None and "hovering_kite" in run.relics and combat.player_statuses.get("cards_discarded_turn", 0) == 1:
            combat.energy += 1
            messages.append("Hovering Kite grants 1 Energy.")
        if run is not None and "tough_bandages" in run.relics:
            self._gain_player_block(
                run,
                combat,
                3,
                messages,
                already_scaled=True,
                message="Tough Bandages grants {gained} Block.",
            )
        if run is not None and "tingsha" in run.relics:
            alive = [enemy for enemy in combat.enemies if enemy.hp > 0]
            if alive:
                target = self.rng.choice(alive)
                dealt, extra_messages = self._deal_damage_to_enemy(run, combat, target, 3)
                messages.append(f"Tingsha deals {dealt} damage to {target.name}.")
                messages.extend(extra_messages)
                combat.enemies = self._prune_enemies(combat.enemies)
        return messages

    def _discard_random_cards(
        self,
        combat: CombatState,
        count: int,
        *,
        run: RunState | None = None,
    ) -> list[str]:
        messages: list[str] = []
        count = min(count, len(combat.hand))
        for _ in range(count):
            victim = self.rng.choice(combat.hand)
            combat.hand.remove(victim)
            messages.extend(self._discard_card(run, combat, victim))
        return messages

    def _move_random_card_from_pile(
        self,
        source: list[CardInstance],
        destination: list[CardInstance],
    ) -> CardInstance | None:
        if not source:
            return None
        card = self.rng.choice(source)
        source.remove(card)
        destination.append(card)
        return card

    def _exhaust_hand_matching(
        self,
        run: RunState,
        combat: CombatState,
        *,
        exclude_types: set[str] | None = None,
        include_types: set[str] | None = None,
    ) -> tuple[int, list[str]]:
        exhausted = 0
        messages: list[str] = []
        keep: list[CardInstance] = []
        for card in combat.hand:
            card_type = CARD_LIBRARY[card.key].card_type
            if include_types is not None and card_type not in include_types:
                keep.append(card)
                continue
            if exclude_types is not None and card_type in exclude_types:
                keep.append(card)
                continue
            exhausted += 1
            messages.extend(self._exhaust_card(run, combat, card))
        combat.hand = keep
        return exhausted, messages

    def _summon_enemies(
        self,
        run: RunState,
        combat: CombatState,
        enemy_keys: list[str],
        *,
        max_enemies: int = 5,
    ) -> list[str]:
        messages: list[str] = []
        alive = [enemy for enemy in combat.enemies if enemy.hp > 0]
        slots = max(0, max_enemies - len(alive))
        if slots <= 0:
            return messages
        for enemy_key in enemy_keys[:slots]:
            enemy = self._build_enemy_state(
                enemy_key,
                combat.encounter_kind,
                run.relics,
                len(combat.enemies) + 1,
            )
            combat.enemies.append(enemy)
            messages.append(f"{enemy.name} joins the fight.")
        return messages

    def _clear_debuffs(self, statuses: dict[str, int]) -> None:
        for status in list(statuses):
            if status in self.DEBUFF_STATUSES:
                statuses.pop(status, None)

    def _deal_damage_to_enemy(
        self,
        run: RunState,
        combat: CombatState,
        enemy: EnemyState,
        damage: int,
    ) -> tuple[int, list[str]]:
        dealt = self._damage_enemy(enemy, damage)
        return dealt, self._handle_enemy_damage_trigger(run, combat, enemy, dealt)

    def _handle_enemy_damage_trigger(
        self,
        run: RunState,
        combat: CombatState,
        enemy: EnemyState,
        dealt: int,
    ) -> list[str]:
        enemy_def = ENEMY_LIBRARY[enemy.key]
        if enemy.key == "the_champ" and not enemy.meta.get("phase_two") and enemy.hp > 0:
            threshold = max(1, enemy.max_hp // 2)
            if enemy.hp <= threshold:
                enemy.meta["phase_two"] = True
                enemy.meta["champ_phase_two_step"] = 1
                enemy.current_intent_index = int(enemy.meta.get("phase_two_intent", 5))
                return [f"{enemy.name} enters Phase Two and prepares Anger."]
        if enemy.key == "time_eater" and enemy.hp > 0 and not enemy.meta.get("hasted"):
            threshold = max(1, enemy.max_hp // 2)
            if enemy.hp <= threshold:
                enemy.meta["hasted"] = True
                enemy.current_intent_index = 3
                return [f"{enemy.name} prepares Haste."]
        if enemy.hp <= 0:
            messages: list[str] = []
            death_by_doom = bool(enemy.meta.pop("death_by_doom", 0))
            self._register_combat_death(combat)
            if death_by_doom and "book_repair_knife" in run.relics and "minion" not in enemy_def.tags:
                healed = self._heal_run(run, 3)
                self._sync_player_hp_relics(run, combat, messages)
                if healed > 0:
                    messages.append(f"Book Repair Knife heals {healed} HP.")
            if "the_specimen" in run.relics and enemy.statuses.get("poison", 0) > 0:
                targets = [
                    other
                    for other in combat.enemies
                    if other.enemy_id != enemy.enemy_id and other.hp > 0
                ]
                if targets:
                    target = self.rng.choice(targets)
                    poison = enemy.statuses.get("poison", 0)
                    _, poison_messages = self._apply_status_to_enemy(target, "poison", poison)
                    messages.extend(poison_messages)
            if enemy.statuses.get("corpse_explosion", 0) > 0:
                for other in list(combat.enemies):
                    if other.enemy_id == enemy.enemy_id or other.hp <= 0:
                        continue
                    dealt, extra_messages = self._deal_damage_to_enemy(run, combat, other, enemy.max_hp)
                    messages.append(f"Corpse Explosion deals {dealt} damage to {other.name}.")
                    messages.extend(extra_messages)
                return messages
            if enemy.key == "darkling" and self._other_living_darkling_exists(combat, enemy.enemy_id):
                enemy.block = 0
                enemy.statuses = {}
                enemy.meta["revive_pending"] = 2
                enemy.meta["darkling_nip_streak"] = 0
                enemy.current_intent_index = 3
                return [f"{enemy.name} collapses and begins to Regrow."]
            if enemy.key == "awakened_one" and not enemy.meta.get("revived"):
                enemy.meta["revived"] = True
                enemy.hp = enemy.max_hp
                enemy.block = 0
                enemy.statuses = {"strength": enemy.statuses.get("strength", 0)}
                enemy.meta["rebirth_invulnerable"] = 1
                enemy.meta.pop("power_reaction_strength", None)
                enemy.current_intent_index = int(enemy.meta.get("phase_two_intent", 0))
                return [f"{enemy.name} revives in a second form."]
            if enemy.key == "awakened_one" and enemy.meta.get("revived"):
                for other in combat.enemies:
                    if other.key == "cultist" and other.enemy_id != enemy.enemy_id:
                        other.hp = 0
                messages.append("The Awakened One falls and its cultists collapse with it.")
            if enemy.key == "the_collector":
                for other in combat.enemies:
                    if other.key == "torch_head" and other.enemy_id != enemy.enemy_id:
                        other.hp = 0
                messages.append("The Collector falls and its torches gutter out.")
            if enemy.key == "bronze_automaton":
                for other in combat.enemies:
                    if other.key == "bronze_orb" and other.enemy_id != enemy.enemy_id:
                        other.hp = 0
                messages.append("Bronze Automaton crashes and its orbs go dark.")
            stolen_gold = int(enemy.meta.get("stolen_gold", 0))
            if stolen_gold > 0:
                gained = self._gain_gold(run, stolen_gold)
                if gained > 0:
                    messages.append(f"You recover {gained} Gold from {enemy.name}.")
                else:
                    messages.append(f"Ectoplasm prevents recovering Gold from {enemy.name}.")
            if "gremlin_horn" in run.relics:
                if combat.player_meta.get("enemy_turn_active"):
                    combat.player_statuses["next_turn_energy"] = (
                        combat.player_statuses.get("next_turn_energy", 0) + 1
                    )
                    combat.player_statuses["next_turn_draw"] = (
                        combat.player_statuses.get("next_turn_draw", 0) + 1
                    )
                else:
                    combat.energy += 1
                    self._draw_cards(run, combat, 1)
                messages.append(f"Gremlin Horn triggers as {enemy.name} dies.")
            death_target = enemy_def.special.get("death_status_target")
            death_status = enemy_def.special.get("death_status")
            death_value = enemy_def.special.get("death_status_value")
            if death_target == "player" and death_status and death_value:
                _, status_messages = self._apply_status_to_player(
                    combat,
                    str(death_status),
                    int(death_value),
                )
                return messages + [
                    message.replace(
                        f"You gain {int(death_value)} {self._status_label(str(death_status))}.",
                        (
                            f"{enemy.name} lashes out on death. "
                            f"You gain {int(death_value)} {self._status_label(str(death_status))}."
                        ),
                    )
                    for message in status_messages
                ] or messages + [f"{enemy.name}'s death effect is negated."]
            return messages
        if enemy.key == "guardian" and enemy.current_intent_index != 1:
            remaining = enemy.meta.get("mode_shift_remaining", 30) - dealt
            enemy.meta["mode_shift_remaining"] = remaining
            if remaining <= 0:
                enemy.current_intent_index = 1
                enemy.meta["mode_shift_remaining"] = int(enemy_def.special.get("mode_shift", 30))
                return [f"{enemy.name} shifts into Defensive Mode."]
        split_keys = [str(entry) for entry in list(enemy_def.special.get("split_keys", []))]
        if enemy_def.special.get("split_at_half") and split_keys and not enemy.meta.get("split_done"):
            threshold = max(1, enemy.max_hp // 2)
            if enemy.hp <= threshold:
                enemy.meta["split_done"] = True
                split_hp = max(1, enemy.hp // len(split_keys))
                combat.enemies = [
                    entry for entry in combat.enemies if entry.enemy_id != enemy.enemy_id
                ]
                split_enemies = [
                    self._build_enemy_state(
                        split_key,
                        combat.encounter_kind,
                        run.relics,
                        len(combat.enemies) + index,
                    )
                    for index, split_key in enumerate(split_keys, start=1)
                ]
                for split_enemy in split_enemies:
                    split_enemy.hp = min(split_enemy.max_hp, split_hp)
                combat.enemies.extend(split_enemies)
                message = str(enemy_def.special.get("split_message", f"{enemy.name} splits."))
                return [message]
        messages: list[str] = []
        if enemy.key == "transient" and dealt > 0:
            delta, _ = self._modify_status(enemy.statuses, "strength", -dealt, temporary=True)
            if delta != 0:
                messages.append(f"{enemy.name}'s Shifting loses {abs(delta)} Strength this turn.")
        if enemy.key == "writhing_mass" and dealt > 0:
            current = enemy.current_intent_index
            enemy.current_intent_index = self._choose_writhing_mass_intent(enemy, opening=False)
            if enemy.current_intent_index != current:
                messages.append(f"{enemy.name} writhes and changes intent.")
        if dealt > 0 and enemy.meta.get("malleable_current", 0) > 0:
            gained = int(enemy.meta["malleable_current"])
            enemy.block += gained
            enemy.meta["malleable_current"] = gained + 1
            messages.append(f"{enemy.name}'s Malleable grants {gained} Block.")
        return messages

    def _apply_post_combat_run_effects(
        self,
        run: RunState,
        combat: CombatState,
    ) -> tuple[int, list[str]]:
        if "black_blood" in run.relics:
            healed = self._heal_run(run, 12)
        elif "burning_blood" in run.relics:
            healed = self._heal_run(run, 6)
        else:
            healed = 0
        self_repair = combat.player_statuses.get("self_repair", 0)
        if self_repair > 0:
            healed += self._heal_run(run, self_repair)
        messages: list[str] = []
        if "meat_on_the_bone" in run.relics and run.hp * 2 <= run.max_hp:
            meat_healed = self._heal_run(run, 12)
            healed += meat_healed
            if meat_healed > 0:
                messages.append("Meat On The Bone heals 12 HP.")
        if "face_of_cleric" in run.relics:
            self._increase_max_hp(run, 1, heal_current=False)
            messages.append("Face Of Cleric increases Max HP by 1.")
        return healed, messages

    def _begin_forbidden_grimoire_removal(
        self,
        run: RunState,
        combat: CombatState,
        *,
        resume_phase: str,
    ) -> bool:
        count = max(0, int(combat.player_statuses.get("forbidden_grimoire", 0)))
        if count <= 0 or not run.deck:
            return False
        run.phase = "remove"
        run.selection_context = f"forbidden_grimoire:{count}"
        run.meta["forbidden_grimoire_resume_phase"] = resume_phase
        return True

    def _advance_after_noncombat(self, run: RunState) -> None:
        if run.act > 4:
            run.phase = "victory"
            return
        self._prepare_map_choices(run)
        run.phase = "map"
        run.selection_context = None
        run.shop = None
        run.event = None

    def _prepare_map_choices(self, run: RunState) -> None:
        if run.act == 4:
            if run.act_floor == 0:
                run.map_choices = ["rest"]
            elif run.act_floor == 1:
                run.map_choices = ["shop"]
            elif run.act_floor == 2:
                run.map_choices = ["elite_key"]
            elif run.act_floor == 3:
                run.map_choices = ["boss"]
            else:
                run.map_choices = []
            return
        if run.act_floor >= self.MAP_NODE_ROWS:
            run.map_choices = ["boss"]
            return
        act_map = self._current_act_map(run)
        if act_map is None or run.act_floor == 0:
            self._generate_act_map(run)
            act_map = self._current_act_map(run)
        if act_map is None:
            run.map_choices = ["combat"]
            return
        reachable = [str(value) for value in list(act_map.get("reachable", []))]
        if not reachable:
            run.map_choices = ["boss"]
            return
        run.map_choices = reachable
        return

    def _build_enemy_state(
        self,
        enemy_key: str,
        encounter_kind: str,
        relics: list[str],
        position: int,
    ) -> EnemyState:
        enemy_def = ENEMY_LIBRARY[enemy_key]
        max_hp = enemy_def.max_hp
        if encounter_kind == "elite" and "preserved_insect" in relics:
            max_hp = max(1, (max_hp * 3) // 4)
        enemy = EnemyState(
            enemy_id=f"{enemy_key}_{position}",
            key=enemy_def.key,
            name=enemy_def.name,
            hp=max_hp,
            max_hp=max_hp,
            statuses={},
            asleep_turns=int(enemy_def.special.get("asleep_turns", 0)),
            meta={},
        )
        if enemy.key == "gremlin_nob":
            enemy.meta["enrage"] = 2
        if enemy_def.special.get("split_at_half"):
            enemy.meta["split_done"] = False
        if enemy_def.special.get("mode_shift"):
            enemy.meta["mode_shift_remaining"] = int(enemy_def.special["mode_shift"])
        if enemy_def.special.get("phase_two_intent") is not None:
            enemy.meta["phase_two_intent"] = int(enemy_def.special["phase_two_intent"])
        if enemy_def.special.get("power_reaction_strength"):
            enemy.meta["power_reaction_strength"] = int(enemy_def.special["power_reaction_strength"])
        if enemy_def.special.get("malleable"):
            enemy.meta["malleable_base"] = int(enemy_def.special["malleable"])
            enemy.meta["malleable_current"] = int(enemy_def.special["malleable"])
        if enemy_def.special.get("strength_up"):
            enemy.meta["strength_up"] = int(enemy_def.special["strength_up"])
        if enemy_def.special.get("flight"):
            enemy.statuses["flight"] = int(enemy_def.special["flight"])
            enemy.meta["flight_base"] = int(enemy_def.special["flight"])
        if enemy_def.special.get("explosive"):
            enemy.statuses["explosive"] = int(enemy_def.special["explosive"])
            enemy.meta["explosive_damage"] = int(enemy_def.special.get("explosive_damage", 30))
        if enemy_def.special.get("fading"):
            enemy.statuses["fading"] = int(enemy_def.special["fading"])
        if enemy_def.special.get("start_block"):
            enemy.block = int(enemy_def.special["start_block"])
        if enemy.key == "byrd":
            enemy.meta["grounded"] = False
            enemy.meta["byrd_peck_streak"] = 0
        if enemy.key == "darkling":
            enemy.meta["darkling_middle"] = position == 2
            enemy.meta["darkling_nip_streak"] = 0
            enemy.current_intent_index = self._choose_darkling_intent(enemy, opening=True)
        if enemy.key == "snecko":
            enemy.meta["snecko_bite_streak"] = 0
        for status_name in (
            "artifact",
            "barricade",
            "beat_of_death",
            "intangible",
            "lock_on",
            "plated_armor",
            "regeneration",
            "thorns",
        ):
            if enemy_def.special.get(status_name):
                enemy.statuses[status_name] = int(enemy_def.special[status_name])
        invincible_cap = enemy_def.special.get("invincible")
        if invincible_cap:
            enemy.statuses["invincible"] = int(invincible_cap)
            enemy.meta["invincible_cap"] = int(invincible_cap)
        time_warp_cap = enemy_def.special.get("time_warp")
        if time_warp_cap:
            enemy.meta["time_warp_cap"] = int(time_warp_cap)
            enemy.meta["time_warp_counter"] = 0
            enemy.meta["time_warp_strength"] = int(enemy_def.special.get("time_warp_strength", 2))
        return enemy

    def _current_intent(self, enemy: EnemyState):
        return ENEMY_LIBRARY[enemy.key].intents[enemy.current_intent_index]

    def _choose_byrd_airborne_intent(self, enemy: EnemyState) -> int:
        current = enemy.current_intent_index
        peck_streak = int(enemy.meta.get("byrd_peck_streak", 0))
        while True:
            roll = self.rng.random()
            if roll < 0.5:
                choice = 0
            elif roll < 0.8:
                choice = 1
            else:
                choice = 2
            if choice == 0 and peck_streak >= 2:
                continue
            if choice == 1 and current == 1:
                continue
            if choice == 2 and current == 2:
                continue
            return choice

    def _choose_snecko_intent(self, enemy: EnemyState) -> int:
        if int(enemy.meta.get("snecko_bite_streak", 0)) >= 2:
            return 2
        return 1 if self.rng.random() < 0.6 else 2

    def _choose_hexaghost_intent(self, enemy: EnemyState, *, opening: bool) -> int:
        if opening:
            enemy.meta["hexaghost_cycle_index"] = 0
            return 0
        if enemy.current_intent_index == 0:
            return 1
        cycle = [2, 3, 2, 4, 3, 2, 5]
        index = int(enemy.meta.get("hexaghost_cycle_index", 0))
        choice = cycle[index % len(cycle)]
        enemy.meta["hexaghost_cycle_index"] = (index + 1) % len(cycle)
        return choice

    def _choose_darkling_intent(self, enemy: EnemyState, *, opening: bool) -> int:
        current = enemy.current_intent_index
        nip_streak = int(enemy.meta.get("darkling_nip_streak", 0))
        middle = bool(enemy.meta.get("darkling_middle"))
        while True:
            if middle or opening:
                choice = 0 if self.rng.random() < 0.5 else 2
            else:
                roll = self.rng.random()
                if roll < 0.3:
                    choice = 0
                elif roll < 0.7:
                    choice = 1
                else:
                    choice = 2
            if choice == 0 and nip_streak >= 2:
                continue
            if choice == 1 and current == 1:
                continue
            if choice == 2 and current == 2:
                continue
            if middle and choice == 1:
                continue
            return choice

    def _choose_centurion_intent(
        self,
        enemy: EnemyState,
        combat: CombatState,
        *,
        opening: bool,
    ) -> int:
        mystic_alive = any(entry.key == "mystic" and entry.hp > 0 for entry in combat.enemies)
        slash_streak = int(enemy.meta.get("centurion_slash_streak", 0))
        support_streak = int(enemy.meta.get("centurion_support_streak", 0))
        slash_index = 0
        support_index = 1 if mystic_alive else 2
        while True:
            choice = slash_index if self.rng.random() < 0.65 else support_index
            if choice == slash_index and slash_streak >= 2:
                continue
            if choice == support_index and support_streak >= 2:
                continue
            return choice

    def _choose_mystic_intent(
        self,
        enemy: EnemyState,
        combat: CombatState,
        *,
        opening: bool,
    ) -> int:
        if any(entry.hp > 0 and entry.max_hp - entry.hp >= 16 for entry in combat.enemies):
            if int(enemy.meta.get("mystic_heal_streak", 0)) < 2:
                return 2
        attack_streak = int(enemy.meta.get("mystic_attack_streak", 0))
        buff_streak = int(enemy.meta.get("mystic_buff_streak", 0))
        while True:
            choice = 0 if self.rng.random() < 0.6 else 1
            if choice == 0 and attack_streak >= 2:
                continue
            if choice == 1 and buff_streak >= 2:
                continue
            return choice

    def _choose_writhing_mass_intent(
        self,
        enemy: EnemyState,
        *,
        opening: bool,
    ) -> int:
        current = enemy.current_intent_index
        parasite_used = bool(enemy.meta.get("writhing_mass_parasite_used"))
        candidates: list[tuple[int, float]]
        if opening:
            candidates = [(0, 1.0), (1, 1.0), (2, 1.0)]
        else:
            candidates = [(0, 0.3), (1, 0.2), (2, 0.1), (3, 0.3)]
            if not parasite_used:
                candidates.append((4, 0.1))
        while True:
            total = sum(weight for _, weight in candidates)
            roll = self.rng.random() * total
            upto = 0.0
            choice = candidates[-1][0]
            for index, weight in candidates:
                upto += weight
                if roll <= upto:
                    choice = index
                    break
            if choice == current:
                continue
            return choice

    def _choose_maw_intent(
        self,
        enemy: EnemyState,
        *,
        opening: bool,
    ) -> int:
        if opening:
            return 0
        current = enemy.current_intent_index
        if current in {0, 1}:
            return 2 if self.rng.random() < 0.5 else 3
        if current == 2:
            return 1 if self.rng.random() < 0.5 else 3
        if current == 3:
            return 1
        return 0

    def _choose_champ_intent(
        self,
        enemy: EnemyState,
        combat: CombatState,
        *,
        opening: bool,
    ) -> int:
        def choose_phase_one_random(current_intent: int | None) -> int:
            weights = {0: 15, 3: 15, 1: 25, 2: 45}
            if current_intent in weights:
                redirect = {0: 3, 3: 1, 1: 2, 2: 1}[current_intent]
                weights[redirect] += weights.pop(current_intent, 0)
            if int(enemy.meta.get("champ_defensive_uses", 0)) >= 2:
                weights[3] += weights.pop(0, 0)
            weighted: list[int] = []
            for intent_index, weight in weights.items():
                weighted.extend([intent_index] * weight)
            return self.rng.choice(weighted or [2])

        if enemy.meta.get("phase_two"):
            phase_step = int(enemy.meta.get("champ_phase_two_step", 0))
            if opening or phase_step == 0:
                enemy.meta["champ_phase_two_step"] = 1
                return 5
            next_step = phase_step + 1
            enemy.meta["champ_phase_two_step"] = next_step
            if next_step == 2 or (next_step > 2 and (next_step - 2) % 3 == 0):
                return 6
            return choose_phase_one_random(enemy.current_intent_index)
        if opening:
            return choose_phase_one_random(None)
        if (combat.turn + 1) % 4 == 0:
            return 4
        return choose_phase_one_random(enemy.current_intent_index)

    def _choose_collector_intent(
        self,
        enemy: EnemyState,
        combat: CombatState,
        *,
        opening: bool,
    ) -> int:
        live_heads = sum(1 for entry in combat.enemies if entry.key == "torch_head" and entry.hp > 0)
        if opening or live_heads < 2:
            return 0
        if enemy.current_intent_index == 1:
            return 2 if self.rng.random() < 0.4 else 1
        if enemy.current_intent_index == 2:
            return 1
        return 1 if self.rng.random() < 0.7 else 2

    def _choose_bronze_automaton_intent(
        self,
        enemy: EnemyState,
        combat: CombatState,
        *,
        opening: bool,
    ) -> int:
        live_orbs = sum(1 for entry in combat.enemies if entry.key == "bronze_orb" and entry.hp > 0)
        if opening:
            return 0
        if live_orbs < 2 and enemy.current_intent_index != 0:
            return 0
        if enemy.current_intent_index == 3:
            return 1
        if enemy.current_intent_index == 2:
            return 3 if self.rng.random() < 0.25 else 1
        if enemy.current_intent_index == 1:
            return 2 if self.rng.random() < 0.6 else 3
        return 1 if self.rng.random() < 0.7 else 2

    def _choose_donu_intent(self, enemy: EnemyState, *, opening: bool) -> int:
        if opening:
            return 0
        return 1 if enemy.current_intent_index == 0 else 0

    def _choose_deca_intent(self, enemy: EnemyState, *, opening: bool) -> int:
        if opening:
            return 1
        return 0 if enemy.current_intent_index == 1 else 1

    def _choose_awakened_one_intent(self, enemy: EnemyState, *, opening: bool) -> int:
        if opening:
            enemy.meta["awakened_phase_one_last"] = 0
            enemy.meta["awakened_phase_one_streak"] = 1
            enemy.meta["awakened_phase_two_streak"] = 0
            return 0
        if not enemy.meta.get("revived"):
            last = int(enemy.meta.get("awakened_phase_one_last", enemy.current_intent_index))
            streak = int(enemy.meta.get("awakened_phase_one_streak", 1))
            if last == 0 and streak >= 2:
                choice = 1
            elif last == 1 and streak >= 1:
                choice = 0
            else:
                choice = 1 if self.rng.random() < 0.25 else 0
            enemy.meta["awakened_phase_one_last"] = choice
            enemy.meta["awakened_phase_one_streak"] = streak + 1 if choice == last else 1
            return choice
        if enemy.current_intent_index == 2:
            choice = 3 if self.rng.random() < 0.5 else 4
            enemy.meta["awakened_phase_two_streak"] = 1
            enemy.meta["awakened_phase_two_last"] = choice
            return choice
        last = int(enemy.meta.get("awakened_phase_two_last", 3))
        streak = int(enemy.meta.get("awakened_phase_two_streak", 0))
        if streak >= 2:
            choice = 4 if last == 3 else 3
            enemy.meta["awakened_phase_two_streak"] = 1
            enemy.meta["awakened_phase_two_last"] = choice
            return choice
        if self.rng.random() < 0.5:
            choice = last
            enemy.meta["awakened_phase_two_streak"] = streak + 1
        else:
            choice = 4 if last == 3 else 3
            enemy.meta["awakened_phase_two_streak"] = 1
        enemy.meta["awakened_phase_two_last"] = choice
        return choice

    def _choose_repulsor_intent(self, enemy: EnemyState) -> int:
        if enemy.current_intent_index == 1:
            return 0
        return 1 if self.rng.random() < 0.2 else 0

    def _choose_reptomancer_intent(
        self,
        enemy: EnemyState,
        combat: CombatState,
        *,
        opening: bool,
    ) -> int:
        live_daggers = sum(1 for entry in combat.enemies if entry.key == "dagger" and entry.hp > 0)
        if opening or live_daggers < 2:
            return 0
        if enemy.current_intent_index == 1:
            return 2 if self.rng.random() < 0.4 else 1
        if enemy.current_intent_index == 2:
            return 1 if self.rng.random() < 0.7 else 2
        return 1 if self.rng.random() < 0.65 else 2

    def _choose_time_eater_intent(
        self,
        enemy: EnemyState,
        *,
        opening: bool,
    ) -> int:
        if enemy.current_intent_index == 3:
            enemy.meta.pop("time_eater_reverb_streak", None)
        if opening:
            return self.rng.choice([0, 1, 2])
        current = enemy.current_intent_index
        reverb_streak = int(enemy.meta.get("time_eater_reverb_streak", 0))
        choices: list[int] = []
        if current == 0 and reverb_streak < 2:
            choices.extend([0, 0, 0, 0, 0])
        elif current != 0:
            choices.extend([0, 0, 0, 0, 0])
        if current != 1:
            choices.extend([1, 1, 1, 1])
        if current != 2:
            choices.extend([2, 2, 2])
        return self.rng.choice(choices or [0, 1, 2])

    def _choose_corrupt_heart_intent(self, enemy: EnemyState, *, opening: bool) -> int:
        if opening:
            enemy.meta.pop("heart_pair_pending", None)
            return 0
        pending = enemy.meta.pop("heart_pair_pending", None)
        if isinstance(pending, int):
            return pending
        if enemy.current_intent_index in {0, 3}:
            first = 1 if self.rng.random() < 0.5 else 2
            enemy.meta["heart_pair_pending"] = 2 if first == 1 else 1
            return first
        return 3

    def _advance_enemy_intent(
        self,
        enemy: EnemyState,
        combat: CombatState | None = None,
    ) -> None:
        if enemy.key == "byrd":
            if enemy.meta.get("grounded"):
                if enemy.current_intent_index == 3:
                    enemy.current_intent_index = 4
                    return
                if enemy.current_intent_index == 4:
                    enemy.current_intent_index = 5
                    return
                enemy.meta["grounded"] = False
                enemy.meta["byrd_peck_streak"] = 0
                enemy.current_intent_index = self._choose_byrd_airborne_intent(enemy)
                return
            if enemy.current_intent_index == 0:
                enemy.meta["byrd_peck_streak"] = int(enemy.meta.get("byrd_peck_streak", 0)) + 1
            else:
                enemy.meta["byrd_peck_streak"] = 0
            enemy.current_intent_index = self._choose_byrd_airborne_intent(enemy)
            return
        if enemy.key == "darkling":
            if enemy.current_intent_index == 0:
                enemy.meta["darkling_nip_streak"] = int(enemy.meta.get("darkling_nip_streak", 0)) + 1
            else:
                enemy.meta["darkling_nip_streak"] = 0
            enemy.current_intent_index = self._choose_darkling_intent(enemy, opening=False)
            return
        if enemy.key == "centurion" and combat is not None:
            if enemy.current_intent_index == 0:
                enemy.meta["centurion_slash_streak"] = int(enemy.meta.get("centurion_slash_streak", 0)) + 1
                enemy.meta["centurion_support_streak"] = 0
            else:
                enemy.meta["centurion_support_streak"] = int(enemy.meta.get("centurion_support_streak", 0)) + 1
                enemy.meta["centurion_slash_streak"] = 0
            enemy.current_intent_index = self._choose_centurion_intent(enemy, combat, opening=False)
            return
        if enemy.key == "mystic" and combat is not None:
            if enemy.current_intent_index == 0:
                enemy.meta["mystic_attack_streak"] = int(enemy.meta.get("mystic_attack_streak", 0)) + 1
                enemy.meta["mystic_buff_streak"] = 0
                enemy.meta["mystic_heal_streak"] = 0
            elif enemy.current_intent_index == 1:
                enemy.meta["mystic_buff_streak"] = int(enemy.meta.get("mystic_buff_streak", 0)) + 1
                enemy.meta["mystic_attack_streak"] = 0
                enemy.meta["mystic_heal_streak"] = 0
            else:
                enemy.meta["mystic_heal_streak"] = int(enemy.meta.get("mystic_heal_streak", 0)) + 1
                enemy.meta["mystic_attack_streak"] = 0
                enemy.meta["mystic_buff_streak"] = 0
            enemy.current_intent_index = self._choose_mystic_intent(enemy, combat, opening=False)
            return
        if enemy.key == "snecko":
            if enemy.current_intent_index == 1:
                enemy.meta["snecko_bite_streak"] = int(enemy.meta.get("snecko_bite_streak", 0)) + 1
            else:
                enemy.meta["snecko_bite_streak"] = 0
            enemy.current_intent_index = self._choose_snecko_intent(enemy)
            return
        if enemy.key == "hexaghost":
            enemy.current_intent_index = self._choose_hexaghost_intent(enemy, opening=False)
            return
        if enemy.key == "writhing_mass":
            if enemy.current_intent_index == 4:
                enemy.meta["writhing_mass_parasite_used"] = True
            enemy.current_intent_index = self._choose_writhing_mass_intent(enemy, opening=False)
            return
        if enemy.key == "the_maw":
            enemy.current_intent_index = self._choose_maw_intent(enemy, opening=False)
            return
        if enemy.key == "the_champ" and combat is not None:
            enemy.current_intent_index = self._choose_champ_intent(enemy, combat, opening=False)
            return
        if enemy.key == "the_collector" and combat is not None:
            enemy.current_intent_index = self._choose_collector_intent(enemy, combat, opening=False)
            return
        if enemy.key == "awakened_one":
            enemy.current_intent_index = self._choose_awakened_one_intent(enemy, opening=False)
            return
        if enemy.key == "bronze_automaton" and combat is not None:
            enemy.current_intent_index = self._choose_bronze_automaton_intent(enemy, combat, opening=False)
            return
        if enemy.key == "donu":
            enemy.current_intent_index = self._choose_donu_intent(enemy, opening=False)
            return
        if enemy.key == "deca":
            enemy.current_intent_index = self._choose_deca_intent(enemy, opening=False)
            return
        if enemy.key == "repulsor":
            enemy.current_intent_index = self._choose_repulsor_intent(enemy)
            return
        if enemy.key == "reptomancer" and combat is not None:
            enemy.current_intent_index = self._choose_reptomancer_intent(enemy, combat, opening=False)
            return
        if enemy.key == "time_eater":
            if enemy.current_intent_index == 0:
                enemy.meta["time_eater_reverb_streak"] = int(enemy.meta.get("time_eater_reverb_streak", 0)) + 1
            else:
                enemy.meta["time_eater_reverb_streak"] = 0
            enemy.current_intent_index = self._choose_time_eater_intent(enemy, opening=False)
            return
        if enemy.key == "corrupt_heart":
            enemy.current_intent_index = self._choose_corrupt_heart_intent(enemy, opening=False)
            return
        if enemy.key in {"looter", "mugger"}:
            enemy.current_intent_index = min(
                enemy.current_intent_index + 1,
                len(ENEMY_LIBRARY[enemy.key].intents) - 1,
            )
            return
        if enemy.key == "romeo":
            if enemy.current_intent_index == 0:
                enemy.current_intent_index = 1
            elif enemy.current_intent_index == 1:
                enemy.current_intent_index = 2
            else:
                enemy.current_intent_index = 1
            return
        if enemy.key == "bear":
            if enemy.current_intent_index == 0:
                enemy.current_intent_index = 1
            elif enemy.current_intent_index == 1:
                enemy.current_intent_index = 2
            else:
                enemy.current_intent_index = 1
            return
        if enemy.key == "shelled_parasite":
            enemy.current_intent_index = (
                enemy.current_intent_index + 1
            ) % 3
            return
        enemy.current_intent_index = (
            enemy.current_intent_index + 1
        ) % len(ENEMY_LIBRARY[enemy.key].intents)

    def _combat_statuses_from_relics(self, run: RunState) -> dict[str, int]:
        relics = run.relics
        statuses: dict[str, int] = {}
        if "vajra" in relics:
            statuses["strength"] = statuses.get("strength", 0) + 1
        if "oddly_smooth_stone" in relics:
            statuses["dexterity"] = statuses.get("dexterity", 0) + 1
        if "data_disk" in relics:
            statuses["focus"] = statuses.get("focus", 0) + 1
        if "akabeko" in relics:
            statuses["akabeko_pending"] = 8
        if "snecko_skull" in relics:
            statuses["poison_bonus"] = 1
        if "champion_belt" in relics:
            statuses["champion_belt"] = 1
        if "paper_frog" in relics:
            statuses["paper_frog"] = 1
        if "bronze_scales" in relics:
            statuses["thorns"] = statuses.get("thorns", 0) + 3
        if "thread_and_needle" in relics:
            statuses["plated_armor"] = statuses.get("plated_armor", 0) + 4
        if "gremlin_visage" in relics:
            statuses["weak"] = statuses.get("weak", 0) + 1
        if "happy_flower" in relics:
            statuses["happy_flower_counter"] = 0
        if "incense_burner" in relics:
            statuses["incense_burner_counter"] = 0
        if "centennial_puzzle" in relics:
            statuses["centennial_puzzle_ready"] = 1
        if "odd_mushroom" in relics:
            statuses["odd_mushroom"] = 1
        if "clockwork_souvenir" in relics:
            statuses["artifact"] = statuses.get("artifact", 0) + 1
        if "fossilized_helix" in relics:
            statuses["buffer"] = statuses.get("buffer", 0) + 1
        if "du_vu_doll" in relics:
            statuses["strength"] = statuses.get("strength", 0) + sum(
                1 for card in run.deck if CARD_LIBRARY[card.key].rarity == "curse"
            )
        girya_lifts = int(run.meta.get("girya_lifts", 0))
        if girya_lifts > 0:
            statuses["strength"] = statuses.get("strength", 0) + girya_lifts
        if "nunchaku" in relics:
            statuses["nunchaku_counter"] = 0
        if "pen_nib" in relics:
            statuses["pen_nib_counter"] = 0
        if "ink_bottle" in relics:
            statuses["ink_bottle_counter"] = 0
        if "sundial" in relics:
            statuses["sundial_counter"] = 0
        if "blue_candle" in relics:
            statuses["blue_candle"] = 1
        if "medical_kit" in relics:
            statuses["medical_kit"] = 1
        if "snecko_eye" in relics:
            statuses["confused"] = 1
        statuses["attacks_played_turn"] = 0
        statuses["skills_played_turn"] = 0
        statuses["cards_played_turn"] = 0
        return statuses

    def _compute_player_attack_damage(
        self,
        combat: CombatState,
        base: int,
        attacker_statuses: dict[str, int],
        defender_statuses: dict[str, int],
    ) -> int:
        damage = max(0, int(base) + attacker_statuses.get("strength", 0))
        if attacker_statuses.get("first_attack_bonus", 0) > 0:
            damage += attacker_statuses.pop("first_attack_bonus", 0)
        damage += int(combat.player_meta.get("wrist_blade_bonus", 0))
        if attacker_statuses.get("weak", 0) > 0:
            damage = (damage * 3) // 4
        lethality = attacker_statuses.get("lethality", 0)
        if lethality > 0 and combat.player_statuses.get("attacks_played_turn", 0) == 0:
            damage = (damage * (100 + lethality)) // 100
        double_count = attacker_statuses.get("double_attack_damage", 0) + int(
            combat.player_meta.get("double_attack_damage_card", 0)
        )
        if double_count > 0:
            damage *= 2**double_count
        if combat.stance == "wrath":
            damage *= 2
        if combat.stance == "divinity":
            damage *= 3
        damage = self._apply_enemy_vulnerable_multiplier(
            damage,
            attacker_statuses,
            defender_statuses,
        )
        return max(0, damage)

    def _compute_enemy_attack_damage(
        self,
        combat: CombatState,
        base: int,
        attacker_statuses: dict[str, int],
        defender_statuses: dict[str, int],
    ) -> int:
        damage = max(0, int(base) + attacker_statuses.get("strength", 0))
        if attacker_statuses.get("weak", 0) > 0:
            if attacker_statuses.get("debilitate", 0) > 0:
                damage //= 2
            else:
                damage = (damage * 3) // 4
        if defender_statuses.get("vulnerable", 0) > 0:
            if defender_statuses.get("odd_mushroom", 0) > 0:
                damage = (damage * 5) // 4
            else:
                damage = (damage * 3) // 2
        if combat.stance == "wrath":
            damage *= 2
        return max(0, damage)

    def _compute_block_gain(self, base: int, statuses: dict[str, int]) -> int:
        total = max(0, int(base) + statuses.get("dexterity", 0))
        if statuses.get("frail", 0) > 0:
            total = (total * 3) // 4
        return max(0, total)

    def _damage_enemy(self, enemy: EnemyState, damage: int) -> int:
        if damage > 0 and enemy.meta.get("rebirth_invulnerable"):
            return 0
        absorbed = min(enemy.block, damage)
        enemy.block -= absorbed
        remaining = damage - absorbed
        if remaining > 0 and enemy.statuses.get("intangible", 0) > 0:
            remaining = 1
        invincible = enemy.statuses.get("invincible", 0)
        if remaining > 0 and invincible > 0:
            remaining = min(remaining, invincible)
            enemy.statuses["invincible"] = max(0, invincible - remaining)
        enemy.hp = max(0, enemy.hp - remaining)
        if remaining > 0 and enemy.statuses.get("plated_armor", 0) > 0:
            enemy.statuses["plated_armor"] -= 1
            if enemy.statuses["plated_armor"] <= 0:
                enemy.statuses.pop("plated_armor", None)
        return remaining

    def _damage_player(
        self,
        run: RunState,
        combat: CombatState,
        damage: int,
        *,
        from_attack: bool = False,
    ) -> int:
        if damage > 0 and combat.player_statuses.get("buffer", 0) > 0:
            combat.player_statuses["buffer"] -= 1
            if combat.player_statuses["buffer"] <= 0:
                combat.player_statuses.pop("buffer", None)
            return 0
        absorbed = min(combat.player_block, damage)
        combat.player_block -= absorbed
        remaining = damage - absorbed
        if remaining > 0 and combat.player_statuses.get("intangible", 0) > 0:
            remaining = 1
        if remaining > 0 and from_attack and "torii" in run.relics and remaining <= 5:
            remaining = 1
        if remaining > 0 and "tungsten_rod" in run.relics:
            remaining = max(0, remaining - 1)
        if remaining > 0 and from_attack and self._osty_alive(combat):
            osty_messages: list[str] = []
            absorbed_by_osty = self._damage_osty(run, combat, remaining, osty_messages)
            if absorbed_by_osty > 0:
                combat.log.append(f"Osty intercepts {absorbed_by_osty} damage.")
            combat.log.extend(osty_messages)
            return 0
        run.hp = max(0, run.hp - remaining)
        self._trigger_combat_hp_loss_relics(run, combat, remaining)
        if remaining > 0 and combat.player_statuses.pop("centennial_puzzle_ready", 0) > 0:
            self._draw_cards(run, combat, 3)
            combat.log.append("Centennial Puzzle draws 3 card(s).")
        if remaining > 0 and combat.player_statuses.get("static_discharge", 0) > 0:
            for _ in range(combat.player_statuses["static_discharge"]):
                self._channel_orb(combat, "lightning")
        if remaining > 0 and combat.player_statuses.get("plated_armor", 0) > 0:
            combat.player_statuses["plated_armor"] -= 1
            if combat.player_statuses["plated_armor"] <= 0:
                combat.player_statuses.pop("plated_armor", None)
        return remaining

    def _after_enemy_attack_hit(
        self,
        run: RunState,
        combat: CombatState,
        enemy: EnemyState,
        dealt: int,
    ) -> list[str]:
        if dealt <= 0:
            return []
        painful_stabs = int(enemy.statuses.get("painful_stabs", 0))
        if painful_stabs <= 0:
            return []
        return self._create_cards_in_combat(
            run,
            combat,
            key="wound",
            location="discard",
            count=painful_stabs,
        )

    def _upgrade_burn_cards_in_combat(self, combat: CombatState) -> None:
        for pile in (combat.hand, combat.draw_pile, combat.discard_pile, combat.exhaust_pile):
            for card in pile:
                if card.key == "burn":
                    card.upgraded = True

    def _tick_statuses(
        self, statuses: dict[str, int], messages: list[str], owner: str
    ) -> None:
        if statuses.get("temp_strength_loss", 0) > 0:
            loss = statuses["temp_strength_loss"]
            statuses["strength"] = statuses.get("strength", 0) - loss
            statuses["temp_strength_loss"] = 0
            messages.append(f"{owner} loses {loss} temporary Strength.")
        for key in [entry for entry in list(statuses) if entry.startswith("temp_revert_")]:
            status = key.removeprefix("temp_revert_")
            revert = statuses.get(key, 0)
            if revert != 0:
                statuses[status] = statuses.get(status, 0) + revert
                if statuses[status] == 0:
                    statuses.pop(status, None)
                messages.append(f"{owner}'s {self._status_label(status)} returns by {revert}.")
            statuses.pop(key, None)
        for status in ("weak", "vulnerable", "frail", "debilitate"):
            if statuses.get(status, 0) > 0:
                statuses[status] -= 1
                if statuses[status] <= 0:
                    statuses.pop(status, None)

    def _resolve_player_end_of_turn(self, run: RunState, combat: CombatState) -> None:
        if "cloak_clasp" in run.relics and combat.hand:
            self._gain_player_block(
                run,
                combat,
                len(combat.hand),
                combat.log,
                already_scaled=True,
                message="Cloak Clasp grants {gained} Block.",
            )
        fumes = combat.player_statuses.get("noxious_fumes", 0)
        if fumes > 0:
            for enemy in list(combat.enemies):
                _, status_messages = self._apply_status_to_enemy(enemy, "poison", fumes)
                combat.log.extend(
                    message.replace(
                        f"{enemy.name} gains {fumes} Poison.",
                        f"{enemy.name} gains {fumes} Poison from Noxious Fumes.",
                    )
                    for message in status_messages
                )
        metallicize = combat.player_statuses.get("metallicize", 0)
        if metallicize > 0:
            self._gain_player_block(
                run,
                combat,
                metallicize,
                combat.log,
                message="Metallicize grants {gained} Block.",
            )
        if combat.stance == "calm" and combat.player_statuses.get("like_water", 0) > 0:
            self._gain_player_block(
                run,
                combat,
                combat.player_statuses["like_water"],
                combat.log,
                message="Like Water grants {gained} Block.",
            )
        constricted = combat.player_statuses.get("constricted", 0)
        if constricted > 0:
            run.hp = max(0, run.hp - constricted)
            combat.log.append(f"Constricted makes you lose {constricted} HP.")
            self._trigger_combat_hp_loss_relics(run, combat, constricted, combat.log)
        omega = combat.player_statuses.get("omega", 0)
        if omega > 0:
            for enemy in list(combat.enemies):
                damage = self._compute_player_attack_damage(
                    combat,
                    50,
                    combat.player_statuses,
                    enemy.statuses,
                )
                dealt, extra_messages = self._resolve_player_attack_hit(
                    run,
                    combat,
                    enemy,
                    damage,
                )
                combat.log.append(f"Omega deals {dealt} damage to {enemy.name}.")
                combat.log.extend(extra_messages)
            combat.enemies = self._prune_enemies(combat.enemies)
        bombs = list(combat.player_meta.get("bombs", []))
        remaining_bombs: list[dict[str, int]] = []
        for bomb in bombs:
            timer = int(bomb.get("timer", 3)) - 1
            damage = int(bomb.get("damage", 40))
            if timer <= 0:
                for enemy in list(combat.enemies):
                    dealt, extra_messages = self._deal_damage_to_enemy(run, combat, enemy, damage)
                    combat.log.append(f"The Bomb deals {dealt} damage to {enemy.name}.")
                    combat.log.extend(extra_messages)
                combat.enemies = self._prune_enemies(combat.enemies)
            else:
                remaining_bombs.append({"timer": timer, "damage": damage})
        if remaining_bombs:
            combat.player_meta["bombs"] = remaining_bombs
        else:
            combat.player_meta.pop("bombs", None)
        demon_form = combat.player_statuses.get("demon_form", 0)
        if demon_form > 0:
            combat.player_statuses["strength"] = combat.player_statuses.get("strength", 0) + demon_form
            combat.log.append(f"Demon Form grants {demon_form} Strength.")
        if combat.player_statuses.get("wraith_form", 0) > 0:
            combat.player_statuses["dexterity"] = combat.player_statuses.get("dexterity", 0) - 1
            combat.log.append("Wraith Form costs 1 Dexterity.")
        if combat.player_statuses.get("biased_cognition", 0) > 0:
            combat.player_statuses["focus"] = combat.player_statuses.get("focus", 0) - 1
            combat.log.append("Biased Cognition loses 1 Focus.")
        ritual = combat.player_statuses.get("ritual", 0)
        if ritual > 0:
            combat.player_statuses["strength"] = combat.player_statuses.get("strength", 0) + ritual
            combat.log.append(f"Ritual grants {ritual} Strength.")
        if "art_of_war" in run.relics and combat.player_statuses.get("attacks_played_turn", 0) == 0:
            combat.player_statuses["next_turn_energy"] = (
                combat.player_statuses.get("next_turn_energy", 0) + 1
            )
            combat.log.append("Art Of War will grant 1 Energy next turn.")
        if "pocketwatch" in run.relics and combat.player_statuses.get("cards_played_turn", 0) <= 3:
            combat.player_statuses["next_turn_draw"] = (
                combat.player_statuses.get("next_turn_draw", 0) + 3
            )
            combat.log.append("Pocketwatch will draw 3 extra card(s) next turn.")
        combust = combat.player_statuses.get("combust", 0)
        if combust > 0:
            run.hp = max(0, run.hp - 1)
            combat.log.append("Combust deals 1 damage to you.")
            self._trigger_combat_hp_loss_relics(run, combat, 1, combat.log)
            for enemy in list(combat.enemies):
                dealt, extra_messages = self._deal_damage_to_enemy(run, combat, enemy, combust)
                combat.log.append(f"Combust deals {dealt} damage to {enemy.name}.")
                combat.log.extend(extra_messages)
        if "stone_calendar" in run.relics and combat.turn == 7:
            for enemy in list(combat.enemies):
                dealt, extra_messages = self._deal_damage_to_enemy(run, combat, enemy, 52)
                combat.log.append(f"Stone Calendar deals {dealt} damage to {enemy.name}.")
                combat.log.extend(extra_messages)
            combat.enemies = self._prune_enemies(combat.enemies)
        plated = combat.player_statuses.get("plated_armor", 0)
        if plated > 0:
            self._gain_player_block(
                run,
                combat,
                plated,
                combat.log,
                already_scaled=True,
                message="Plated Armor grants {gained} Block.",
            )
        for index in range(len(combat.orbs)):
            self._trigger_orb_passive_at_index(run, combat, index)
        loop = combat.player_statuses.get("loop", 0)
        if loop > 0 and combat.orbs:
            for _ in range(loop):
                self._trigger_orb_passive_at_index(run, combat, 0, prefix="Loop triggers")
        if "gold_plated_cables" in run.relics and combat.orbs:
            self._trigger_orb_passive_at_index(run, combat, len(combat.orbs) - 1, prefix="Gold-Plated Cables triggers")
        if combat.player_statuses.pop("emotion_chip_ready", 0) > 0 and combat.orbs:
            self._trigger_orb_passive_at_index(run, combat, 0, prefix="Emotion Chip triggers")
        if "frozen_core" in run.relics and len(combat.orbs) < combat.orb_slots:
            self._channel_orb(combat, "frost")
            combat.log.append("Frozen Core channels a Frost orb.")
        regeneration = combat.player_statuses.get("regeneration", 0)
        if regeneration > 0:
            healed = min(run.max_hp, run.hp + regeneration) - run.hp
            run.hp += healed
            if healed > 0:
                combat.log.append(f"Regeneration heals {healed} HP.")
            combat.player_statuses["regeneration"] = regeneration - 1
            if combat.player_statuses["regeneration"] <= 0:
                combat.player_statuses.pop("regeneration", None)
        if combat.player_statuses.get("poison", 0) > 0:
            poison = combat.player_statuses["poison"]
            dealt = self._damage_player(run, combat, poison)
            combat.log.append(f"You take {dealt} poison damage.")
            combat.player_statuses["poison"] = max(0, poison - 1)
            if combat.player_statuses["poison"] <= 0:
                combat.player_statuses.pop("poison", None)
        combat.player_statuses.pop("oblivion", None)
        combat.player_statuses.pop("next_ethereal_free", None)
        combat.player_statuses.pop("double_attack_damage", None)
        combat.player_statuses.pop("rage", None)
        self._tick_statuses(combat.player_statuses, combat.log, "player")
        self._resolve_player_doom(run, combat)
        if combat.stance == "divinity":
            combat.stance = "neutral"
            combat.log.append("Divinity fades.")
        combat.enemies = self._prune_enemies(combat.enemies)

    def _resolve_hand_end_of_turn(self, run: RunState, combat: CombatState) -> None:
        for card in combat.hand:
            if card.key == "burn":
                dealt = self._damage_player(run, combat, 4 if card.upgraded else 2)
                combat.log.append(f"Burn deals {dealt} damage to you.")
            elif card.key == "decay":
                dealt = self._damage_player(run, combat, 2)
                combat.log.append(f"Decay deals {dealt} damage to you.")
            elif card.key == "doubt":
                _, messages = self._apply_status_to_player(combat, "weak", 1)
                combat.log.extend(message.replace("You gain 1 Weak.", "Doubt applies 1 Weak.") for message in messages)
            elif card.key == "shame":
                _, messages = self._apply_status_to_player(combat, "frail", 1)
                combat.log.extend(message.replace("You gain 1 Frail.", "Shame applies 1 Frail.") for message in messages)
            elif card.key == "regret":
                dealt = self._damage_player(run, combat, len(combat.hand))
                combat.log.append(f"Regret deals {dealt} damage to you.")

    def _trigger_orb_passive_at_index(
        self,
        run: RunState,
        combat: CombatState,
        index: int,
        *,
        prefix: str = "",
    ) -> None:
        if index < 0 or index >= len(combat.orbs):
            return
        orb = combat.orbs[index]
        alive = [enemy for enemy in combat.enemies if enemy.hp > 0]
        kind = self._orb_kind(orb)
        label_prefix = f"{prefix} " if prefix else ""
        if kind == "lightning" and alive:
            damage = max(0, 3 + combat.player_statuses.get("focus", 0))
            if combat.player_statuses.get("electrodynamics", 0) > 0:
                for target in list(alive):
                    dealt, extra_messages = self._deal_orb_damage_to_enemy(
                        run,
                        combat,
                        target,
                        damage,
                    )
                    combat.log.append(f"{label_prefix}Lightning orb zaps {target.name} for {dealt}.")
                    combat.log.extend(extra_messages)
            else:
                target = self.rng.choice(alive)
                dealt, extra_messages = self._deal_orb_damage_to_enemy(
                    run,
                    combat,
                    target,
                    damage,
                )
                combat.log.append(f"{label_prefix}Lightning orb zaps {target.name} for {dealt}.")
                combat.log.extend(extra_messages)
        elif kind == "frost":
            gain = max(0, 2 + combat.player_statuses.get("focus", 0))
            template = "Frost orb grants {gained} Block." if not prefix else f"{prefix} Frost grants {{gained}} Block."
            self._gain_player_block(
                run,
                combat,
                gain,
                combat.log,
                already_scaled=True,
                message=template,
            )
        elif kind == "plasma":
            combat.player_statuses["next_turn_energy"] = (
                combat.player_statuses.get("next_turn_energy", 0) + 1
            )
            if prefix:
                combat.log.append(f"{prefix} Plasma prepares 1 extra Energy next turn.")
            else:
                combat.log.append("Plasma orb prepares 1 Energy for next turn.")
        elif kind == "dark":
            value = self._orb_value(combat.orbs[index]) + max(0, 6 + combat.player_statuses.get("focus", 0))
            self._set_orb_value(combat, index, "dark", value)
            if prefix:
                combat.log.append(f"{prefix} Dark grows to {value} damage.")
            else:
                combat.log.append(f"Dark orb grows to {value} damage.")

    def _orb_kind(self, orb: str) -> str:
        return orb.split(":", 1)[0]

    def _orb_value(self, orb: str) -> int:
        if ":" not in orb:
            return 0
        try:
            return int(orb.split(":", 1)[1])
        except ValueError:
            return 0

    def _set_orb_value(self, combat: CombatState, index: int, kind: str, value: int) -> None:
        combat.orbs[index] = f"{kind}:{value}"

    def _channel_orb(self, combat: CombatState, orb_name: str) -> list[str]:
        messages: list[str] = []
        if combat.orb_slots <= 0:
            return messages
        if len(combat.orbs) >= combat.orb_slots:
            messages.extend(self._evoke_leftmost_orb(None, combat))
        if orb_name == "dark":
            combat.orbs.append(f"dark:{max(6, 6 + combat.player_statuses.get('focus', 0))}")
        else:
            combat.orbs.append(orb_name)
        if orb_name == "lightning":
            combat.player_statuses["lightning_orbs_channeled"] = (
                combat.player_statuses.get("lightning_orbs_channeled", 0) + 1
            )
        elif orb_name == "frost":
            combat.player_statuses["frost_orbs_channeled"] = (
                combat.player_statuses.get("frost_orbs_channeled", 0) + 1
            )
        return messages

    def _evoke_leftmost_orb(
        self, run: RunState | None, combat: CombatState
    ) -> list[str]:
        if not combat.orbs:
            return ["No orb is available to evoke."]
        return self._resolve_orb_evoke(run, combat, combat.orbs.pop(0))

    def _resolve_orb_evoke(
        self,
        run: RunState | None,
        combat: CombatState,
        orb: str,
    ) -> list[str]:
        messages: list[str] = []
        kind = self._orb_kind(orb)
        if kind == "lightning":
            alive = [enemy for enemy in combat.enemies if enemy.hp > 0]
            damage = max(0, 8 + combat.player_statuses.get("focus", 0))
            if combat.player_statuses.get("electrodynamics", 0) > 0:
                for target in list(alive):
                    dealt, extra_messages = self._deal_orb_damage_to_enemy(
                        run,
                        combat,
                        target,
                        damage,
                    )
                    messages.append(f"Evoke Lightning deals {dealt} damage to {target.name}.")
                    messages.extend(extra_messages)
            else:
                target = alive[0] if alive else None
                if target is not None:
                    dealt, extra_messages = self._deal_orb_damage_to_enemy(
                        run,
                        combat,
                        target,
                        damage,
                    )
                    messages.append(f"Evoke Lightning deals {dealt} damage to {target.name}.")
                    messages.extend(extra_messages)
        elif kind == "frost":
            gain = max(0, 5 + combat.player_statuses.get("focus", 0))
            self._gain_player_block(run, combat, gain, messages, already_scaled=True, message="Evoke Frost grants {gained} Block.")
        elif kind == "plasma":
            combat.energy += 2
            messages.append("Evoke Plasma grants 2 Energy.")
        elif kind == "dark":
            alive = [enemy for enemy in combat.enemies if enemy.hp > 0]
            target = min(alive, key=lambda enemy: enemy.hp) if alive else None
            if target is not None:
                damage = self._orb_value(orb)
                dealt, extra_messages = self._deal_orb_damage_to_enemy(
                    run,
                    combat,
                    target,
                    damage,
                )
                messages.append(f"Evoke Dark deals {dealt} damage to {target.name}.")
                messages.extend(extra_messages)
        return messages

    def _complete_end_turn(self, run: RunState) -> str:
        combat = self._require_combat(run)
        self._resolve_hand_end_of_turn(run, combat)
        self._discard_hand(run, combat)
        if combat.player_block == 0 and "orichalcum" in run.relics:
            combat.player_block = 6
            combat.log.append("Orichalcum grants 6 Block.")
        self._resolve_player_end_of_turn(run, combat)
        if not self._has_remaining_enemies(combat):
            return self._resolve_victory(run)
        if combat.player_statuses.pop("blasphemy", 0) > 0:
            run.hp = 0
            combat.log.append("Blasphemy kills you.")
        if run.hp <= 0:
            return self._resolve_player_defeat(run, [])
        if combat.player_statuses.pop("skip_enemy_turn", 0) > 0:
            self._start_next_turn(run)
            return "You take another turn."
        message = self._run_enemy_turn(run)
        if run.phase == "combat" and not self._has_remaining_enemies(combat):
            return self._resolve_victory(run)
        if run.phase == "combat":
            self._start_next_turn(run)
            if combat.player_statuses.pop("skip_player_turn", 0) > 0:
                combat.log.append("Osty's death costs you a turn.")
                return self._complete_end_turn(run)
            if run.hp <= 0:
                return self._resolve_player_defeat(run, [])
        return message

    def _resolve_player_defeat(self, run: RunState, messages: list[str]) -> str:
        if "lizard_tail" in run.relics and not run.meta.get("lizard_tail_used"):
            run.meta["lizard_tail_used"] = 1
            run.hp = max(1, run.max_hp // 2)
            run.phase = "combat"
            if run.combat is not None:
                run.combat.player_block = 0
                run.combat.log.extend(messages + ["Lizard Tail revives you."])
                run.combat.log = run.combat.log[-12:]
            return " ".join(messages + ["Lizard Tail revives you."]).strip()
        run.phase = "defeat"
        run.combat = None
        run.reward = None
        run.shop = None
        run.event = None
        return " ".join(messages + ["You are slain."]).strip()

    def _status_label(self, status: str) -> str:
        return status.replace("_", " ").title()

    def _status_is_debuff(self, status: str) -> bool:
        return status in self.DEBUFF_STATUSES

    def _enemy_intends_attack(self, enemy: EnemyState) -> bool:
        return any(
            action.get("type")
            in {
                "attack",
                "attack_scaling",
                "attack_turn_scaled_hits",
                "attack_hexaghost_divider",
                "hexaghost_inferno",
                "hexaghost_sear",
                "explode",
            }
            for action in self._current_intent(enemy).actions
        )

    def _modify_status(
        self,
        statuses: dict[str, int],
        status: str,
        delta: int,
        *,
        use_artifact: bool = False,
        temporary: bool = False,
    ) -> tuple[int, bool]:
        if delta == 0:
            return 0, False
        if use_artifact and delta < 0 and statuses.get("artifact", 0) > 0:
            statuses["artifact"] -= 1
            if statuses["artifact"] <= 0:
                statuses.pop("artifact", None)
            return 0, True
        statuses[status] = statuses.get(status, 0) + delta
        if statuses[status] == 0:
            statuses.pop(status, None)
        if temporary:
            revert_key = f"temp_revert_{status}"
            statuses[revert_key] = statuses.get(revert_key, 0) - delta
        return delta, False

    def _apply_status_value(
        self,
        statuses: dict[str, int],
        status: str,
        value: int,
        *,
        use_artifact: bool = False,
    ) -> tuple[int, bool]:
        if value <= 0:
            return 0, False
        if use_artifact and self._status_is_debuff(status) and statuses.get("artifact", 0) > 0:
            statuses["artifact"] -= 1
            if statuses["artifact"] <= 0:
                statuses.pop("artifact", None)
            return 0, True
        if status == "confused":
            statuses[status] = 1
            return 1, False
        statuses[status] = statuses.get(status, 0) + value
        return value, False

    def _apply_status_to_player(
        self,
        combat: CombatState,
        status: str,
        value: int,
    ) -> tuple[int, list[str]]:
        applied, blocked = self._apply_status_value(
            combat.player_statuses,
            status,
            value,
            use_artifact=True,
        )
        if blocked:
            return 0, [f"Artifact negates {self._status_label(status)}."]
        messages = [f"You gain {applied} {self._status_label(status)}."] if applied > 0 else []
        if status == "mantra" and applied > 0:
            combat.player_statuses["mantra_gained_combat"] = (
                combat.player_statuses.get("mantra_gained_combat", 0) + applied
            )
            messages.extend(self._resolve_mantra(None, combat))
        return applied, messages

    def _apply_status_to_enemy(
        self,
        enemy: EnemyState,
        status: str,
        value: int,
    ) -> tuple[int, list[str]]:
        applied, blocked = self._apply_status_value(
            enemy.statuses,
            status,
            value,
            use_artifact=True,
        )
        if blocked:
            return 0, [f"{enemy.name}'s Artifact negates {self._status_label(status)}."]
        return (
            applied,
            [f"{enemy.name} gains {applied} {self._status_label(status)}."]
            if applied > 0
            else [],
        )

    def _resolve_player_attack_hit(
        self,
        run: RunState,
        combat: CombatState,
        enemy: EnemyState,
        damage: int,
        *,
        triggers_thorns: bool,
    ) -> tuple[int, list[str]]:
        messages: list[str] = []
        flight = enemy.statuses.get("flight", 0)
        if damage > 0 and flight > 0:
            damage = damage // 2
            messages.append(f"{enemy.name}'s Flight reduces the attack to {damage}.")
        potential_unblocked = max(0, damage - enemy.block)
        if (
            "the_boot" in run.relics
            and 0 < potential_unblocked < 5
            and enemy.statuses.get("intangible", 0) <= 0
        ):
            damage = enemy.block + 5
            messages.append("The Boot increases the hit to 5 damage.")
        initial_block = enemy.block
        dealt, extra_messages = self._deal_damage_to_enemy(run, combat, enemy, damage)
        messages.extend(extra_messages)
        if combat.player_statuses.get("reaper_form", 0) > 0 and dealt > 0:
            messages.extend(
                self._apply_status_from_action(
                    run,
                    combat,
                    target="enemy",
                    status="doom",
                    value=dealt,
                    target_enemy=enemy,
                )
            )
        if "hand_drill" in run.relics and initial_block > 0 and enemy.block <= 0 and damage > initial_block and enemy.hp > 0:
            _, vulnerable_messages = self._apply_status_to_enemy(enemy, "vulnerable", 2)
            messages.extend(vulnerable_messages)
        if damage > 0 and flight > 0:
            enemy.statuses["flight"] = flight - 1
            if enemy.statuses["flight"] <= 0:
                enemy.statuses.pop("flight", None)
                if enemy.key == "byrd":
                    enemy.meta["grounded"] = True
                    enemy.meta["byrd_peck_streak"] = 0
                    enemy.current_intent_index = 3
                    messages.append(f"{enemy.name} is knocked out of the air.")
        ttth = enemy.statuses.get("talk_to_the_hand", 0)
        if dealt > 0 and ttth > 0:
            self._gain_player_block(
                run,
                combat,
                ttth,
                messages,
                message="Talk To The Hand grants {gained} Block.",
            )
        envenom = combat.player_statuses.get("envenom", 0)
        if dealt > 0 and envenom > 0:
            _, poison_messages = self._apply_status_to_enemy(enemy, "poison", envenom)
            messages.extend(poison_messages)
        if triggers_thorns and enemy.statuses.get("thorns", 0) > 0 and run.hp > 0:
            messages.extend(self._retaliate_with_enemy_thorns(run, combat, enemy))
        return dealt, messages

    def _retaliate_with_player_thorns(
        self,
        run: RunState,
        combat: CombatState,
        enemy: EnemyState,
    ) -> list[str]:
        thorns = combat.player_statuses.get("thorns", 0)
        if thorns <= 0 or enemy.hp <= 0:
            return []
        dealt, extra_messages = self._deal_damage_to_enemy(run, combat, enemy, thorns)
        messages = [f"Thorns deal {dealt} damage to {enemy.name}."]
        messages.extend(extra_messages)
        if enemy.hp <= 0:
            messages.append(f"{enemy.name} is defeated.")
        return messages

    def _retaliate_with_enemy_thorns(
        self,
        run: RunState,
        combat: CombatState,
        enemy: EnemyState,
    ) -> list[str]:
        thorns = enemy.statuses.get("thorns", 0)
        if thorns <= 0:
            return []
        dealt = self._damage_player(run, combat, thorns)
        return [f"{enemy.name}'s Thorns deal {dealt} damage to you."]

    def _deal_orb_damage_to_enemy(
        self,
        run: RunState | None,
        combat: CombatState,
        enemy: EnemyState,
        damage: int,
    ) -> tuple[int, list[str]]:
        messages: list[str] = []
        if enemy.statuses.get("lock_on", 0) > 0:
            damage = (damage * 3) // 2
            enemy.statuses["lock_on"] -= 1
            if enemy.statuses["lock_on"] <= 0:
                enemy.statuses.pop("lock_on", None)
            messages.append(f"Lock-On amplifies orb damage on {enemy.name}.")
        dealt, extra_messages = self._deal_damage_to_enemy(run, combat, enemy, damage)
        messages.extend(extra_messages)
        return dealt, messages

    def _handle_post_card_play(
        self,
        run: RunState,
        combat: CombatState,
    ) -> tuple[list[str], bool]:
        messages: list[str] = []
        if combat.last_target_enemy_id:
            for enemy in list(combat.enemies):
                if enemy.enemy_id != combat.last_target_enemy_id:
                    continue
                choke = enemy.statuses.get("choke", 0)
                if choke > 0:
                    dealt, extra_messages = self._deal_damage_to_enemy(run, combat, enemy, choke)
                    messages.append(f"Choke deals {dealt} damage to {enemy.name}.")
                    messages.extend(extra_messages)
                    if enemy.hp <= 0:
                        messages.append(f"{enemy.name} is defeated.")
                        combat.enemies = [entry for entry in combat.enemies if entry.hp > 0]
                break
        for enemy in list(combat.enemies):
            beat_of_death = enemy.statuses.get("beat_of_death", 0)
            if beat_of_death <= 0:
                continue
            dealt = self._damage_player(run, combat, beat_of_death)
            messages.append(f"{enemy.name}'s Beat Of Death deals {dealt} damage to you.")
            if run.hp <= 0:
                return messages, False
        forced_end = False
        if combat.player_meta.pop("force_end_turn", False):
            forced_end = True
        for enemy in combat.enemies:
            time_warp_cap = enemy.meta.get("time_warp_cap")
            if not time_warp_cap:
                continue
            enemy.meta["time_warp_counter"] = enemy.meta.get("time_warp_counter", 0) + 1
            if enemy.meta["time_warp_counter"] >= time_warp_cap:
                enemy.meta["time_warp_counter"] = 0
                strength = int(enemy.meta.get("time_warp_strength", 2))
                enemy.statuses["strength"] = enemy.statuses.get("strength", 0) + strength
                messages.append(
                    f"{enemy.name}'s Time Warp ends your turn and grants {strength} Strength."
                )
                forced_end = True
        if "unceasing_top" in run.relics and not combat.hand and combat.energy > 0:
            self._draw_cards(run, combat, 1)
            messages.append("Unceasing Top draws 1 card.")
        return messages, forced_end

    def _change_stance(
        self,
        run: RunState | None,
        combat: CombatState,
        stance: str,
    ) -> str:
        old = combat.stance
        new = stance.lower()
        if old == new:
            return f"You remain in {new.title()}."
        if old == "calm" and new != "calm":
            combat.energy += 2
            if run is not None and "violet_lotus" in run.relics:
                combat.energy += 1
        combat.stance = new
        mental_fortress = combat.player_statuses.get("mental_fortress", 0)
        if mental_fortress > 0:
            gained = self._compute_block_gain(mental_fortress, combat.player_statuses)
            combat.player_block += gained
        if new == "wrath" and combat.player_statuses.get("rushdown", 0) > 0:
            self._draw_cards(run, combat, 2 * combat.player_statuses["rushdown"])
        if new == "divinity":
            combat.energy += 3
        flurry_cards = [card for card in list(combat.discard_pile) if card.key == "flurry_of_blows"]
        for card in flurry_cards:
            combat.discard_pile.remove(card)
            combat.hand.append(card)
        if new == "neutral":
            return f"You leave {old.title()} stance."
        return f"You enter {new.title()}."

    def _select_target_enemy(
        self,
        run: RunState,
        target_mode: str,
        target_enemy_id: str | None,
    ) -> EnemyState | None:
        if run.combat is None:
            return None
        if target_mode != "enemy":
            return None
        alive = self.alive_enemies(run)
        if not alive:
            return None
        if len(alive) == 1:
            return alive[0]
        if target_enemy_id is None:
            raise ValueError("Choose a target.")
        for enemy in alive:
            if enemy.enemy_id == target_enemy_id:
                return enemy
        raise ValueError("Target not found.")

    def _count_cards_by_key(
        self,
        run: RunState,
        combat: CombatState,
        key: str,
    ) -> int:
        return sum(1 for card in run.deck if card.key == key)

    def _find_card(
        self, cards: list[CardInstance], instance_id: str
    ) -> CardInstance | None:
        for card in cards:
            if card.instance_id == instance_id:
                return card
        return None

    def _require_combat(self, run: RunState) -> CombatState:
        if run.phase != "combat" or run.combat is None:
            raise ValueError("No combat is active.")
        return run.combat

    def _actions_for_card(self, card: CardInstance) -> list[dict[str, object]]:
        card_def = CARD_LIBRARY[card.key]
        if card.upgraded and card_def.upgraded_actions is not None:
            return copy.deepcopy(card_def.upgraded_actions)
        return copy.deepcopy(card_def.actions)
