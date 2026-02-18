import asyncio
import json
import re

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiohttp
import discord

from discord.ext import commands, tasks

from cogs.shard_communication import user_on_cooldown as user_cooldown
from utils.checks import is_gm


class SetupCancelled(Exception):
    pass


class PatreonRequestError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"[{status}] {message}" if status else message)


@dataclass
class SyncResult:
    patrons: int = 0
    candidates: int = 0
    roles_added: int = 0
    roles_removed: int = 0
    tier_updates: int = 0
    pages: int = 0
    members_seen: int = 0
    active_members: int = 0
    mapped_members: int = 0
    error: str | None = None


class PatreonCore(commands.Cog):
    """Synchronize Patreon pledges with Discord roles and in-game tier values."""

    TOKEN_URL = "https://www.patreon.com/api/oauth2/token"
    CAMPAIGNS_URL = "https://www.patreon.com/api/oauth2/api/current_user/campaigns"
    MEMBERS_URL = "https://www.patreon.com/api/oauth2/v2/campaigns/{campaign_id}/members"
    CAMPAIGN_DETAILS_URL = "https://www.patreon.com/api/oauth2/v2/campaigns/{campaign_id}"

    def __init__(self, bot):
        self.bot = bot
        self.http_timeout = aiohttp.ClientTimeout(total=30)
        self.config_file = Path("patreon_config.json")
        self._sync_lock = asyncio.Lock()

        ids_section = getattr(self.bot.config, "ids", None)
        patreoncore_ids = getattr(ids_section, "patreoncore", {}) if ids_section else {}
        if not isinstance(patreoncore_ids, dict):
            patreoncore_ids = {}

        self.debug_user_id = self._parse_int(patreoncore_ids.get("debug_user_id"))
        self.guild_id = self._parse_int(patreoncore_ids.get("guild_id"))
        self.log_channel_id: int | None = None
        self.check_interval_seconds = 60 * 30

        self.client_id = ""
        self.client_secret = ""
        self.access_token = ""
        self.refresh_token = ""
        self.token_expires_at = self._utcnow() + timedelta(days=30)

        self.patreon_campaign_id: str | None = None

        self.tier_role_mapping: dict[str, int] = {}
        self.tier_level_mapping: dict[str, int] = {}
        self.tier_titles: dict[str, str] = {}
        self.tier_amounts: dict[str, int] = {}

        self.patrons_data: dict[int, list[str]] = {}
        self.last_updated: datetime | None = None
        self.last_sync_result: SyncResult | None = None

        self._load_config()

        self.sync_patrons_loop.change_interval(seconds=self.check_interval_seconds)
        self.sync_patrons_loop.start()

    def cog_unload(self):
        self.sync_patrons_loop.cancel()
        self._save_config()

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _parse_int(value: Any) -> int | None:
        try:
            if value is None:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        try:
            dt = datetime.fromisoformat(str(value))
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    @staticmethod
    def _extract_snowflake(value: str) -> int | None:
        if not value:
            return None
        if value.isdigit():
            return int(value)
        match = re.search(r"\d{15,22}", value)
        return int(match.group(0)) if match else None

    @staticmethod
    def _normalize_tier_role_mapping(raw: Any) -> dict[str, int]:
        if not isinstance(raw, dict):
            return {}
        mapping = {}
        for tier_id, role_id in raw.items():
            tier_key = str(tier_id).strip()
            parsed_role_id = PatreonCore._parse_int(role_id)
            if tier_key and parsed_role_id:
                mapping[tier_key] = parsed_role_id
        return mapping

    @staticmethod
    def _normalize_tier_level_mapping(raw: Any) -> dict[str, int]:
        if not isinstance(raw, dict):
            return {}
        mapping = {}
        for tier_id, level in raw.items():
            tier_key = str(tier_id).strip()
            parsed_level = PatreonCore._parse_int(level)
            if tier_key and parsed_level and parsed_level > 0:
                mapping[tier_key] = parsed_level
        return mapping

    def _snapshot_config(self) -> dict[str, Any]:
        return {
            "guild_id": self.guild_id,
            "log_channel_id": self.log_channel_id,
            "check_interval_seconds": self.check_interval_seconds,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_expires_at": self.token_expires_at.isoformat(),
            "patreon_campaign_id": self.patreon_campaign_id,
            "tier_role_mapping": dict(self.tier_role_mapping),
            "tier_level_mapping": dict(self.tier_level_mapping),
        }

    def _restore_config(self, snapshot: dict[str, Any]) -> None:
        self.guild_id = self._parse_int(snapshot.get("guild_id"))
        self.log_channel_id = self._parse_int(snapshot.get("log_channel_id"))
        self.check_interval_seconds = max(
            300, self._parse_int(snapshot.get("check_interval_seconds")) or 1800
        )
        self.client_id = str(snapshot.get("client_id") or "")
        self.client_secret = str(snapshot.get("client_secret") or "")
        self.access_token = str(snapshot.get("access_token") or "")
        self.refresh_token = str(snapshot.get("refresh_token") or "")
        self.token_expires_at = self._coerce_datetime(snapshot.get("token_expires_at")) or (
            self._utcnow() + timedelta(days=30)
        )
        campaign = snapshot.get("patreon_campaign_id")
        self.patreon_campaign_id = str(campaign).strip() if campaign else None
        self.tier_role_mapping = self._normalize_tier_role_mapping(
            snapshot.get("tier_role_mapping", {})
        )
        self.tier_level_mapping = self._normalize_tier_level_mapping(
            snapshot.get("tier_level_mapping", {})
        )
        self.sync_patrons_loop.change_interval(seconds=self.check_interval_seconds)

    def _load_config(self) -> None:
        try:
            if not self.config_file.exists():
                return

            with self.config_file.open("r", encoding="utf-8") as f:
                config = json.load(f)

            self.guild_id = self._parse_int(config.get("guild_id")) or self.guild_id
            self.log_channel_id = self._parse_int(config.get("log_channel_id"))

            interval_seconds = self._parse_int(config.get("check_interval_seconds"))
            legacy_interval = self._parse_int(config.get("check_interval"))
            interval = interval_seconds or legacy_interval or self.check_interval_seconds
            self.check_interval_seconds = max(300, interval)

            self.client_id = str(config.get("client_id") or self.client_id or "")
            self.client_secret = str(config.get("client_secret") or self.client_secret or "")
            self.access_token = str(config.get("access_token") or self.access_token or "")
            self.refresh_token = str(config.get("refresh_token") or self.refresh_token or "")

            token_expires_at = self._coerce_datetime(config.get("token_expires_at"))
            if token_expires_at:
                self.token_expires_at = token_expires_at

            campaign_id = config.get("patreon_campaign_id")
            self.patreon_campaign_id = str(campaign_id).strip() if campaign_id else None

            self.tier_role_mapping = self._normalize_tier_role_mapping(
                config.get("tier_role_mapping", {})
            )
            self.tier_level_mapping = self._normalize_tier_level_mapping(
                config.get("tier_level_mapping", {})
            )

            print("[PatreonCore] Configuration loaded successfully.")
        except Exception as e:
            print(f"[PatreonCore] Error loading config: {e}")

    def _save_config(self) -> None:
        try:
            config = {
                "guild_id": self.guild_id,
                "log_channel_id": self.log_channel_id,
                "check_interval_seconds": self.check_interval_seconds,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "token_expires_at": self.token_expires_at.isoformat(),
                "patreon_campaign_id": self.patreon_campaign_id,
                "tier_role_mapping": self.tier_role_mapping,
                "tier_level_mapping": self.tier_level_mapping,
            }
            with self.config_file.open("w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            print("[PatreonCore] Configuration saved successfully.")
        except Exception as e:
            print(f"[PatreonCore] Error saving config: {e}")

    def _is_minimally_configured(self) -> bool:
        return bool(self.guild_id and (self.access_token or self.refresh_token))

    async def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> tuple[int, Any | None, str]:
        session = getattr(self.bot, "session", None)
        owns_session = session is None or session.closed
        if owns_session:
            session = aiohttp.ClientSession(timeout=self.http_timeout)

        try:
            async with session.request(
                method,
                url,
                headers=headers,
                params=params,
                data=data,
                timeout=self.http_timeout,
            ) as response:
                text = await response.text()
                payload = None
                if text:
                    try:
                        payload = json.loads(text)
                    except json.JSONDecodeError:
                        payload = None
                return response.status, payload, text
        finally:
            if owns_session:
                await session.close()

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        status, payload, text = await self._request(
            method, url, headers=headers, params=params, data=data
        )
        if status < 200 or status >= 300:
            raise PatreonRequestError(status, text[:400] if text else "Request failed.")
        if not isinstance(payload, dict):
            raise PatreonRequestError(status, "Expected a JSON object response.")
        return payload

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}

    async def refresh_access_token(self) -> bool:
        if not self.client_id or not self.client_secret or not self.refresh_token:
            print("[PatreonCore] Missing client credentials or refresh token.")
            return False

        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        try:
            data = await self._request_json("POST", self.TOKEN_URL, data=payload)
        except PatreonRequestError as e:
            print(f"[PatreonCore] Token refresh failed: {e}")
            return False
        except Exception as e:
            print(f"[PatreonCore] Unexpected token refresh error: {e}")
            return False

        new_access_token = data.get("access_token")
        if not new_access_token:
            print("[PatreonCore] Token refresh response did not contain access_token.")
            return False

        self.access_token = str(new_access_token)
        new_refresh = data.get("refresh_token")
        if new_refresh:
            self.refresh_token = str(new_refresh)

        expires_in = self._parse_int(data.get("expires_in")) or 2592000
        self.token_expires_at = self._utcnow() + timedelta(seconds=expires_in)
        self._save_config()
        print("[PatreonCore] Access token refreshed.")
        return True

    async def _ensure_access_token(self) -> bool:
        if not self.access_token and self.refresh_token:
            return await self.refresh_access_token()

        if self.token_expires_at <= self._utcnow() + timedelta(minutes=5):
            if self.refresh_token:
                refreshed = await self.refresh_access_token()
                if refreshed:
                    return True
            return bool(self.access_token)

        return bool(self.access_token)

    async def _patreon_get_json(
        self, url: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not await self._ensure_access_token():
            raise PatreonRequestError(0, "Patreon access token is not configured.")

        status, payload, text = await self._request(
            "GET", url, headers=self._auth_headers(), params=params
        )
        if status == 401:
            refreshed = await self.refresh_access_token()
            if refreshed:
                status, payload, text = await self._request(
                    "GET", url, headers=self._auth_headers(), params=params
                )

        if status < 200 or status >= 300:
            raise PatreonRequestError(status, text[:400] if text else "Patreon API request failed.")
        if not isinstance(payload, dict):
            raise PatreonRequestError(status, "Patreon API returned invalid JSON.")
        return payload

    async def get_campaign_id(self, force_refresh: bool = False) -> str | None:
        if self.patreon_campaign_id and not force_refresh:
            return self.patreon_campaign_id

        data = await self._patreon_get_json(self.CAMPAIGNS_URL)
        campaigns = data.get("data")
        if isinstance(campaigns, dict):
            campaigns = [campaigns]
        if not isinstance(campaigns, list) or not campaigns:
            return None

        first_campaign = campaigns[0] if isinstance(campaigns[0], dict) else {}
        campaign_id = str(first_campaign.get("id") or "").strip()
        if not campaign_id:
            return None

        self.patreon_campaign_id = campaign_id
        self._save_config()
        return campaign_id

    async def fetch_tiers(self) -> dict[str, dict[str, Any]]:
        campaign_id = await self.get_campaign_id()
        if not campaign_id:
            return {}

        url = self.CAMPAIGN_DETAILS_URL.format(campaign_id=campaign_id)
        params = {"include": "tiers", "fields[tier]": "title,amount_cents"}
        data = await self._patreon_get_json(url, params=params)

        tiers: dict[str, dict[str, Any]] = {}
        for item in data.get("included", []):
            if not isinstance(item, dict) or item.get("type") != "tier":
                continue
            tier_id = str(item.get("id") or "").strip()
            if not tier_id:
                continue
            attrs = item.get("attributes", {}) if isinstance(item.get("attributes"), dict) else {}
            amount_cents = self._parse_int(attrs.get("amount_cents"))
            tiers[tier_id] = {
                "title": str(attrs.get("title") or f"Tier {tier_id}"),
                "amount_cents": amount_cents if amount_cents is not None else 0,
            }
        return tiers

    @staticmethod
    def _extract_discord_user_id(user_obj: dict[str, Any]) -> int | None:
        attrs = user_obj.get("attributes", {})
        if not isinstance(attrs, dict):
            return None
        social = attrs.get("social_connections", {})
        if not isinstance(social, dict):
            return None
        discord_data = social.get("discord", {})
        if not isinstance(discord_data, dict):
            return None
        user_id = discord_data.get("user_id")
        try:
            return int(user_id)
        except (TypeError, ValueError):
            return None

    async def fetch_active_patrons(
        self,
    ) -> tuple[dict[int, list[str]], dict[str, int], dict[str, str], dict[str, int]]:
        campaign_id = await self.get_campaign_id()
        if not campaign_id:
            raise PatreonRequestError(0, "No campaign ID available.")

        next_url = self.MEMBERS_URL.format(campaign_id=campaign_id)
        params: dict[str, Any] | None = {
            "include": "user,currently_entitled_tiers",
            "fields[member]": "patron_status,currently_entitled_amount_cents",
            "fields[user]": "social_connections",
            "fields[tier]": "title,amount_cents",
            "page[count]": 100,
        }

        patrons: dict[int, set[str]] = defaultdict(set)
        known_user_discord_map: dict[str, int] = {}
        tier_amounts: dict[str, int] = {}
        tier_titles: dict[str, str] = {}

        pages = 0
        members_seen = 0
        active_members = 0
        mapped_members = 0

        while next_url:
            payload = await self._patreon_get_json(next_url, params=params)
            params = None
            pages += 1

            included = payload.get("included", [])
            if isinstance(included, list):
                for item in included:
                    if not isinstance(item, dict):
                        continue
                    item_type = item.get("type")
                    item_id = str(item.get("id") or "").strip()
                    if not item_id:
                        continue

                    if item_type == "user":
                        discord_id = self._extract_discord_user_id(item)
                        if discord_id:
                            known_user_discord_map[item_id] = discord_id
                    elif item_type == "tier":
                        attrs = item.get("attributes", {})
                        if not isinstance(attrs, dict):
                            attrs = {}
                        title = str(attrs.get("title") or f"Tier {item_id}")
                        amount = self._parse_int(attrs.get("amount_cents")) or 0
                        tier_titles[item_id] = title
                        tier_amounts[item_id] = amount

            members = payload.get("data", [])
            if isinstance(members, list):
                for member in members:
                    if not isinstance(member, dict):
                        continue
                    members_seen += 1

                    attrs = member.get("attributes", {})
                    if not isinstance(attrs, dict):
                        attrs = {}
                    if attrs.get("patron_status") != "active_patron":
                        continue
                    active_members += 1

                    relationships = member.get("relationships", {})
                    if not isinstance(relationships, dict):
                        relationships = {}
                    user_data = relationships.get("user", {})
                    if not isinstance(user_data, dict):
                        user_data = {}
                    user_rel = user_data.get("data", {})
                    if not isinstance(user_rel, dict):
                        user_rel = {}
                    patreon_user_id = str(user_rel.get("id") or "").strip()
                    if not patreon_user_id:
                        continue

                    discord_id = known_user_discord_map.get(patreon_user_id)
                    if not discord_id:
                        continue

                    entitled = relationships.get("currently_entitled_tiers", {})
                    if not isinstance(entitled, dict):
                        entitled = {}
                    entitled_data = entitled.get("data", [])
                    if not isinstance(entitled_data, list):
                        entitled_data = []

                    for tier in entitled_data:
                        if not isinstance(tier, dict):
                            continue
                        tier_id = str(tier.get("id") or "").strip()
                        if tier_id:
                            patrons[discord_id].add(tier_id)

                    mapped_members += 1

            links = payload.get("links", {})
            if not isinstance(links, dict):
                links = {}
            next_link = links.get("next")
            next_url = str(next_link).strip() if next_link else None

        patron_map = {uid: sorted(tiers) for uid, tiers in patrons.items()}
        stats = {
            "pages": pages,
            "members_seen": members_seen,
            "active_members": active_members,
            "mapped_members": mapped_members,
        }
        return patron_map, tier_amounts, tier_titles, stats

    def _desired_role_ids_for_tiers(self, tier_ids: list[str]) -> set[int]:
        role_ids = set()
        for tier_id in tier_ids:
            role_id = self.tier_role_mapping.get(tier_id)
            if role_id:
                role_ids.add(role_id)
        return role_ids

    def _tier_level_for_tiers(self, tier_ids: list[str], tier_amounts: dict[str, int]) -> int:
        if not tier_ids:
            return 0

        explicit_level = 0
        for tier_id in tier_ids:
            explicit_level = max(explicit_level, self.tier_level_mapping.get(tier_id, 0))
        if explicit_level > 0:
            return explicit_level

        amounts = sorted({amt for amt in tier_amounts.values() if isinstance(amt, int) and amt > 0})
        if not amounts:
            return 1

        highest_amount = max(tier_amounts.get(tier_id, 0) for tier_id in tier_ids)
        if highest_amount <= 0:
            return 1

        return sum(1 for amount in amounts if amount <= highest_amount)

    async def _bulk_update_tiers(self, tier_by_user: dict[int, int]) -> int:
        if not tier_by_user:
            return 0

        user_ids = list(tier_by_user.keys())
        async with self.bot.pool.acquire() as conn:
            existing_rows = await conn.fetch(
                'SELECT "user", "tier" FROM profile WHERE "user" = ANY($1::bigint[])',
                user_ids,
            )
            current = {int(row["user"]): int(row["tier"] or 0) for row in existing_rows}

            changed = [
                (user_id, level)
                for user_id, level in tier_by_user.items()
                if user_id in current and current[user_id] != level
            ]
            if not changed:
                return 0

            changed_user_ids = [user_id for user_id, _ in changed]
            changed_levels = [level for _, level in changed]

            await conn.execute(
                'UPDATE profile AS p SET "tier" = src.tier '
                "FROM UNNEST($1::bigint[], $2::integer[]) AS src(user_id, tier) "
                'WHERE p."user" = src.user_id;',
                changed_user_ids,
                changed_levels,
            )
            return len(changed)

    async def _sync_roles(self, guild: discord.Guild, patrons: dict[int, list[str]]) -> tuple[int, int, int]:
        tracked_role_ids = set(self.tier_role_mapping.values())
        if not tracked_role_ids:
            return 0, 0, 0

        candidate_ids = set(patrons.keys()) | set(self.patrons_data.keys())
        for role_id in tracked_role_ids:
            role = guild.get_role(role_id)
            if role:
                candidate_ids.update(member.id for member in role.members)

        roles_added = 0
        roles_removed = 0

        for member_id in candidate_ids:
            member = guild.get_member(member_id)
            if member is None:
                try:
                    member = await guild.fetch_member(member_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    continue

            desired_role_ids = self._desired_role_ids_for_tiers(patrons.get(member_id, []))
            current_role_ids = {role.id for role in member.roles if role.id in tracked_role_ids}

            to_add = desired_role_ids - current_role_ids
            to_remove = current_role_ids - desired_role_ids

            if to_add:
                add_roles = [guild.get_role(role_id) for role_id in to_add]
                add_roles = [role for role in add_roles if role is not None]
                if add_roles:
                    try:
                        await member.add_roles(*add_roles, reason="Patreon sync")
                        roles_added += len(add_roles)
                    except (discord.Forbidden, discord.HTTPException):
                        pass

            if to_remove:
                remove_roles = [guild.get_role(role_id) for role_id in to_remove]
                remove_roles = [role for role in remove_roles if role is not None]
                if remove_roles:
                    try:
                        await member.remove_roles(*remove_roles, reason="Patreon sync")
                        roles_removed += len(remove_roles)
                    except (discord.Forbidden, discord.HTTPException):
                        pass

        return len(candidate_ids), roles_added, roles_removed

    def _format_sync_result(self, result: SyncResult) -> str:
        if result.error:
            return f"Patreon sync failed: {result.error}"
        return (
            "Patreon sync complete: "
            f"{result.patrons} patrons, "
            f"{result.candidates} role candidates, "
            f"+{result.roles_added}/-{result.roles_removed} role changes, "
            f"{result.tier_updates} tier DB updates, "
            f"{result.pages} page(s), "
            f"{result.members_seen} members seen, "
            f"{result.active_members} active, "
            f"{result.mapped_members} mapped."
        )

    async def run_sync(self, *, manual: bool = False) -> SyncResult:
        result = SyncResult()

        if not self._is_minimally_configured():
            result.error = "Missing guild ID or Patreon token credentials. Run patreonsetup."
            self.last_sync_result = result
            return result

        async with self._sync_lock:
            try:
                patrons, tier_amounts, tier_titles, stats = await self.fetch_active_patrons()
                result.patrons = len(patrons)
                result.pages = stats.get("pages", 0)
                result.members_seen = stats.get("members_seen", 0)
                result.active_members = stats.get("active_members", 0)
                result.mapped_members = stats.get("mapped_members", 0)

                guild = self.bot.get_guild(self.guild_id)
                if not guild:
                    result.error = f"Guild {self.guild_id} not found."
                    self.last_sync_result = result
                    return result

                tier_by_user: dict[int, int] = {user_id: 0 for user_id in self.patrons_data.keys()}
                for user_id, tier_ids in patrons.items():
                    tier_by_user[user_id] = self._tier_level_for_tiers(tier_ids, tier_amounts)

                result.tier_updates = await self._bulk_update_tiers(tier_by_user)
                result.candidates, result.roles_added, result.roles_removed = await self._sync_roles(
                    guild, patrons
                )

                self.patrons_data = patrons
                self.tier_titles = tier_titles
                self.tier_amounts = tier_amounts
                self.last_updated = self._utcnow()
                self.last_sync_result = result

                if manual:
                    await self.log_message(self._format_sync_result(result))
                return result
            except PatreonRequestError as e:
                result.error = str(e)
                self.last_sync_result = result
                print(f"[PatreonCore] API error during sync: {e}")
                return result
            except Exception as e:
                result.error = str(e)
                self.last_sync_result = result
                print(f"[PatreonCore] Unexpected sync error: {e}")
                return result

    async def log_message(self, message: str):
        if not self.log_channel_id:
            return
        channel = self.bot.get_channel(self.log_channel_id)
        if not channel:
            return
        try:
            await channel.send(message)
        except Exception as e:
            print(f"[PatreonCore] Failed to send log message: {e}")

    @tasks.loop(seconds=1800)
    async def sync_patrons_loop(self):
        if not self._is_minimally_configured():
            return
        result = await self.run_sync(manual=False)
        if result.error:
            print(f"[PatreonCore] {result.error}")

    @sync_patrons_loop.before_loop
    async def before_sync_patrons_loop(self):
        await self.bot.wait_until_ready()

    async def _wizard_wait(self, ctx, *, timeout: int = 300) -> str:
        def check(msg):
            return msg.author.id == ctx.author.id and msg.channel.id == ctx.channel.id

        msg = await self.bot.wait_for("message", check=check, timeout=timeout)
        content = msg.content.strip()

        if ctx.guild is None:
            try:
                await msg.delete()
            except discord.HTTPException:
                pass

        if content.lower() in {"cancel", "abort", "stop"}:
            raise SetupCancelled()
        return content

    async def _wizard_ask(
        self,
        ctx,
        prompt: str,
        *,
        default: str | None = None,
        allow_empty: bool = False,
    ) -> str:
        default_text = f" (default: {default})" if default is not None else ""
        await ctx.send(f"{prompt}{default_text}")

        while True:
            value = await self._wizard_wait(ctx)
            if not value:
                if default is not None:
                    return default
                if allow_empty:
                    return ""
                await ctx.send("This value cannot be empty.")
                continue
            if allow_empty and value.lower() in {"skip", "none"}:
                return ""
            return value

    @staticmethod
    def _chunk_text(text: str, limit: int = 1900) -> list[str]:
        if len(text) <= limit:
            return [text]
        chunks = []
        start = 0
        while start < len(text):
            chunks.append(text[start : start + limit])
            start += limit
        return chunks

    @commands.command()
    @is_gm()
    async def patreonsetup(self, ctx):
        """DM-only setup wizard for PatreonCore configuration."""
        if ctx.guild is not None:
            return await ctx.send(
                "Run this command in DM with the bot. It collects Patreon secrets."
            )

        snapshot = self._snapshot_config()
        await ctx.send(
            "Patreon setup started. Reply `cancel` anytime to abort and restore previous config."
        )

        try:
            guild_id = None
            while guild_id is None:
                raw_guild = await self._wizard_ask(ctx, "1) Enter the guild ID for role sync:")
                guild_id = self._extract_snowflake(raw_guild)
                if guild_id is None:
                    await ctx.send("Invalid guild ID. Please try again.")

            log_channel_id = None
            while True:
                raw_log = await self._wizard_ask(
                    ctx,
                    "2) Enter log channel ID (or `skip`):",
                    allow_empty=True,
                )
                if not raw_log:
                    log_channel_id = None
                    break
                parsed = self._extract_snowflake(raw_log)
                if parsed is None:
                    await ctx.send("Invalid channel ID. Please try again.")
                    continue
                log_channel_id = parsed
                break

            client_id = await self._wizard_ask(ctx, "3) Patreon OAuth Client ID:")
            client_secret = await self._wizard_ask(ctx, "4) Patreon OAuth Client Secret:")
            access_token = await self._wizard_ask(ctx, "5) Patreon Access Token:")
            refresh_token = await self._wizard_ask(ctx, "6) Patreon Refresh Token:")

            interval_default = str(max(5, self.check_interval_seconds // 60))
            interval_minutes = None
            while interval_minutes is None:
                raw_interval = await self._wizard_ask(
                    ctx,
                    "7) Sync interval in minutes (minimum 5):",
                    default=interval_default,
                )
                parsed_interval = self._parse_int(raw_interval)
                if parsed_interval is None or parsed_interval < 5:
                    await ctx.send("Interval must be an integer >= 5.")
                    continue
                interval_minutes = parsed_interval

            raw_campaign_id = await self._wizard_ask(
                ctx,
                "8) Patreon campaign ID (or `skip` to auto-detect):",
                allow_empty=True,
            )
            campaign_id = str(raw_campaign_id).strip() if raw_campaign_id else None

            self.guild_id = guild_id
            self.log_channel_id = log_channel_id
            self.client_id = client_id.strip()
            self.client_secret = client_secret.strip()
            self.access_token = access_token.strip()
            self.refresh_token = refresh_token.strip()
            self.check_interval_seconds = interval_minutes * 60
            self.patreon_campaign_id = campaign_id or None

            self.sync_patrons_loop.change_interval(seconds=self.check_interval_seconds)

            if not self.patreon_campaign_id:
                auto_campaign_id = await self.get_campaign_id(force_refresh=True)
                if not auto_campaign_id:
                    raise RuntimeError("Could not auto-detect campaign ID from Patreon API.")
                self.patreon_campaign_id = auto_campaign_id

            tiers = await self.fetch_tiers()
            if tiers:
                tier_lines = ["Detected tiers (tier_id | title | amount):"]
                for tier_id, info in sorted(
                    tiers.items(), key=lambda item: item[1].get("amount_cents", 0)
                ):
                    amount_cents = info.get("amount_cents", 0)
                    amount_display = f"${amount_cents / 100:.2f}" if amount_cents else "$0.00"
                    tier_lines.append(f"{tier_id} | {info.get('title', f'Tier {tier_id}')} | {amount_display}")
                for chunk in self._chunk_text("\n".join(tier_lines)):
                    await ctx.send(f"```{chunk}```")
            else:
                await ctx.send(
                    "No tiers were returned from Patreon. You can still map tier IDs manually."
                )

            await ctx.send(
                "9) Send tier mappings one per message in format `tier_id role_id tier_level`.\n"
                "`tier_level` is optional and defaults to 1.\n"
                "Send `done` when finished."
            )

            tier_role_mapping: dict[str, int] = {}
            tier_level_mapping: dict[str, int] = {}

            while True:
                line = await self._wizard_wait(ctx)
                if not line:
                    continue
                if line.lower() == "done":
                    break

                parts = [p for p in re.split(r"[:\s,]+", line.strip()) if p]
                if len(parts) < 2:
                    await ctx.send("Invalid format. Use `tier_id role_id tier_level`.")
                    continue

                tier_id = parts[0]
                role_id = self._extract_snowflake(parts[1])
                if not role_id:
                    await ctx.send("Invalid role ID.")
                    continue

                level = 1
                if len(parts) >= 3:
                    parsed_level = self._parse_int(parts[2])
                    if not parsed_level or parsed_level < 1:
                        await ctx.send("Tier level must be a positive integer.")
                        continue
                    level = parsed_level

                tier_role_mapping[tier_id] = role_id
                tier_level_mapping[tier_id] = level
                await ctx.send(f"Mapped tier `{tier_id}` -> role `{role_id}` (level {level}).")

            if not tier_role_mapping:
                raise RuntimeError("At least one tier mapping is required.")

            self.tier_role_mapping = tier_role_mapping
            self.tier_level_mapping = tier_level_mapping
            self._save_config()

            await ctx.send("Configuration saved. Running initial Patreon sync...")
            sync_result = await self.run_sync(manual=True)
            await ctx.send(self._format_sync_result(sync_result))
        except SetupCancelled:
            self._restore_config(snapshot)
            self._save_config()
            await ctx.send("Setup cancelled. Previous configuration restored.")
        except asyncio.TimeoutError:
            self._restore_config(snapshot)
            self._save_config()
            await ctx.send("Setup timed out. Previous configuration restored.")
        except Exception as e:
            self._restore_config(snapshot)
            self._save_config()
            await ctx.send(f"Setup failed: {e}. Previous configuration restored.")

    @commands.command()
    @is_gm()
    async def forcesync(self, ctx):
        """Force an immediate Patreon sync."""
        await ctx.send("Running Patreon sync...")
        result = await self.run_sync(manual=True)
        await ctx.send(self._format_sync_result(result))

    @commands.command()
    @is_gm()
    async def patronstatus(self, ctx):
        """Show PatreonCore status and sync health."""
        embed = discord.Embed(title="PatreonCore Status", color=0xFF5441)
        embed.add_field(
            name="Configured",
            value="Yes" if self._is_minimally_configured() else "No",
            inline=True,
        )
        embed.add_field(name="Guild ID", value=str(self.guild_id or "Not set"), inline=True)
        embed.add_field(
            name="Campaign ID",
            value=str(self.patreon_campaign_id or "Auto/Not set"),
            inline=True,
        )
        embed.add_field(
            name="Log Channel",
            value=str(self.log_channel_id or "Not set"),
            inline=True,
        )
        embed.add_field(
            name="Sync Interval",
            value=f"{self.check_interval_seconds // 60} minute(s)",
            inline=True,
        )
        embed.add_field(
            name="Tier Mappings",
            value=str(len(self.tier_role_mapping)),
            inline=True,
        )

        if self.last_updated:
            embed.add_field(
                name="Last Updated",
                value=self.last_updated.strftime("%Y-%m-%d %H:%M:%S UTC"),
                inline=False,
            )
        else:
            embed.add_field(name="Last Updated", value="Never", inline=False)

        if self.last_sync_result:
            embed.add_field(
                name="Last Sync",
                value=self._format_sync_result(self.last_sync_result)[:1024],
                inline=False,
            )

        if self.sync_patrons_loop.is_running() and self.sync_patrons_loop.next_iteration:
            next_sync = self.sync_patrons_loop.next_iteration
            if next_sync.tzinfo is None:
                next_sync = next_sync.replace(tzinfo=timezone.utc)
            remaining = next_sync - self._utcnow()
            if remaining.total_seconds() < 0:
                remaining = timedelta(0)
            embed.set_footer(text=f"Next sync in {str(remaining).split('.')[0]}")

        await ctx.send(embed=embed)

    @commands.command()
    @is_gm()
    async def patronlist(self, ctx):
        """List currently tracked patrons and their tiers."""
        if not self.patrons_data:
            return await ctx.send("No patron data is cached yet.")

        guild = self.bot.get_guild(self.guild_id) if self.guild_id else None
        embed = discord.Embed(
            title="Patreon Supporters",
            description=f"Tracked patrons: {len(self.patrons_data)}",
            color=0xFF5441,
        )

        displayed = 0
        for user_id, tier_ids in list(self.patrons_data.items())[:25]:
            member = guild.get_member(user_id) if guild else None
            name = member.display_name if member else str(user_id)
            tier_names = [self.tier_titles.get(tier_id, f"Tier {tier_id}") for tier_id in tier_ids]
            embed.add_field(
                name=name,
                value=", ".join(tier_names) if tier_names else "No entitled tier",
                inline=False,
            )
            displayed += 1

        if displayed < len(self.patrons_data):
            embed.set_footer(text=f"Showing {displayed} of {len(self.patrons_data)} patrons")

        await ctx.send(embed=embed)

    @commands.command()
    @is_gm()
    async def refreshtoken(self, ctx):
        """Manually refresh Patreon OAuth access token."""
        await ctx.send("Refreshing Patreon token...")
        success = await self.refresh_access_token()
        if success:
            await ctx.send(
                "Token refreshed. "
                f"Expires at {self.token_expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}."
            )
        else:
            await ctx.send("Token refresh failed. Check logs/config.")

    @commands.command()
    @user_cooldown(2764800)  # 32 days
    async def redeemweapontokens(self, ctx):
        """Redeem 5 weapon tokens if user has Patreon tier 1 or higher."""
        async with self.bot.pool.acquire() as conn:
            patron_tier = await conn.fetchval(
                'SELECT "tier" FROM profile WHERE "user"=$1',
                ctx.author.id,
            )

            if patron_tier is None or patron_tier < 1:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(
                    "You need to be a patron (tier 1 or higher) to redeem weapon tokens."
                )

            try:
                await conn.execute(
                    'UPDATE profile SET "weapontoken"="weapontoken"+5 WHERE "user"=$1',
                    ctx.author.id,
                )

                new_balance = await conn.fetchval(
                    'SELECT "weapontoken" FROM profile WHERE "user"=$1',
                    ctx.author.id,
                )

                if self.log_channel_id:
                    log_channel = self.bot.get_channel(self.log_channel_id)
                    if log_channel:
                        await log_channel.send(
                            "Weapon Token Redemption: "
                            f"{ctx.author.mention} ({ctx.author.id}) redeemed 5 weapon tokens as tier {patron_tier}."
                        )

                embed = discord.Embed(
                    title="Weapon Tokens Redeemed",
                    description="Thank you for supporting us on Patreon.",
                    color=0x3CB371,
                )
                embed.add_field(name="Tokens Added", value="5", inline=True)
                embed.add_field(name="New Balance", value=f"{new_balance:,}", inline=True)
                embed.add_field(name="Patron Tier", value=f"Tier {patron_tier}", inline=True)
                embed.set_footer(text="You can redeem this once every 32 days.")
                await ctx.send(embed=embed)
            except Exception as e:
                await self.bot.reset_cooldown(ctx)
                await ctx.send(f"Error updating weapon tokens: {e}")
                print(f"[PatreonCore] redeemweapontokens error for {ctx.author.id}: {e}")


async def setup(bot):
    await bot.add_cog(PatreonCore(bot))
