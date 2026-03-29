"""Configuration helpers for SEO exporter."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict

from exporter import DEFAULT_CATEGORY_SQL_TEMPLATE, DEFAULT_PRODUCT_SQL_TEMPLATE

CONFIG_PATH = Path("config.json")
CONFIG_EXAMPLE_PATH = Path("config.example.json")
DEFAULT_OUTPUT = "seo_export.csv"
DEFAULT_TABLE_PREFIX = "wp_"


def ensure_gitignore() -> None:
    """Ensure sensitive and temporary files are ignored by Git."""
    gitignore_path = Path(".gitignore")
    required_lines = ["config.json", "*.csv", "*.log", "__pycache__/"]

    existing = set()
    if gitignore_path.exists():
        existing = {line.strip() for line in gitignore_path.read_text(encoding="utf-8").splitlines()}

    missing = [line for line in required_lines if line not in existing]
    if not missing:
        return

    with gitignore_path.open("a", encoding="utf-8") as handle:
        if gitignore_path.stat().st_size > 0:
            handle.write("\n")
        for line in missing:
            handle.write(f"{line}\n")


def validate_table_prefix(table_prefix: str) -> str:
    """Validate a WordPress table prefix."""
    value = table_prefix.strip()
    if not value:
        raise ValueError("export.table_prefix must not be empty.")
    if not re.fullmatch(r"[A-Za-z0-9_]+", value):
        raise ValueError("export.table_prefix may contain only letters, digits, and underscores.")
    return value


def validate_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate config structure and apply backward-compatible defaults."""
    if not isinstance(config, dict):
        raise ValueError("Config root must be a JSON object.")

    for section_name in ("ssh", "database", "export"):
        section = config.get(section_name)
        if not isinstance(section, dict):
            raise ValueError(f"Config section '{section_name}' must be an object.")

    ssh_cfg = config["ssh"]
    db_cfg = config["database"]
    export_cfg = config["export"]

    for key in ("host", "username", "remote_bind_host"):
        value = ssh_cfg.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Missing required config key: ssh.{key}")
        ssh_cfg[key] = value.strip()

    for key in ("port", "remote_bind_port"):
        if key not in ssh_cfg:
            raise ValueError(f"Missing required config key: ssh.{key}")

    for key in ("user", "password", "name"):
        value = db_cfg.get(key)
        if not isinstance(value, str):
            raise ValueError(f"Missing required config key: database.{key}")
        db_cfg[key] = value

    base_url = export_cfg.get("base_url")
    if not isinstance(base_url, str) or not base_url.strip():
        raise ValueError("Missing required config key: export.base_url")
    export_cfg["base_url"] = base_url.strip().rstrip("/")

    table_prefix = validate_table_prefix(str(export_cfg.get("table_prefix", DEFAULT_TABLE_PREFIX)))
    export_cfg["table_prefix"] = table_prefix
    export_cfg["output_csv"] = str(export_cfg.get("output_csv") or DEFAULT_OUTPUT)
    export_cfg["include_products"] = bool(export_cfg.get("include_products", True))
    export_cfg["include_categories"] = bool(export_cfg.get("include_categories", True))

    queries = export_cfg.get("queries")
    if queries is None:
        queries = {}
        export_cfg["queries"] = queries
    if not isinstance(queries, dict):
        raise ValueError("Config section 'export.queries' must be an object.")

    default_queries = {
        "products": {
            "entity_type": "product",
            "sql": DEFAULT_PRODUCT_SQL_TEMPLATE,
        },
        "categories": {
            "entity_type": "category",
            "sql": DEFAULT_CATEGORY_SQL_TEMPLATE,
        },
    }

    for query_name, defaults in default_queries.items():
        query_cfg = queries.get(query_name)
        if query_cfg is None:
            query_cfg = {}
            queries[query_name] = query_cfg
        if not isinstance(query_cfg, dict):
            raise ValueError(f"Config section 'export.queries.{query_name}' must be an object.")

        entity_type = query_cfg.get("entity_type") or defaults["entity_type"]
        sql = query_cfg.get("sql") or defaults["sql"]
        if not isinstance(entity_type, str) or not entity_type.strip():
            raise ValueError(f"Config key 'export.queries.{query_name}.entity_type' must be a non-empty string.")
        if not isinstance(sql, str) or not sql.strip():
            raise ValueError(f"Config key 'export.queries.{query_name}.sql' must be a non-empty string.")

        query_cfg["entity_type"] = entity_type.strip()
        query_cfg["sql"] = sql

    return config


def write_example_config() -> None:
    """Write config.example.json if it does not exist."""
    if CONFIG_EXAMPLE_PATH.exists():
        return

    example = {
        "ssh": {
            "host": "example.com",
            "port": 22,
            "username": "deploy",
            "password": "",
            "pkey_path": "",
            "pkey_passphrase": "",
            "remote_bind_host": "127.0.0.1",
            "remote_bind_port": 3306,
        },
        "database": {
            "user": "db_user",
            "password": "",
            "name": "db_name",
            "charset": "utf8mb4",
        },
        "export": {
            "base_url": "https://example.com",
            "output_csv": DEFAULT_OUTPUT,
            "table_prefix": DEFAULT_TABLE_PREFIX,
            "include_products": True,
            "include_categories": True,
            "queries": {
                "products": {
                    "entity_type": "product",
                    "sql": DEFAULT_PRODUCT_SQL_TEMPLATE,
                },
                "categories": {
                    "entity_type": "category",
                    "sql": DEFAULT_CATEGORY_SQL_TEMPLATE,
                },
            },
        },
    }
    CONFIG_EXAMPLE_PATH.write_text(json.dumps(example, indent=2, ensure_ascii=False), encoding="utf-8")


def load_config() -> Dict[str, Any]:
    """Load configuration from config.json."""
    if not CONFIG_PATH.exists():
        print("❌ Error: config.json not found in the current directory. Run: python seo_exporter.py --init")
        sys.exit(1)

    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)
