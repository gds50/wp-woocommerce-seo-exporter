"""SSH tunnel and database operations for SEO exporter."""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List

import pymysql
from pymysql.cursors import DictCursor
from sshtunnel import BaseSSHTunnelForwarderError, SSHTunnelForwarder

from exporter import QuerySpec, validate_row

LOGGER = logging.getLogger("seo_exporter")


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
                raise RuntimeError(
                    "Database connection failed. Check MySQL credentials, database name, charset, and SSH tunnel settings."
                ) from exc

            try:
                with connection.cursor() as cursor:
                    for spec in spec_list:
                        LOGGER.info("Running query: %s", spec.name)
                        try:
                            cursor.execute(spec.sql)
                            result = cursor.fetchall()
                        except pymysql.MySQLError as exc:
                            raise RuntimeError(
                                f"SQL query failed for '{spec.name}'. Check the configured SQL, table_prefix, and database structure."
                            ) from exc

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
        raise RuntimeError(
            "SSH tunnel connection failed. Check SSH host, port, credentials, and remote MySQL bind settings."
        ) from exc
    except OSError as exc:
        raise RuntimeError("SSH connection failed due to a network or socket error. Verify host reachability and SSH access.") from exc

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
                raise RuntimeError(
                    "Database connection failed. Check MySQL credentials, database name, charset, and SSH tunnel settings."
                ) from exc

            try:
                with connection.cursor() as cursor:
                    for spec in spec_list:
                        LOGGER.info("Running dry-run query: %s", spec.name)
                        try:
                            cursor.execute(spec.sql)
                            result = cursor.fetchall()
                        except pymysql.MySQLError as exc:
                            raise RuntimeError(
                                f"SQL query failed for '{spec.name}'. Check the configured SQL, table_prefix, and database structure."
                            ) from exc

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
        raise RuntimeError(
            "SSH tunnel connection failed. Check SSH host, port, credentials, and remote MySQL bind settings."
        ) from exc
    except OSError as exc:
        raise RuntimeError("SSH connection failed due to a network or socket error. Verify host reachability and SSH access.") from exc

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
                raise RuntimeError(
                    "Database connection failed. Check MySQL credentials, database name, charset, and SSH tunnel settings."
                ) from exc

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
        raise RuntimeError(
            "SSH tunnel connection failed. Check SSH host, port, credentials, and remote MySQL bind settings."
        ) from exc
    except OSError as exc:
        raise RuntimeError("SSH connection failed due to a network or socket error. Verify host reachability and SSH access.") from exc

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
