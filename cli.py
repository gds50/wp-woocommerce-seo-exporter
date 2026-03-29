"""CLI entrypoints for SEO exporter."""

from __future__ import annotations

import argparse
import json
import logging
from getpass import getpass
from pathlib import Path
from typing import Any, Dict, List

from config import CONFIG_PATH, DEFAULT_OUTPUT, DEFAULT_TABLE_PREFIX, ensure_gitignore, load_config, validate_config, validate_table_prefix, write_example_config
from db import diagnose_seo_sources, dry_run_queries, fetch_rows, test_connection
from exporter import DEFAULT_CATEGORY_SQL_TEMPLATE, DEFAULT_PRODUCT_SQL_TEMPLATE, TABLE_PREFIX_TOKEN, QuerySpec, apply_query_filters, build_query_specs, write_csv

LOGGER = logging.getLogger("seo_exporter")


def setup_logging(verbose: bool) -> None:
    """Configure application logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


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
