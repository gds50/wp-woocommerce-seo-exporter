"""Export query, row normalization, and CSV helpers."""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

LOGGER = logging.getLogger("seo_exporter")
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


def render_sql_template(sql: str, table_prefix: str) -> str:
    """Replace the table prefix token in SQL."""
    return sql.replace(TABLE_PREFIX_TOKEN, table_prefix)


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


def apply_query_filters(specs: List[QuerySpec], products_only: bool, categories_only: bool) -> List[QuerySpec]:
    """Apply CLI query filters without changing query definitions."""
    filtered_specs = list(specs)
    if products_only:
        filtered_specs = [spec for spec in filtered_specs if spec.name == "products"]
    if categories_only:
        filtered_specs = [spec for spec in filtered_specs if spec.name == "categories"]
    return filtered_specs
