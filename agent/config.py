import os
from functools import lru_cache

import yaml


CONFIG_PATH = os.environ.get("TENANT_CONFIG_PATH", "config/tenant.yaml")


@lru_cache(maxsize=1)
def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def tenant() -> dict:
    return load_config().get("tenant", {})


def feature_enabled(feature: str) -> bool:
    return bool(tenant().get("features", {}).get(feature, False))


def reload_config() -> None:
    load_config.cache_clear()
