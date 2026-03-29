import argparse
import copy
from pathlib import Path

import cli as cli_module
import config as config_module


def make_args(**overrides):
    values = {
        "init": False,
        "run": False,
        "dry_run": False,
        "check_connection": False,
        "diagnose_seo": False,
        "output": None,
        "products_only": False,
        "categories_only": False,
        "verbose": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def make_config(output_path: Path):
    return {
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
            "output_csv": str(output_path),
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


def prepare_cli(monkeypatch, tmp_path, **arg_overrides):
    output_path = tmp_path / "seo_export.csv"
    config = config_module.validate_config(copy.deepcopy(make_config(output_path)))

    monkeypatch.setattr(cli_module, "parse_args", lambda: make_args(**arg_overrides))
    monkeypatch.setattr(cli_module, "setup_logging", lambda verbose: None)
    monkeypatch.setattr(cli_module, "load_config", lambda: copy.deepcopy(config))

    return config, output_path


def test_main_run_writes_csv_with_real_writer(monkeypatch, tmp_path, capsys):
    _, output_path = prepare_cli(monkeypatch, tmp_path, run=True)
    observed = {}

    def fake_fetch_rows(cfg, specs):
        observed["spec_names"] = [spec.name for spec in specs]
        return [
            {
                "entity_type": "product",
                "id": "101",
                "url": "https://example.com/product/item-101/",
                "seo_title": "Product 101",
                "seo_description": "Description 101",
            },
            {
                "entity_type": "category",
                "id": "5",
                "url": "https://example.com/product-category/cat-5/",
                "seo_title": "Category 5",
                "seo_description": "Category description 5",
            },
        ]

    monkeypatch.setattr(cli_module, "fetch_rows", fake_fetch_rows)

    result = cli_module.main()

    assert result == 0
    assert observed["spec_names"] == ["products", "categories"]
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8-sig").splitlines()
    assert content[0] == "entity_type;id;url;seo_title;seo_description"
    assert "product;101;https://example.com/product/item-101/;Product 101;Description 101" in content[1:]
    assert "category;5;https://example.com/product-category/cat-5/;Category 5;Category description 5" in content[1:]
    assert "Export completed: 2 row(s) saved to" in capsys.readouterr().out


def test_main_run_products_only_passes_only_product_query(monkeypatch, tmp_path):
    _, output_path = prepare_cli(monkeypatch, tmp_path, run=True, products_only=True)
    observed = {}

    def fake_fetch_rows(cfg, specs):
        observed["spec_names"] = [spec.name for spec in specs]
        return [
            {
                "entity_type": "product",
                "id": "201",
                "url": "https://example.com/product/item-201/",
                "seo_title": "Product 201",
                "seo_description": "Description 201",
            }
        ]

    monkeypatch.setattr(cli_module, "fetch_rows", fake_fetch_rows)

    result = cli_module.main()

    assert result == 0
    assert observed["spec_names"] == ["products"]
    content = output_path.read_text(encoding="utf-8-sig").splitlines()
    assert content == [
        "entity_type;id;url;seo_title;seo_description",
        "product;201;https://example.com/product/item-201/;Product 201;Description 201",
    ]


def test_main_run_categories_only_passes_only_category_query(monkeypatch, tmp_path):
    _, output_path = prepare_cli(monkeypatch, tmp_path, run=True, categories_only=True)
    observed = {}

    def fake_fetch_rows(cfg, specs):
        observed["spec_names"] = [spec.name for spec in specs]
        return [
            {
                "entity_type": "category",
                "id": "9",
                "url": "https://example.com/product-category/cat-9/",
                "seo_title": "Category 9",
                "seo_description": "Category description 9",
            }
        ]

    monkeypatch.setattr(cli_module, "fetch_rows", fake_fetch_rows)

    result = cli_module.main()

    assert result == 0
    assert observed["spec_names"] == ["categories"]
    content = output_path.read_text(encoding="utf-8-sig").splitlines()
    assert content == [
        "entity_type;id;url;seo_title;seo_description",
        "category;9;https://example.com/product-category/cat-9/;Category 9;Category description 9",
    ]


def test_main_run_writes_header_only_csv_when_no_rows_returned(monkeypatch, tmp_path, capsys):
    _, output_path = prepare_cli(monkeypatch, tmp_path, run=True)
    monkeypatch.setattr(cli_module, "fetch_rows", lambda cfg, specs: [])

    result = cli_module.main()

    assert result == 0
    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8-sig").splitlines() == ["entity_type;id;url;seo_title;seo_description"]
    assert "Export completed: 0 row(s) saved to" in capsys.readouterr().out


def test_main_dry_run_skips_csv_and_prints_counts(monkeypatch, tmp_path, capsys):
    _, output_path = prepare_cli(monkeypatch, tmp_path, dry_run=True)
    observed = {}

    def fake_dry_run_queries(cfg, specs):
        observed["spec_names"] = [spec.name for spec in specs]
        return {"products": 7, "categories": 3}

    def fail_write_csv(rows, csv_output_path):
        raise AssertionError("write_csv must not be called during dry run")

    monkeypatch.setattr(cli_module, "dry_run_queries", fake_dry_run_queries)
    monkeypatch.setattr(cli_module, "write_csv", fail_write_csv)

    result = cli_module.main()

    output = capsys.readouterr().out
    assert result == 0
    assert observed["spec_names"] == ["products", "categories"]
    assert not output_path.exists()
    assert "Dry run completed successfully" in output
    assert "products: 7 row(s)" in output
    assert "categories: 3 row(s)" in output
    assert "Total rows: 10" in output


def test_main_check_connection_skips_export_and_csv(monkeypatch, tmp_path, capsys):
    prepare_cli(monkeypatch, tmp_path, check_connection=True)
    observed = {"checks": 0}

    def fake_test_connection(cfg):
        observed["checks"] += 1

    def fail_fetch_rows(cfg, specs):
        raise AssertionError("fetch_rows must not be called during connection check")

    def fail_write_csv(rows, output_path):
        raise AssertionError("write_csv must not be called during connection check")

    monkeypatch.setattr(cli_module, "test_connection", fake_test_connection)
    monkeypatch.setattr(cli_module, "fetch_rows", fail_fetch_rows)
    monkeypatch.setattr(cli_module, "write_csv", fail_write_csv)

    result = cli_module.main()

    assert result == 0
    assert observed["checks"] == 1
    assert "config, SSH tunnel, and MySQL access look OK" in capsys.readouterr().out


def test_main_run_returns_error_when_export_pipeline_fails(monkeypatch, tmp_path, capsys):
    prepare_cli(monkeypatch, tmp_path, run=True)
    monkeypatch.setattr(cli_module, "fetch_rows", lambda cfg, specs: (_ for _ in ()).throw(RuntimeError("boom")))

    result = cli_module.main()

    assert result == 1
    assert "❌ Error: boom" in capsys.readouterr().out
