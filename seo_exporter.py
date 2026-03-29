#!/usr/bin/env python3
"""Export SEO data from a remote MySQL database through an SSH tunnel to CSV."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pymysql
from pymysql.cursors import DictCursor
from sshtunnel import BaseSSHTunnelForwarderError, SSHTunnelForwarder

LOGGER = logging.getLogger("seo_exporter")
CONFIG_PATH = Path("config.json")
CONFIG_EXAMPLE_PATH = Path("config.example.json")
DEFAULT_OUTPUT = "seo_export.csv"
DEFAULT_TABLE_PREFIX = "wp_"
TABLE_PREFIX_TOKEN = "{table_prefix}"
DEFAULT_PRODUCT_SQL_TEMPLATE = """
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
FROM {table_prefix}posts AS p
LEFT JOIN {table_prefix}postmeta AS pm ON pm.post_id = p.ID
WHERE p.post_type = 'product'
  AND p.post_status IN ('publish', 'private')
GROUP BY p.ID, p.post_name, p.post_title, p.post_excerpt, p.post_content
ORDER BY p.ID
""".strip()
DEFAULT_CATEGORY_SQL_TEMPLATE = """
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
FROM {table_prefix}terms AS t
INNER JOIN {table_prefix}term_taxonomy AS tt ON tt.term_id = t.term_id
LEFT JOIN {table_prefix}termmeta AS tm ON tm.term_id = t.term_id
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


def render_sql_template(sql: str, table_prefix: str) -> str:
    """Replace the table prefix token in SQL."""
    return sql.replace(TABLE_PREFIX_TOKEN, table_prefix)


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
            "output_csv": "seo_export.csv",
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
    value = input(f"{label} [press Enter for default SQL with {TABLE_PREFIX_TOKEN}]: ").strip()
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
    table_prefix = validate_table_prefix(input(f"WordPress table prefix [{DEFAULT_TABLE_PREFIX}]: ").strip() or DEFAULT_TABLE_PREFIX)
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
            "table_prefix": table_prefix,
            "include_products": use_products,
            "include_categories": use_categories,
            "queries": {
                "products": {
                    "entity_type": "product",
                    "sql": prompt_sql(
                        "SQL for products (must return id, url, seo_title, seo_description)",
                        DEFAULT_PRODUCT_SQL_TEMPLATE,
                    ),
                },
                "categories": {
                    "entity_type": "category",
                    "sql": prompt_sql(
                        "SQL for categories (must return id, url, seo_title, seo_description)",
                        DEFAULT_CATEGORY_SQL_TEMPLATE,
                    ),
                },
            },
        },
    }

    validate_config(config)
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
    table_prefix = export_cfg["table_prefix"]
    specs: List[QuerySpec] = []

    if export_cfg.get("include_products", True):
        specs.append(
            QuerySpec(
                name="products",
                sql=render_sql_template(query_cfg["products"]["sql"], table_prefix),
                entity_type=query_cfg["products"].get("entity_type", "product"),
            )
        )
    if export_cfg.get("include_categories", True):
        specs.append(
            QuerySpec(
                name="categories",
                sql=render_sql_template(query_cfg["categories"]["sql"], table_prefix),
                entity_type=query_cfg["categories"].get("entity_type", "category"),
            )
        )
    return specs


def fetch_rows(config: Dict[str, Any], specs: Iterable[QuerySpec]) -> List[Dict[str, str]]:
    """Fetch SEO data through SSH tunnel and return normalized rows."""
    ssh_cfg = config["ssh"]
    db_cfg = config["database"]
    base_url = config["export"]["base_url"].rstrip("/")
    spec_list = list(specs)
    rows: List[Dict[str, str]] = []

    tunnel_kwargs = get_tunnel_kwargs(config)
    gateway = (ssh_cfg["host"], int(ssh_cfg["port"]))

    try:
        LOGGER.info("Opening SSH tunnel for %s query(s).", len(spec_list))
        with SSHTunnelForwarder(gateway, **tunnel_kwargs) as tunnel:
            try:
                LOGGER.info("Connecting to database through SSH tunnel.")
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
            except pymysql.MySQLError as exc:
                raise RuntimeError("Database connection failed. Check MySQL credentials, database name, and tunnel settings.") from exc

            try:
                with connection.cursor() as cursor:
                    for spec in spec_list:
                        LOGGER.info("Running query: %s", spec.name)
                        try:
                            cursor.execute(spec.sql)
                            result = cursor.fetchall()
                        except pymysql.MySQLError as exc:
                            raise RuntimeError(f"SQL query failed for '{spec.name}'. Check the configured SQL and database structure.") from exc

                        if not result:
                            LOGGER.warning("Query '%s' returned 0 rows.", spec.name)
                            continue

                        LOGGER.info("Fetched %s row(s) for %s", len(result), spec.name)
                        for row in result:
                            rows.append(validate_row(row, spec.entity_type, base_url))
            finally:
                connection.close()
                LOGGER.info("Database connection closed.")
    except BaseSSHTunnelForwarderError as exc:
        raise RuntimeError("SSH tunnel connection failed. Check SSH host, port, credentials, and remote MySQL bind settings.") from exc
    except OSError as exc:
        raise RuntimeError("SSH connection failed due to a network or socket error.") from exc

    return rows


def test_connection(config: Dict[str, Any]) -> None:
    """Test SSH tunnel and DB connectivity."""
    test_spec = QuerySpec(name="healthcheck", sql="SELECT 1 AS id, '' AS url, '' AS seo_title, '' AS seo_description", entity_type="healthcheck")
    fetch_rows(config, [test_spec])


def dry_run_queries(config: Dict[str, Any], specs: Iterable[QuerySpec]) -> Dict[str, int]:
    """Execute export queries without writing CSV and return row counts per query."""
    ssh_cfg = config["ssh"]
    db_cfg = config["database"]
    base_url = config["export"]["base_url"].rstrip("/")
    spec_list = list(specs)
    query_counts: Dict[str, int] = {}

    tunnel_kwargs = get_tunnel_kwargs(config)
    gateway = (ssh_cfg["host"], int(ssh_cfg["port"]))

    try:
        LOGGER.info("Opening SSH tunnel for dry run with %s query(s).", len(spec_list))
        with SSHTunnelForwarder(gateway, **tunnel_kwargs) as tunnel:
            try:
                LOGGER.info("Connecting to database through SSH tunnel.")
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
            except pymysql.MySQLError as exc:
                raise RuntimeError("Database connection failed. Check MySQL credentials, database name, and tunnel settings.") from exc

            try:
                with connection.cursor() as cursor:
                    for spec in spec_list:
                        LOGGER.info("Running dry-run query: %s", spec.name)
                        try:
                            cursor.execute(spec.sql)
                            result = cursor.fetchall()
                        except pymysql.MySQLError as exc:
                            raise RuntimeError(f"SQL query failed for '{spec.name}'. Check the configured SQL and database structure.") from exc

                        query_counts[spec.name] = len(result)
                        if not result:
                            LOGGER.warning("Dry-run query '%s' returned 0 rows.", spec.name)
                            continue

                        for row in result:
                            validate_row(row, spec.entity_type, base_url)
            finally:
                connection.close()
                LOGGER.info("Database connection closed.")
    except BaseSSHTunnelForwarderError as exc:
        raise RuntimeError("SSH tunnel connection failed. Check SSH host, port, credentials, and remote MySQL bind settings.") from exc
    except OSError as exc:
        raise RuntimeError("SSH connection failed due to a network or socket error.") from exc

    return query_counts


def diagnose_seo_sources(config: Dict[str, Any]) -> None:
    """Inspect common WooCommerce SEO meta storages without exporting CSV."""
    ssh_cfg = config["ssh"]
    db_cfg = config["database"]
    table_prefix = config["export"]["table_prefix"]

    diagnostic_queries = [
        (
            "published_products",
            "Published/private products",
            f"""
SELECT COUNT(*) AS matches
FROM {table_prefix}posts
WHERE post_type = 'product'
  AND post_status IN ('publish', 'private')
""".strip(),
        ),
        (
            "product_categories",
            "Product categories",
            f"""
SELECT COUNT(*) AS matches
FROM {table_prefix}term_taxonomy
WHERE taxonomy = 'product_cat'
""".strip(),
        ),
        (
            "yoast_product_meta",
            "Yoast SEO product meta",
            f"""
SELECT COUNT(DISTINCT pm.post_id) AS matches
FROM {table_prefix}postmeta AS pm
INNER JOIN {table_prefix}posts AS p ON p.ID = pm.post_id
WHERE p.post_type = 'product'
  AND p.post_status IN ('publish', 'private')
  AND pm.meta_key IN ('_yoast_wpseo_title', '_yoast_wpseo_metadesc')
""".strip(),
        ),
        (
            "rank_math_product_meta",
            "Rank Math product meta",
            f"""
SELECT COUNT(DISTINCT pm.post_id) AS matches
FROM {table_prefix}postmeta AS pm
INNER JOIN {table_prefix}posts AS p ON p.ID = pm.post_id
WHERE p.post_type = 'product'
  AND p.post_status IN ('publish', 'private')
  AND pm.meta_key IN ('rank_math_title', 'rank_math_description')
""".strip(),
        ),
        (
            "yoast_category_meta",
            "Yoast SEO category meta",
            f"""
SELECT COUNT(DISTINCT tm.term_id) AS matches
FROM {table_prefix}termmeta AS tm
INNER JOIN {table_prefix}term_taxonomy AS tt ON tt.term_id = tm.term_id
WHERE tt.taxonomy = 'product_cat'
  AND tm.meta_key IN ('_yoast_wpseo_title', '_yoast_wpseo_metadesc')
""".strip(),
        ),
        (
            "rank_math_category_meta",
            "Rank Math category meta",
            f"""
SELECT COUNT(DISTINCT tm.term_id) AS matches
FROM {table_prefix}termmeta AS tm
INNER JOIN {table_prefix}term_taxonomy AS tt ON tt.term_id = tm.term_id
WHERE tt.taxonomy = 'product_cat'
  AND tm.meta_key IN ('rank_math_title', 'rank_math_description')
""".strip(),
        ),
    ]

    results: Dict[str, int] = {}
    tunnel_kwargs = get_tunnel_kwargs(config)
    gateway = (ssh_cfg["host"], int(ssh_cfg["port"]))

    try:
        LOGGER.info("Starting SEO diagnostics with table_prefix=%s", table_prefix)
        with SSHTunnelForwarder(gateway, **tunnel_kwargs) as tunnel:
            try:
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
            except pymysql.MySQLError as exc:
                raise RuntimeError("Database connection failed. Check MySQL credentials, database name, and tunnel settings.") from exc

            try:
                with connection.cursor() as cursor:
                    for query_name, query_label, sql in diagnostic_queries:
                        LOGGER.info("Running diagnostic query: %s", query_label)
                        try:
                            cursor.execute(sql)
                            result = cursor.fetchone() or {}
                        except pymysql.MySQLError as exc:
                            raise RuntimeError(
                                "SEO diagnostics failed. Check export.table_prefix and whether the WordPress/WooCommerce tables exist."
                            ) from exc
                        results[query_name] = int(result.get("matches") or 0)
            finally:
                connection.close()
                LOGGER.info("Database connection closed.")
    except BaseSSHTunnelForwarderError as exc:
        raise RuntimeError("SSH tunnel connection failed. Check SSH host, port, credentials, and remote MySQL bind settings.") from exc
    except OSError as exc:
        raise RuntimeError("SSH connection failed due to a network or socket error.") from exc

    print("SEO diagnostics")
    print(f"- table_prefix: {table_prefix}")
    print("- built-in export priority: Yoast SEO -> Rank Math -> WordPress/WooCommerce fallback")
    print(f"- published/private products: {results['published_products']}")
    print(f"- product categories: {results['product_categories']}")
    print(f"- Yoast SEO product meta detected on {results['yoast_product_meta']} product(s)")
    print(f"- Rank Math product meta detected on {results['rank_math_product_meta']} product(s)")
    print(f"- Yoast SEO category meta detected on {results['yoast_category_meta']} category record(s)")
    print(f"- Rank Math category meta detected on {results['rank_math_category_meta']} category record(s)")
    print("- AIOSEO is not auto-detected by the built-in export yet; use custom SQL in config.json if your site stores SEO there.")


def write_csv(rows: List[Dict[str, str]], output_path: Path) -> None:
    """Write normalized SEO rows to CSV."""
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        LOGGER.info("Writing %s row(s) to CSV: %s", len(rows), output_path)
        with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["entity_type", "id", "url", "seo_title", "seo_description"],
                delimiter=";",
            )
            writer.writeheader()
            writer.writerows(rows)
        LOGGER.info("CSV file written successfully: %s", output_path)
    except (OSError, csv.Error) as exc:
        raise RuntimeError(f"Failed to write CSV file: {output_path}") from exc


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Export SEO title and description from a remote MySQL database over SSH to CSV.",
    )
    parser.add_argument("--init", action="store_true", help="Initialize config.json interactively.")
    parser.add_argument("--run", action="store_true", help="Run export using config.json.")
    parser.add_argument("--dry-run", action="store_true", help="Run export queries and count rows without writing CSV.")
    parser.add_argument("--check-connection", action="store_true", help="Check config, SSH tunnel, and MySQL connectivity without running export SQL.")
    parser.add_argument("--diagnose-seo", action="store_true", help="Detect which built-in SEO sources are present in the database.")
    parser.add_argument("--output", help="Override output CSV file path.")
    parser.add_argument("--products-only", action="store_true", help="Export only product rows.")
    parser.add_argument("--categories-only", action="store_true", help="Export only category rows.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging.")
    return parser.parse_args()


def apply_query_filters(specs: List[QuerySpec], products_only: bool, categories_only: bool) -> List[QuerySpec]:
    """Apply CLI query filters without changing query definitions."""
    filtered_specs = list(specs)
    if products_only:
        filtered_specs = [spec for spec in filtered_specs if spec.name == "products"]
    if categories_only:
        filtered_specs = [spec for spec in filtered_specs if spec.name == "categories"]
    return filtered_specs


def main() -> int:
    """Application entry point."""
    args = parse_args()
    setup_logging(args.verbose)

    if args.init:
        init_config()
        return 0

    selected_actions = []
    if args.run:
        selected_actions.append("--run")
    if args.dry_run:
        selected_actions.append("--dry-run")
    if args.check_connection:
        selected_actions.append("--check-connection")
    if args.diagnose_seo:
        selected_actions.append("--diagnose-seo")

    if len(selected_actions) > 1:
        print(f"❌ Error: choose one action. Conflicting options: {', '.join(selected_actions)}")
        return 2

    if args.check_connection:
        try:
            config = validate_config(load_config())
            LOGGER.info("Starting connection check.")
            test_connection(config)
            print("✅ Connection check passed: SSH tunnel and MySQL access are working.")
            return 0
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.exception("Connection check failed: %s", exc)
            print(f"❌ Error: {exc}")
            return 1

    if args.diagnose_seo:
        try:
            config = validate_config(load_config())
            diagnose_seo_sources(config)
            return 0
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.exception("SEO diagnostics failed: %s", exc)
            print(f"❌ Error: {exc}")
            return 1

    if args.dry_run:
        try:
            config = validate_config(load_config())
            specs = apply_query_filters(build_query_specs(config), args.products_only, args.categories_only)

            if not specs:
                raise ValueError("No queries selected. Check config flags or CLI options.")

            LOGGER.info(
                "Starting dry run | queries=%s | table_prefix=%s",
                ",".join(spec.name for spec in specs),
                config["export"]["table_prefix"],
            )
            query_counts = dry_run_queries(config, specs)
            total_rows = sum(query_counts.values())
            print("✅ Dry run completed. No CSV file was written.")
            print(f"- Queries checked: {', '.join(spec.name for spec in specs)}")
            for spec in specs:
                print(f"- {spec.name}: {query_counts.get(spec.name, 0)} row(s)")
            print(f"- Total rows: {total_rows}")
            if total_rows == 0:
                print("- Warning: all selected queries returned 0 rows.")
            return 0
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.exception("Dry run failed: %s", exc)
            print(f"❌ Error: {exc}")
            return 1

    if not args.run:
        print("❌ Error: choose an action. Use --init, --run, --dry-run, --check-connection, or --diagnose-seo.")
        return 2

    try:
        config = validate_config(load_config())
        specs = apply_query_filters(build_query_specs(config), args.products_only, args.categories_only)

        if not specs:
            raise ValueError("No queries selected. Check config flags or CLI options.")

        output = Path(args.output or config["export"].get("output_csv", DEFAULT_OUTPUT))
        LOGGER.info(
            "Starting export | queries=%s | table_prefix=%s | output=%s",
            ",".join(spec.name for spec in specs),
            config["export"]["table_prefix"],
            output,
        )

        rows = fetch_rows(config, specs)
        if not rows:
            LOGGER.warning("No rows were returned by the selected queries. Writing header-only CSV.")
        write_csv(rows, output)
        LOGGER.info("Export finished successfully. Total row(s) processed: %s", len(rows))
        print(f"✅ Export completed: {len(rows)} rows saved to {output}")
        return 0
    except Exception as exc:  # pylint: disable=broad-except
        LOGGER.exception("Export failed: %s", exc)
        print(f"❌ Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
