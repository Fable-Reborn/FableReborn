"""Catalog and presentation helpers for the Legacy Shop."""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import discord


LIVING_LEGEND_MIN_LIFETIME = 50_000
LIVING_LEGEND_FEAT_RATIO = 0.82
LIVING_LEGEND_RELIC_MILESTONE = "exalted"


@dataclass(frozen=True)
class LegacyShopItem:
    key: str
    name: str
    cost: int
    description: str
    reward_type: str
    amount: int = 1
    weekly_limit: int | None = None
    crate: str | None = None
    badge: str | None = None

    def remaining_stock(self, purchases: int) -> int | None:
        if self.weekly_limit is None:
            return None
        return max(0, self.weekly_limit - max(0, int(purchases)))


LEGACY_SHOP_ITEMS = (
    LegacyShopItem(
        key="mystery5",
        name="5x Mystery Crates",
        cost=300,
        description="Five mystery crates, straight from the vault.",
        reward_type="crate",
        crate="mystery",
        amount=5,
        weekly_limit=2,
    ),
    LegacyShopItem(
        key="goldpouch",
        name="Legacy Gold Pouch",
        cost=500,
        description="A heavy pouch holding $250,000.",
        reward_type="money",
        amount=250_000,
        weekly_limit=2,
    ),
    LegacyShopItem(
        key="fortune",
        name="Fortune Crate",
        cost=1_000,
        description="One fortune crate.",
        reward_type="crate",
        crate="fortune",
        weekly_limit=1,
    ),
    LegacyShopItem(
        key="divine",
        name="Divine Crate",
        cost=2_500,
        description="One divine crate.",
        reward_type="crate",
        crate="divine",
        weekly_limit=1,
    ),
    LegacyShopItem(
        key="badge",
        name="Living Legend Badge",
        cost=25_000,
        description="A permanent profile badge for masters of the realm.",
        reward_type="badge",
        badge="LIVING_LEGEND",
    ),
)

LEGACY_SHOP = {item.key: item for item in LEGACY_SHOP_ITEMS}


def living_legend_required_feat_count(total_feats: int) -> int:
    """Return the feat count required for the Living Legend rank."""

    return math.ceil(max(0, int(total_feats)) * LIVING_LEGEND_FEAT_RATIO)


def legacy_week_start(now: datetime | None = None) -> datetime:
    """Return Monday at 00:00 UTC for the week containing ``now``."""

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    return (current - timedelta(days=current.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def living_legend_gate_failures(progress: dict) -> tuple[str, ...]:
    """Return human-readable unmet capstone requirements."""

    required_feats = living_legend_required_feat_count(progress.get("feat_total", 0))
    required_sets = max(0, int(progress.get("relic_total", 0)))
    failures = []
    if int(progress.get("lifetime", 0)) < LIVING_LEGEND_MIN_LIFETIME:
        failures.append(
            f"Lifetime LP: {int(progress.get('lifetime', 0)):,}/"
            f"{LIVING_LEGEND_MIN_LIFETIME:,}"
        )
    if int(progress.get("feat_count", 0)) < required_feats:
        failures.append(
            f"Active Feats: {int(progress.get('feat_count', 0)):,}/{required_feats:,}"
        )
    if int(progress.get("relic_count", 0)) < required_sets:
        failures.append(
            f"Exalted Relic sets: {int(progress.get('relic_count', 0)):,}/"
            f"{required_sets:,}"
        )
    return tuple(failures)


def living_legend_progress_lines(progress: dict) -> list[str]:
    required_feats = living_legend_required_feat_count(progress.get("feat_total", 0))
    rows = (
        (int(progress.get("lifetime", 0)), LIVING_LEGEND_MIN_LIFETIME, "lifetime LP"),
        (int(progress.get("feat_count", 0)), required_feats, "active Feats"),
        (
            int(progress.get("relic_count", 0)),
            int(progress.get("relic_total", 0)),
            "Exalted Relic sets",
        ),
    )
    return [
        f"{'✓' if current >= required else '○'} **{current:,}/{required:,}** {label}"
        for current, required, label in rows
    ]


def _weekly_offer_line(
    item: LegacyShopItem, points: int, weekly_purchases: dict[str, int]
) -> str:
    remaining = item.remaining_stock(weekly_purchases.get(item.key, 0))
    if remaining == 0:
        marker = "—"
        stock = "sold out"
    else:
        marker = "✓" if points >= item.cost else "○"
        stock = f"{remaining}/{item.weekly_limit} left"
    return (
        f"{marker} `{item.key}` **{item.name}** — **{item.cost:,} LP**\n"
        f"{item.description} · {stock}"
    )


def build_legacy_shop_embed(
    points: int,
    lifetime: int,
    weekly_purchases: dict[str, int],
    living_legend_progress: dict,
    *,
    prefix: str = "$",
) -> discord.Embed:
    """Build a concise shop card without database or Discord I/O."""

    points = int(points)
    lifetime = int(lifetime)
    command = f"{prefix}legacy buy"
    embed = discord.Embed(
        title="🏛️ Legacy Shop",
        description=(
            f"**{points:,} LP** available · **{lifetime:,} LP** lifetime\n"
            f"Buy with `{command} <item>`"
        ),
        color=0xD4B95E,
    )

    weekly_items = [
        _weekly_offer_line(item, points, weekly_purchases)
        for item in LEGACY_SHOP_ITEMS
        if item.weekly_limit is not None
    ]
    embed.add_field(
        name="Weekly rewards",
        value="\n\n".join(weekly_items),
        inline=False,
    )

    badge = LEGACY_SHOP["badge"]
    requirements = "\n".join(living_legend_progress_lines(living_legend_progress))
    gate_open = not living_legend_gate_failures(living_legend_progress)
    marker = "✓" if gate_open and points >= badge.cost else "○"
    status = "Requirements met" if gate_open else "Requirements incomplete"
    embed.add_field(
        name="Permanent reward",
        value=(
            f"{marker} `{badge.key}` **{badge.name}** — **{badge.cost:,} LP**\n"
            f"{badge.description} · {status}\n{requirements}"
        ),
        inline=False,
    )
    embed.set_footer(text="Weekly stock resets Monday at 00:00 UTC")
    return embed
