"""Durable builder storage and personal library policy.

The registry is JSON TEXT deliberately: normal ritual actions use dict ordering.
Compare-and-swap protects the entire registry (including quotas and routing) across
bot clusters. Preferences are separate, so navigation never rewrites raid content.
"""

import copy
import json

from functools import wraps

SAVED_LIMIT = 5
DRAFT_LIMIT = 10


class StorageError(ValueError):
    pass


class StaleEdit(StorageError):
    pass


def library_counts(registry, user_id):
    owned = [
        d for d in registry["definitions"].values() if d.get("creator_id") == user_id
    ]
    return {
        "saved": sum(d.get("status") == "published" for d in owned),
        "drafts": sum(d.get("status") != "published" for d in owned),
    }


def require_slot(registry, user_id, status):
    key, limit = (
        ("saved", SAVED_LIMIT) if status == "published" else ("drafts", DRAFT_LIMIT)
    )
    if library_counts(registry, user_id)[key] >= limit:
        raise ValueError(
            f"Your library is full: {limit} {key} across normal and advanced mode. "
            "Delete an entry or publish a draft to free the appropriate slot."
        )


class RaidStore:
    def __init__(self, pool):
        self.pool = pool

    async def initialize(self, seed_factory):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Serializes first-time DDL/import across clusters.
                await conn.execute("SELECT pg_advisory_xact_lock(782341905);")
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS raid_builder_registry (
                        id SMALLINT PRIMARY KEY CHECK (id = 1),
                        revision BIGINT NOT NULL DEFAULT 1,
                        content TEXT NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    CREATE TABLE IF NOT EXISTS raid_builder_preferences (
                        user_id BIGINT NOT NULL,
                        guild_id BIGINT NOT NULL,
                        content TEXT NOT NULL,
                        PRIMARY KEY (user_id, guild_id)
                    );
                """)
                exists = await conn.fetchval(
                    "SELECT revision FROM raid_builder_registry WHERE id=1"
                )
                if exists is None:
                    # Only consult the legacy file during the first import. Never
                    # overwrite an existing database from a checkout's old JSON.
                    content = json.dumps(
                        seed_factory(), ensure_ascii=False, allow_nan=False
                    )
                    await conn.execute(
                        "INSERT INTO raid_builder_registry (id, content) VALUES (1, $1)",
                        content,
                    )
        return await self.load()

    async def load(self):
        try:
            row = await self.pool.fetchrow(
                "SELECT revision, content FROM raid_builder_registry WHERE id=1"
            )
            if row is None:
                raise StorageError(
                    "Raid storage is missing. Reload the builder extension."
                )
            content = json.loads(row["content"])
            if not isinstance(content, dict) or not isinstance(
                content.get("definitions"), dict
            ):
                raise StorageError(
                    "Raid storage is invalid; existing data has been preserved."
                )
            return content, row["revision"]
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError(
                "Raid storage is unavailable; please retry. No defaults were written."
            ) from exc

    async def save(self, registry, expected_revision):
        content = json.dumps(registry, ensure_ascii=False, allow_nan=False)
        try:
            revision = await self.pool.fetchval(
                """
                UPDATE raid_builder_registry
                SET content=$1, revision=revision+1, updated_at=NOW()
                WHERE id=1 AND revision=$2 RETURNING revision
            """,
                content,
                expected_revision,
            )
        except Exception as exc:
            raise StorageError(
                "Raid save failed. Your changes were not confirmed; please retry."
            ) from exc
        if revision is None:
            raise StaleEdit(
                "Another editor saved changes. Reopen the page and retry; their work was preserved."
            )
        return revision

    async def preferences(self, user_id, guild_id):
        content = await self.pool.fetchval(
            "SELECT content FROM raid_builder_preferences WHERE user_id=$1 AND guild_id=$2",
            user_id,
            guild_id,
        )
        return json.loads(content) if content else {}

    async def save_preferences(self, user_id, guild_id, content):
        await self.pool.execute(
            """
            INSERT INTO raid_builder_preferences (user_id, guild_id, content) VALUES ($1, $2, $3)
            ON CONFLICT (user_id, guild_id) DO UPDATE SET content=EXCLUDED.content
        """,
            user_id,
            guild_id,
            json.dumps(content),
        )


def registry_edit(callback):
    """Serialize local mutations; reject stale forms and report durable save errors.

    Mutation callbacks must await _save_registry before acknowledging success.
    Restore unsaved partial form edits even when a handler catches ValueError.
    """

    @wraps(callback)
    async def wrapped(self, target, *args, **kwargs):
        panel = getattr(self, "builder_view", self)
        cog = getattr(panel, "cog", self)
        is_interaction = hasattr(target, "response")
        if is_interaction and target.user.id != panel.author.id:
            await target.response.send_message(
                "This raid builder panel is not for you.", ephemeral=True
            )
            return
        try:
            async with cog._edit_lock:
                await cog._refresh_registry_unlocked()
                expected = getattr(
                    self, "edit_revision", getattr(panel, "registry_revision", None)
                )
                if expected is not None and expected != cog.registry_revision:
                    raise StaleEdit(
                        "This panel is out of date. Reopen the builder before editing."
                    )
                before = copy.deepcopy(cog.registry)
                revision = cog.registry_revision
                try:
                    return await callback(self, target, *args, **kwargs)
                finally:
                    if cog.registry_revision == revision and cog.registry != before:
                        cog.registry = before
        except ValueError as exc:
            if is_interaction:
                if target.response.is_done():
                    await target.followup.send(str(exc), ephemeral=True)
                else:
                    await target.response.send_message(str(exc), ephemeral=True)
            else:
                await target.send(str(exc))

    return wrapped


def registry_navigation(callback):
    @wraps(callback)
    async def wrapped(self, interaction, *args, **kwargs):
        panel = self.builder_view
        if interaction.user.id != panel.author.id:
            await interaction.response.send_message(
                "This raid builder panel is not for you.", ephemeral=True
            )
            return
        try:
            async with panel.cog._edit_lock:
                await panel.cog._refresh_registry_unlocked()
                return await callback(self, interaction, *args, **kwargs)
        except StorageError as exc:
            if interaction.response.is_done():
                await interaction.followup.send(str(exc), ephemeral=True)
            else:
                await interaction.response.send_message(str(exc), ephemeral=True)

    return wrapped
