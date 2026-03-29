import copy

import pytest

import seo_exporter as se


@pytest.fixture
def valid_config():
    config = {
        "ssh": {
            "host": "example.com",
            "port": 22,
            "username": "deploy",
            "password": "secret",
            "pkey_path": "",
            "pkey_passphrase": "",
            "remote_bind_host": "127.0.0.1",
            "remote_bind_port": 3306,
        },
        "database": {
            "user": "db_user",
            "password": "db_pass",
            "name": "db_name",
            "charset": "utf8mb4",
        },
        "export": {
            "base_url": "https://example.com",
            "output_csv": "seo_export.csv",
            "table_prefix": "wp_",
            "include_products": True,
            "include_categories": True,
            "queries": {
                "products": {
                    "entity_type": "product",
                    "sql": "SELECT * FROM {table_prefix}posts",
                },
                "categories": {
                    "entity_type": "category",
                    "sql": "SELECT * FROM {table_prefix}terms",
                },
            },
        },
    }
    return se.validate_config(copy.deepcopy(config))


def test_validate_row_preserves_absolute_url_and_normalizes_none_values():
    row = {
        "id": 101,
        "url": "https://shop.example.com/product/test/",
        "seo_title": None,
        "seo_description": None,
    }

    result = se.validate_row(row, "product", "https://example.com")

    assert result == {
        "entity_type": "product",
        "id": "101",
        "url": "https://shop.example.com/product/test/",
        "seo_title": "",
        "seo_description": "",
    }


def test_validate_row_builds_absolute_url_from_relative_path():
    row = {
        "id": 7,
        "url": "product/test-item/",
        "seo_title": "Title",
        "seo_description": "Description",
    }

    result = se.validate_row(row, "product", "https://example.com")

    assert result["url"] == "https://example.com/product/test-item/"


def test_validate_row_uses_base_url_for_empty_path():
    row = {
        "id": 9,
        "url": "",
        "seo_title": "Title",
        "seo_description": "Description",
    }

    result = se.validate_row(row, "category", "https://example.com")

    assert result["url"] == "https://example.com"


def test_validate_row_raises_for_missing_required_columns():
    with pytest.raises(ValueError, match="missing required columns: seo_description"):
        se.validate_row({"id": 1, "url": "x", "seo_title": "y"}, "product", "https://example.com")


def test_build_query_specs_returns_both_default_queries(valid_config):
    specs = se.build_query_specs(valid_config)

    assert [spec.name for spec in specs] == ["products", "categories"]
    assert specs[0].sql == "SELECT * FROM wp_posts"
    assert specs[1].sql == "SELECT * FROM wp_terms"


@pytest.mark.parametrize(
    ("include_products", "include_categories", "expected_names"),
    [
        (True, False, ["products"]),
        (False, True, ["categories"]),
    ],
)
def test_build_query_specs_respects_enabled_flags(valid_config, include_products, include_categories, expected_names):
    valid_config["export"]["include_products"] = include_products
    valid_config["export"]["include_categories"] = include_categories

    specs = se.build_query_specs(valid_config)

    assert [spec.name for spec in specs] == expected_names


def test_build_query_specs_uses_custom_entity_type(valid_config):
    valid_config["export"]["queries"]["products"]["entity_type"] = "woo_product"

    specs = se.build_query_specs(valid_config)

    assert specs[0].entity_type == "woo_product"


def test_write_csv_writes_expected_header_and_rows(tmp_path):
    output_path = tmp_path / "nested" / "result.csv"
    rows = [
        {
            "entity_type": "product",
            "id": "15",
            "url": "https://example.com/product/test/",
            "seo_title": "Product title",
            "seo_description": "Product description",
        }
    ]

    se.write_csv(rows, output_path)

    content = output_path.read_text(encoding="utf-8-sig").splitlines()
    assert content[0] == "entity_type;id;url;seo_title;seo_description"
    assert content[1] == "product;15;https://example.com/product/test/;Product title;Product description"


def test_write_csv_writes_header_only_when_rows_are_empty(tmp_path):
    output_path = tmp_path / "empty.csv"

    se.write_csv([], output_path)

    content = output_path.read_text(encoding="utf-8-sig").splitlines()
    assert content == ["entity_type;id;url;seo_title;seo_description"]
