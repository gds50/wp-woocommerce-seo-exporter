import copy

import pytest

import config as config_module
import db as db_module
import exporter as exporter_module


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
    return config_module.validate_config(copy.deepcopy(config))


def test_validate_row_preserves_absolute_url_and_normalizes_none_values():
    row = {
        "id": 101,
        "url": "https://shop.example.com/product/test/",
        "seo_title": None,
        "seo_description": None,
    }

    result = exporter_module.validate_row(row, "product", "https://example.com")

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

    result = exporter_module.validate_row(row, "product", "https://example.com")

    assert result["url"] == "https://example.com/product/test-item/"


def test_validate_row_uses_base_url_for_empty_path():
    row = {
        "id": 9,
        "url": "",
        "seo_title": "Title",
        "seo_description": "Description",
    }

    result = exporter_module.validate_row(row, "category", "https://example.com")

    assert result["url"] == "https://example.com"


def test_validate_row_raises_for_missing_required_columns():
    with pytest.raises(ValueError, match="missing required columns: seo_description"):
        exporter_module.validate_row({"id": 1, "url": "x", "seo_title": "y"}, "product", "https://example.com")


def test_build_query_specs_returns_both_default_queries(valid_config):
    specs = exporter_module.build_query_specs(valid_config)

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

    specs = exporter_module.build_query_specs(valid_config)

    assert [spec.name for spec in specs] == expected_names


def test_build_query_specs_uses_custom_entity_type(valid_config):
    valid_config["export"]["queries"]["products"]["entity_type"] = "woo_product"

    specs = exporter_module.build_query_specs(valid_config)

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

    exporter_module.write_csv(rows, output_path)

    content = output_path.read_text(encoding="utf-8-sig").splitlines()
    assert content[0] == "entity_type;id;url;seo_title;seo_description"
    assert content[1] == "product;15;https://example.com/product/test/;Product title;Product description"


def test_write_csv_writes_header_only_when_rows_are_empty(tmp_path):
    output_path = tmp_path / "empty.csv"

    exporter_module.write_csv([], output_path)

    content = output_path.read_text(encoding="utf-8-sig").splitlines()
    assert content == ["entity_type;id;url;seo_title;seo_description"]


def test_apply_query_filters_respects_products_only_and_categories_only(valid_config):
    specs = exporter_module.build_query_specs(valid_config)

    products_only = exporter_module.apply_query_filters(specs, products_only=True, categories_only=False)
    categories_only = exporter_module.apply_query_filters(specs, products_only=False, categories_only=True)

    assert [spec.name for spec in products_only] == ["products"]
    assert [spec.name for spec in categories_only] == ["categories"]


def test_dry_run_queries_returns_counts_per_query(valid_config, monkeypatch):
    specs = [
        exporter_module.QuerySpec(name="products", sql="SELECT products", entity_type="product"),
        exporter_module.QuerySpec(name="categories", sql="SELECT categories", entity_type="category"),
    ]

    class FakeTunnel:
        local_bind_port = 3307

        def __init__(self, gateway, **kwargs):
            self.gateway = gateway
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeCursor:
        def __init__(self):
            self.sql = ""

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql):
            self.sql = sql

        def fetchall(self):
            if "products" in self.sql:
                return [
                    {"id": 1, "url": "product/item-1/", "seo_title": "Title 1", "seo_description": "Desc 1"},
                    {"id": 2, "url": "product/item-2/", "seo_title": "Title 2", "seo_description": "Desc 2"},
                ]
            return [{"id": 11, "url": "product-category/cat-1/", "seo_title": "Cat", "seo_description": "Cat desc"}]

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

        def close(self):
            return None

    monkeypatch.setattr(db_module, "SSHTunnelForwarder", FakeTunnel)
    monkeypatch.setattr(db_module.pymysql, "connect", lambda **kwargs: FakeConnection())

    counts = db_module.dry_run_queries(valid_config, specs)

    assert counts == {"products": 2, "categories": 1}
