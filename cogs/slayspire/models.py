from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class CardInstance:
    instance_id: str
    key: str
    upgraded: bool = False
    misc: int = 0
    cost_adjustment: int = 0


@dataclass
class EnemyState:
    enemy_id: str
    key: str
    name: str
    hp: int
    max_hp: int
    block: int = 0
    statuses: dict[str, int] = field(default_factory=dict)
    current_intent_index: int = 0
    asleep_turns: int = 0
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class CombatState:
    encounter_kind: str
    enemies: list[EnemyState]
    hand: list[CardInstance] = field(default_factory=list)
    draw_pile: list[CardInstance] = field(default_factory=list)
    discard_pile: list[CardInstance] = field(default_factory=list)
    exhaust_pile: list[CardInstance] = field(default_factory=list)
    player_block: int = 0
    player_statuses: dict[str, int] = field(default_factory=dict)
    energy: int = 3
    max_energy: int = 3
    turn: int = 1
    log: list[str] = field(default_factory=list)
    reward_gold: int = 0
    reward_cards: list[str] = field(default_factory=list)
    relic_reward: str | None = None
    first_turn: bool = True
    stance: str = "neutral"
    orb_slots: int = 0
    orbs: list[str] = field(default_factory=list)
    active_card_key: str | None = None
    last_target_enemy_id: str | None = None
    player_meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class RewardState:
    source: str
    gold: int
    card_choices: list[str] = field(default_factory=list)
    relic_choices: list[str] = field(default_factory=list)


@dataclass
class ShopOffer:
    offer_id: str
    kind: str
    key: str
    cost: int
    base_cost: int = 0
    sale: bool = False
    slot: str = ""


@dataclass
class ShopState:
    offers: list[ShopOffer] = field(default_factory=list)
    remove_cost: int = 75
    remove_used: bool = False


@dataclass
class EventOptionState:
    option_id: str
    label: str
    description: str


@dataclass
class EventState:
    key: str
    name: str
    description: str
    options: list[EventOptionState] = field(default_factory=list)


@dataclass
class RunState:
    user_id: int
    guild_id: int
    channel_id: int
    character: str
    max_hp: int
    hp: int
    gold: int
    act: int = 1
    act_floor: int = 0
    floor: int = 0
    phase: str = "map"
    deck: list[CardInstance] = field(default_factory=list)
    relics: list[str] = field(default_factory=list)
    potions: list[str] = field(default_factory=list)
    keys: list[str] = field(default_factory=list)
    map_choices: list[str] = field(default_factory=list)
    combat: CombatState | None = None
    reward: RewardState | None = None
    shop: ShopState | None = None
    event: EventState | None = None
    selection_context: str | None = None
    log: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    next_instance_id: int = 1

    def push_log(self, message: str) -> None:
        self.log.append(message)
        if len(self.log) > 12:
            self.log = self.log[-12:]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> RunState:
        combat_payload = payload.get("combat")
        reward_payload = payload.get("reward")
        shop_payload = payload.get("shop")
        event_payload = payload.get("event")

        combat = cls._combat_from_dict(combat_payload) if combat_payload else None
        reward = RewardState(**reward_payload) if reward_payload else None
        shop = cls._shop_from_dict(shop_payload) if shop_payload else None
        event = cls._event_from_dict(event_payload) if event_payload else None

        return cls(
            user_id=int(payload["user_id"]),
            guild_id=int(payload["guild_id"]),
            channel_id=int(payload["channel_id"]),
            character=str(payload["character"]),
            max_hp=int(payload["max_hp"]),
            hp=int(payload["hp"]),
            gold=int(payload.get("gold", 0)),
            act=int(payload.get("act", 1)),
            act_floor=int(payload.get("act_floor", 0)),
            floor=int(payload.get("floor", 0)),
            phase=str(payload.get("phase", "map")),
            deck=[CardInstance(**entry) for entry in payload.get("deck", [])],
            relics=[str(entry) for entry in payload.get("relics", [])],
            potions=[str(entry) for entry in payload.get("potions", [])],
            keys=[str(entry) for entry in payload.get("keys", [])],
            map_choices=[str(entry) for entry in payload.get("map_choices", [])],
            combat=combat,
            reward=reward,
            shop=shop,
            event=event,
            selection_context=payload.get("selection_context"),
            log=[str(entry) for entry in payload.get("log", [])],
            meta={str(key): value for key, value in payload.get("meta", {}).items()},
            next_instance_id=int(payload.get("next_instance_id", 1)),
        )

    @staticmethod
    def _combat_from_dict(payload: dict[str, Any]) -> CombatState:
        enemies = [EnemyState(**entry) for entry in payload.get("enemies", [])]
        return CombatState(
            encounter_kind=str(payload["encounter_kind"]),
            enemies=enemies,
            hand=[CardInstance(**entry) for entry in payload.get("hand", [])],
            draw_pile=[CardInstance(**entry) for entry in payload.get("draw_pile", [])],
            discard_pile=[
                CardInstance(**entry) for entry in payload.get("discard_pile", [])
            ],
            exhaust_pile=[
                CardInstance(**entry) for entry in payload.get("exhaust_pile", [])
            ],
            player_block=int(payload.get("player_block", 0)),
            player_statuses={
                str(key): int(value)
                for key, value in payload.get("player_statuses", {}).items()
            },
            energy=int(payload.get("energy", 3)),
            max_energy=int(payload.get("max_energy", 3)),
            turn=int(payload.get("turn", 1)),
            log=[str(entry) for entry in payload.get("log", [])],
            reward_gold=int(payload.get("reward_gold", 0)),
            reward_cards=[str(entry) for entry in payload.get("reward_cards", [])],
            relic_reward=payload.get("relic_reward"),
            first_turn=bool(payload.get("first_turn", True)),
            stance=str(payload.get("stance", "neutral")),
            orb_slots=int(payload.get("orb_slots", 0)),
            orbs=[str(entry) for entry in payload.get("orbs", [])],
            active_card_key=payload.get("active_card_key"),
            last_target_enemy_id=payload.get("last_target_enemy_id"),
            player_meta=dict(payload.get("player_meta", {})),
        )

    @staticmethod
    def _shop_from_dict(payload: dict[str, Any]) -> ShopState:
        return ShopState(
            offers=[ShopOffer(**entry) for entry in payload.get("offers", [])],
            remove_cost=int(payload.get("remove_cost", 75)),
            remove_used=bool(payload.get("remove_used", False)),
        )

    @staticmethod
    def _event_from_dict(payload: dict[str, Any]) -> EventState:
        return EventState(
            key=str(payload["key"]),
            name=str(payload["name"]),
            description=str(payload["description"]),
            options=[EventOptionState(**entry) for entry in payload.get("options", [])],
        )
