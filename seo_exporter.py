#!/usr/bin/env python3
"""Export SEO data from a remote MySQL database through an SSH tunnel to CSV."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pymysql
from pymysql.cursors import DictCursor
from sshtunnel import SSHTunnelForwarder

LOGGER = logging.getLogger("seo_exporter")
CONFIG_PATH = Path("config.json")
CONFIG_EXAMPLE_PATH = Path("config.example.json")
DEFAULT_OUTPUT = "seo_export.csv"
DEFAULT_PRODUCT_SQL = """
SELECT
    p.ID AS id,
    CONCAT('product/', p.post_name, '/') AS url,
    COALESCE(
        NULLIF(MAX(CASE WHEN pm.meta_key = '_yoast_wpseo_title' THEN pm.meta_value END), ''),
        NULLIF(MAX(CASE WHEN pm.meta_key = 'rank_math_title' THEN pm.meta_value END), ''),
        p.post_title
    ) AS seo_title,
    COALESCE(
        NULLIF(MAX(CASE WHEN pm.meta_key = '_yoast_wpseo_metadesc' THEN pm.meta_value END), ''),
        NULLIF(MAX(CASE WHEN pm.meta_key = 'rank_math_description' THEN pm.meta_value END), ''),
        NULLIF(p.post_excerpt, ''),
        NULLIF(p.post_content, ''),
        NULLIF(p.post_title, ''),
        ''
    ) AS seo_description
FROM wp_posts AS p
LEFT JOIN wp_postmeta AS pm ON pm.post_id = p.ID
WHERE p.post_type = 'product'
  AND p.post_status IN ('publish', 'private')
GROUP BY p.ID, p.post_name, p.post_title, p.post_excerpt, p.post_content
ORDER BY p.ID
""".strip()
DEFAULT_CATEGORY_SQL = """
SELECT
    t.term_id AS id,
    CONCAT('product-category/', t.slug, '/') AS url,
    COALESCE(
        NULLIF(MAX(CASE WHEN tm.meta_key = '_yoast_wpseo_title' THEN tm.meta_value END), ''),
        NULLIF(MAX(CASE WHEN tm.meta_key = 'rank_math_title' THEN tm.meta_value END), ''),
        t.name
    ) AS seo_title,
    COALESCE(
        NULLIF(MAX(CASE WHEN tm.meta_key = '_yoast_wpseo_metadesc' THEN tm.meta_value END), ''),
        NULLIF(MAX(CASE WHEN tm.meta_key = 'rank_math_description' THEN tm.meta_value END), ''),
        NULLIF(tt.description, ''),
        NULLIF(t.name, ''),
        ''
    ) AS seo_description
FROM wp_terms AS t
INNER JOIN wp_term_taxonomy AS tt ON tt.term_id = t.term_id
LEFT JOIN wp_termmeta AS tm ON tm.term_id = t.term_id
WHERE tt.taxonomy = 'product_cat'
GROUP BY t.term_id, t.slug, t.name, tt.description
ORDER BY t.term_id
""".strip()


@dataclass(frozen=True)
class QuerySpec:
    """SQL query specification for one entity type."""

    name: str
    sql: str
    entity_type: str


def setup_logging(verbose: bool) -> None:
    """Configure application logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


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
            "output_csv": "seo_export.csv",
            "include_products": True,
            "include_categories": True,
            "queries": {
                "products": {
                    "entity_type": "product",
                    "sql": DEFAULT_PRODUCT_SQL,
                },
                "categories": {
                    "entity_type": "category",
                    "sql": DEFAULT_CATEGORY_SQL,
                },
            },
        },
    }
    CONFIG_EXAMPLE_PATH.write_text(json.dumps(example, indent=2, ensure_ascii=False), encoding="utf-8")


def load_config() -> Dict[str, Any]:
    """Load configuration from config.json."""
    if not CONFIG_PATH.exists():
        print("❌ Error: config.json not found. Run: python seo_exporter.py --init")
        sys.exit(1)

    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def prompt_bool(label: str, default: bool) -> bool:
    """Prompt for a boolean value."""
    suffix = "Y/n" if default else "y/N"
    value = input(f"{label} [{suffix}]: ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes", "1", "true"}


def prompt_sql(label: str, default_sql: str) -> str:
    """Prompt for SQL and fall back to the WordPress/WooCommerce default."""
    value = input(f"{label} [press Enter for WordPress/WooCommerce default]: ").strip()
    return value or default_sql


def init_config() -> None:
    """Initialize project configuration interactively."""
    ensure_gitignore()
    write_example_config()

    if CONFIG_PATH.exists():
        overwrite = input("Config exists. Overwrite? (y/N): ").strip().lower()
        if overwrite != "y":
            print("ℹ️ Initialization cancelled.")
            return

    print("🚀 Initializing project...")
    ssh_password = getpass("SSH password (leave empty if using private key): ")
    db_password = getpass("MySQL password: ")
    use_products = prompt_bool("Export products", True)
    use_categories = prompt_bool("Export categories", True)

    config: Dict[str, Any] = {
        "ssh": {
            "host": input("SSH host: ").strip(),
            "port": int(input("SSH port [22]: ").strip() or 22),
            "username": input("SSH username: ").strip(),
            "password": ssh_password,
            "pkey_path": input("SSH private key path (optional): ").strip(),
            "pkey_passphrase": getpass("SSH private key passphrase (optional): "),
            "remote_bind_host": input("Remote MySQL host [127.0.0.1]: ").strip() or "127.0.0.1",
            "remote_bind_port": int(input("Remote MySQL port [3306]: ").strip() or 3306),
        },
        "database": {
            "user": input("MySQL user: ").strip(),
            "password": db_password,
            "name": input("Database name: ").strip(),
            "charset": input("MySQL charset [utf8mb4]: ").strip() or "utf8mb4",
        },
        "export": {
            "base_url": input("Website base URL, for example https://example.com: ").strip().rstrip("/"),
            "output_csv": input(f"CSV output file [{DEFAULT_OUTPUT}]: ").strip() or DEFAULT_OUTPUT,
            "include_products": use_products,
            "include_categories": use_categories,
            "queries": {
                "products": {
                    "entity_type": "product",
                    "sql": prompt_sql(
                        "SQL for products (must return id, url, seo_title, seo_description)",
                        DEFAULT_PRODUCT_SQL,
                    ),
                },
                "categories": {
                    "entity_type": "category",
                    "sql": prompt_sql(
                        "SQL for categories (must return id, url, seo_title, seo_description)",
                        DEFAULT_CATEGORY_SQL,
                    ),
                },
            },
        },
    }

    test_connection(config)

    CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    print("✅ Config saved to config.json")
    print("✅ SSH + database connection: OK")
    print("ℹ️ config.json was added to .gitignore")


def validate_row(row: Dict[str, Any], entity_type: str, base_url: str) -> Dict[str, str]:
    """Validate and normalize a DB row for CSV export."""
    required = ["id", "url", "seo_title", "seo_description"]
    missing = [field for field in required if field not in row]
    if missing:
        raise ValueError(f"Query for {entity_type} is missing required columns: {', '.join(missing)}")

    raw_url = "" if row["url"] is None else str(row["url"]).strip()
    if raw_url.startswith(("http://", "https://")):
        browser_url = raw_url
    else:
        browser_url = f"{base_url}/{raw_url.lstrip('/')}" if raw_url else base_url

    return {
        "entity_type": entity_type,
        "id": str(row["id"]),
        "url": browser_url,
        "seo_title": "" if row["seo_title"] is None else str(row["seo_title"]),
        "seo_description": "" if row["seo_description"] is None else str(row["seo_description"]),
    }


def get_tunnel_kwargs(config: Dict[str, Any]) -> Dict[str, Any]:
    """Build keyword arguments for SSHTunnelForwarder."""
    ssh_config = config["ssh"]
    kwargs: Dict[str, Any] = {
        "ssh_username": ssh_config["username"],
        "remote_bind_address": (ssh_config["remote_bind_host"], int(ssh_config["remote_bind_port"])),
    }

    if ssh_config.get("pkey_path"):
        kwargs["ssh_pkey"] = ssh_config["pkey_path"]
        if ssh_config.get("pkey_passphrase"):
            kwargs["ssh_private_key_password"] = ssh_config["pkey_passphrase"]
    elif ssh_config.get("password"):
        kwargs["ssh_password"] = ssh_config["password"]
    else:
        raise ValueError("Either SSH password or SSH private key path must be configured.")

    return kwargs


def build_query_specs(config: Dict[str, Any]) -> List[QuerySpec]:
    """Create enabled query definitions from config."""
    export_cfg = config["export"]
    query_cfg = export_cfg["queries"]
    specs: List[QuerySpec] = []

    if export_cfg.get("include_products", True):
        specs.append(
            QuerySpec(
                name="products",
                sql=query_cfg["products"]["sql"],
                entity_type=query_cfg["products"].get("entity_type", "product"),
            )
        )
    if export_cfg.get("include_categories", True):
        specs.append(
            QuerySpec(
                name="categories",
                sql=query_cfg["categories"]["sql"],
                entity_type=query_cfg["categories"].get("entity_type", "category"),
            )
        )
    return specs


def fetch_rows(config: Dict[str, Any], specs: Iterable[QuerySpec]) -> List[Dict[str, str]]:
    """Fetch SEO data through SSH tunnel and return normalized rows."""
    ssh_cfg = config["ssh"]
    db_cfg = config["database"]
    base_url = config["export"]["base_url"].rstrip("/")
    rows: List[Dict[str, str]] = []

    tunnel_kwargs = get_tunnel_kwargs(config)
    gateway = (ssh_cfg["host"], int(ssh_cfg["port"]))

    with SSHTunnelForwarder(gateway, **tunnel_kwargs) as tunnel:
        connection = pymysql.connect(
            host="127.0.0.1",
            port=tunnel.local_bind_port,
            user=db_cfg["user"],
            password=db_cfg["password"],
            database=db_cfg["name"],
            charset=db_cfg.get("charset", "utf8mb4"),
            cursorclass=DictCursor,
            autocommit=True,
        )
        try:
            with connection.cursor() as cursor:
                for spec in specs:
                    LOGGER.info("Running query: %s", spec.name)
                    cursor.execute(spec.sql)
                    result = cursor.fetchall()
                    LOGGER.info("Fetched %s rows for %s", len(result), spec.name)
                    for row in result:
                        rows.append(validate_row(row, spec.entity_type, base_url))
        finally:
            connection.close()

    return rows


def test_connection(config: Dict[str, Any]) -> None:
    """Test SSH tunnel and DB connectivity."""
    test_spec = QuerySpec(name="healthcheck", sql="SELECT 1 AS id, '' AS url, '' AS seo_title, '' AS seo_description", entity_type="healthcheck")
    fetch_rows(config, [test_spec])


def write_csv(rows: List[Dict[str, str]], output_path: Path) -> None:
    """Write normalized SEO rows to CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["entity_type", "id", "url", "seo_title", "seo_description"],
            delimiter=";",
        )
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Export SEO title and description from a remote MySQL database over SSH to CSV.",
    )
    parser.add_argument("--init", action="store_true", help="Initialize config.json interactively.")
    parser.add_argument("--run", action="store_true", help="Run export using config.json.")
    parser.add_argument("--output", help="Override output CSV file path.")
    parser.add_argument("--products-only", action="store_true", help="Export only product rows.")
    parser.add_argument("--categories-only", action="store_true", help="Export only category rows.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging.")
    return parser.parse_args()


def main() -> int:
    """Application entry point."""
    args = parse_args()
    setup_logging(args.verbose)

    if args.init:
        init_config()
        return 0

    if not args.run:
        print("❌ Error: choose an action. Use --init or --run.")
        return 2

    try:
        config = load_config()
        specs = build_query_specs(config)

        if args.products_only:
            specs = [spec for spec in specs if spec.name == "products"]
        if args.categories_only:
            specs = [spec for spec in specs if spec.name == "categories"]

        if not specs:
            raise ValueError("No queries selected. Check config flags or CLI options.")

        rows = fetch_rows(config, specs)
        output = Path(args.output or config["export"].get("output_csv", DEFAULT_OUTPUT))
        write_csv(rows, output)
        print(f"✅ Export completed: {len(rows)} rows saved to {output}")
        return 0
    except Exception as exc:  # pylint: disable=broad-except
        LOGGER.exception("Export failed")
        print(f"❌ Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
