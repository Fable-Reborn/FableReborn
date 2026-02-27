"""
The IdleRPG Discord Bot
Copyright (C) 2018-2021 Diniboy and Gelbpunkt

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
from typing import Any

import tomli


class BotSection:
    __slots__ = {
        "version",
        "token",
        "initial_extensions",
        "global_prefix",
        "is_beta",
        "is_custom",
        "global_cooldown",
        "donator_cooldown",
    }

    def __init__(self, data: dict[str, Any]) -> None:
        self.version = data.get("version", "unknown")
        self.token = data["token"]
        self.initial_extensions = data.get("initial_extensions", [])
        self.global_prefix = data.get("global_prefix", "$")
        self.is_beta = data.get("is_beta", True)
        self.is_custom = data.get("is_custom", False)
        self.global_cooldown = data.get("global_cooldown", 3)
        self.donator_cooldown = data.get("donator_cooldown", 2)


class DonatorRole:
    __slots__ = {"id", "tier"}

    def __init__(self, data: dict[str, Any]):
        self.id = data.get("id", 0)
        self.tier = data.get("tier", "basic")


class ExternalSection:
    __slots__ = {
        "patreon_token",
        "imgur_token",
        "openai",
        "pixelcut_key",
        "okapi_token",
        "traviapi",
        "base_url",
        "okapi_url",
        "proxy_url",
        "r2_account_id",
        "r2_endpoint_url",
        "r2_access_key_id",
        "r2_secret_access_key",
        "r2_bucket",
        "r2_public_base_url",
        "donator_roles",
    }

    def __init__(self, data: dict[str, Any]) -> None:
        self.patreon_token = data.get("patreon_token", None)
        self.imgur_token = data.get("imgur_token", None)
        self.openai = data.get("openai", None)
        self.pixelcut_key = data.get("pixelcut_key", None)
        self.okapi_token = data.get("okapi_token", None)
        self.traviapi = data.get("traviapi", None)
        self.base_url = data.get("base_url", "https://idlerpg.xyz")
        self.okapi_url = data.get("okapi_url", "http://localhost:3000")
        self.proxy_url = data.get("proxy_url", None)
        self.r2_account_id = data.get("r2_account_id", None)
        self.r2_endpoint_url = data.get("r2_endpoint_url", None)
        self.r2_access_key_id = data.get("r2_access_key_id", None)
        self.r2_secret_access_key = data.get("r2_secret_access_key", None)
        self.r2_bucket = data.get("r2_bucket", None)
        self.r2_public_base_url = data.get("r2_public_base_url", None)
        self.donator_roles = [DonatorRole(i) for i in data.get("donator_roles", [])]


class DatabaseSection:
    __slots__ = {
        "postgres_name",
        "postgres_user",
        "postgres_port",
        "postgres_host",
        "postgres_password",
        "redis_host",
        "redis_port",
        "redis_database",
        "redis_shard_announce_channel",
    }

    def __init__(self, data: dict[str, Any]) -> None:
        self.postgres_name = data.get("postgres_name", "idlerpg")
        self.postgres_user = data.get("postgres_user", "lunar")
        self.postgres_port = data.get("postgres_port", 5432)
        self.postgres_host = data.get("postgres_host", "127.0.0.1")
        self.postgres_password = data.get("postgres_password", "")
        self.redis_host = data.get("redis_host", "127.0.0.1")
        self.redis_port = data.get("redis_port", 6379)
        self.redis_database = data.get("redis_database", 0)
        self.redis_shard_announce_channel = data.get(
            "redis_shard_announce_channel", "guild_channel"
        )

class Second_DatabaseSection:
    __slots__ = {
        "postgres_name",
        "postgres_user",
        "postgres_port",
        "postgres_host",
        "postgres_password",
    }

    def __init__(self, data: dict[str, Any]) -> None:
        self.postgres_name = data.get("postgres_name", "OG-IdleRPG")
        self.postgres_user = data.get("postgres_user", "lunar")
        self.postgres_port = data.get("postgres_port", 5432)
        self.postgres_host = data.get("postgres_host", "127.0.0.1")
        self.postgres_password = data.get("postgres_password", "")


class StatisticsSection:
    __slots__ = {"topggtoken", "bfdtoken", "dbltoken", "join_channel", "sentry_url"}

    def __init__(self, data: dict[str, Any]) -> None:
        self.topggtoken = data.get("topggtoken", None)
        self.bfdtoken = data.get("bfdtoken", None)
        self.dbltoken = data.get("dbltoken", None)
        self.join_channel = data.get("join_channel", None)
        self.sentry_url = data.get("sentry_url", None)


class LauncherSection:
    __slots__ = {"additional_shards", "shards_per_cluster"}

    def __init__(self, data: dict[str, Any]) -> None:
        self.additional_shards = data.get("additional_shards", 8)
        self.shards_per_cluster = data.get("shards_per_cluster", 8)


class GameSection:
    __slots__ = {
        "game_masters",
        "banned_guilds",
        "support_server_id",
        "raid_channel",
        "gm_log_channel",
        "gm_log_createmonster_channel",
        "gm_log_weapon_channel",
        "helpme_channel",
        "official_tournament_channel_id",
        "bot_event_channel",
        "primary_colour",
        "member_role",
        "support_team_role",
    }

    def __init__(self, data: dict[str, Any]) -> None:
        self.game_masters = data.get("game_masters", [])
        self.banned_guilds = data.get("banned_guilds", [])
        self.support_server_id = data.get("support_server_id", None)
        self.raid_channel = data.get("raid_channel", None)
        self.gm_log_channel = data.get("gm_log_channel", None)
        self.gm_log_createmonster_channel = data.get("gm_log_createmonster_channel", None)
        self.gm_log_weapon_channel = data.get("gm_log_weapon_channel", None)
        self.helpme_channel = data.get("helpme_channel", None)
        self.official_tournament_channel_id = data.get(
            "official_tournament_channel_id", None
        )
        self.bot_event_channel = data.get("bot_event_channel", None)
        self.primary_colour = data.get("primary_colour", 16759808)
        self.member_role = data.get("member_role", None)
        self.support_team_role = data.get("support_team_role", None)


class MusicSection:
    __slots__ = {"query_endpoint", "resolve_endpoint", "nodes"}

    def __init__(self, data: dict[str, Any]) -> None:
        self.query_endpoint = data.get("query_endpoint", None)
        self.resolve_endpoint = data.get("resolve_endpoint", None)
        self.nodes = data.get("nodes", [])


class IdsSection:
    __slots__ = {"_data"}

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data if isinstance(data, dict) else {}

    def get_section(self, name: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
        if default is None:
            default = {}
        value = self._data.get(name, default)
        return value if isinstance(value, dict) else default

    def __getattr__(self, name: str) -> dict[str, Any]:
        if name.startswith("_"):
            raise AttributeError(name)
        return self.get_section(name, {})


class ConfigLoader:
    """ConfigLoader provides methods for loading and reading values from a .toml file."""

    __slots__ = {
        "config",
        "values",
        "bot",
        "external",
        "database",
        "second_database",
        "statistics",
        "launcher",
        "game",
        "cities",
        "music",
        "gods",
        "ids",
    }

    def __init__(self, path: str) -> None:
        # the path to the config file of this loader
        self.config = path
        # values initialized as empty dict, in case loading fails
        self.values = {}
        self.reload()

    def reload(self) -> None:
        """Loads the config using the path this loader was initialized with, overriding any previously stored values."""
        with open(self.config, "rb") as f:
            self.values = tomli.load(f)
        self.set_attributes()

    def set_attributes(self) -> None:
        """Sets all config attriutes on the loader."""
        self.bot = BotSection(self.values["bot"])
        self.external = ExternalSection(self.values.get("external", {}))
        self.database = DatabaseSection(self.values.get("database", {}))
        self.second_database = Second_DatabaseSection(self.values.get("second_database", {}))
        self.statistics = StatisticsSection(self.values.get("statistics", {}))
        self.launcher = LauncherSection(self.values.get("launcher", {}))
        self.game = GameSection(self.values.get("game", {}))
        self.cities = self.values.get("cities", [])
        self.music = MusicSection(self.values.get("music", {}))
        self.gods = self.values.get("gods", [])
        self.ids = IdsSection(self.values.get("ids", {}))
