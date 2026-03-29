import argparse
import copy

import pytest

import cli as cli_module
import config as config_module
import exporter as exporter_module


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


def make_config():
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


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["seo_exporter.py", "--diagnose-seo"], "diagnose_seo"),
        (["seo_exporter.py", "--dry-run"], "dry_run"),
        (["seo_exporter.py", "--check-connection"], "check_connection"),
    ],
)
def test_parse_args_parses_action_flags(monkeypatch, argv, expected):
    monkeypatch.setattr("sys.argv", argv)

    args = cli_module.parse_args()

    assert getattr(args, expected) is True
    assert args.run is False


def test_main_returns_error_when_no_action_is_selected(monkeypatch, capsys):
    monkeypatch.setattr(cli_module, "parse_args", lambda: make_args())
    monkeypatch.setattr(cli_module, "setup_logging", lambda verbose: None)

    result = cli_module.main()

    assert result == 2
    assert "Use --init, --run, --dry-run, --check-connection, or --diagnose-seo" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("arg_overrides", "expected_fragment"),
    [
        ({"run": True, "diagnose_seo": True}, "--run, --diagnose-seo"),
        ({"dry_run": True, "check_connection": True}, "--dry-run, --check-connection"),
    ],
)
def test_main_rejects_conflicting_actions(monkeypatch, capsys, arg_overrides, expected_fragment):
    monkeypatch.setattr(cli_module, "parse_args", lambda: make_args(**arg_overrides))
    monkeypatch.setattr(cli_module, "setup_logging", lambda verbose: None)

    result = cli_module.main()

    assert result == 2
    assert expected_fragment in capsys.readouterr().out


@pytest.mark.parametrize(
    ("products_only", "categories_only", "expected_names"),
    [
        (True, False, ["products"]),
        (False, True, ["categories"]),
    ],
)
def test_main_filters_query_specs_for_cli_flags(monkeypatch, products_only, categories_only, expected_names):
    config = config_module.validate_config(copy.deepcopy(make_config()))
    all_specs = [
        exporter_module.QuerySpec(name="products", sql="SELECT 1", entity_type="product"),
        exporter_module.QuerySpec(name="categories", sql="SELECT 2", entity_type="category"),
    ]
    observed = {}

    monkeypatch.setattr(cli_module, "parse_args", lambda: make_args(run=True, products_only=products_only, categories_only=categories_only))
    monkeypatch.setattr(cli_module, "setup_logging", lambda verbose: None)
    monkeypatch.setattr(cli_module, "load_config", lambda: copy.deepcopy(config))
    monkeypatch.setattr(cli_module, "validate_config", lambda cfg: cfg)
    monkeypatch.setattr(cli_module, "build_query_specs", lambda cfg: list(all_specs))

    def fake_fetch_rows(cfg, specs):
        observed["spec_names"] = [spec.name for spec in specs]
        return []

    def fake_write_csv(rows, output_path):
        observed["rows"] = rows
        observed["output_path"] = output_path

    monkeypatch.setattr(cli_module, "fetch_rows", fake_fetch_rows)
    monkeypatch.setattr(cli_module, "write_csv", fake_write_csv)

    result = cli_module.main()

    assert result == 0
    assert observed["spec_names"] == expected_names
    assert observed["rows"] == []
    assert str(observed["output_path"]) == "seo_export.csv"


def test_main_runs_diagnostics_without_export(monkeypatch):
    config = config_module.validate_config(copy.deepcopy(make_config()))
    calls = {"diagnose": 0}

    monkeypatch.setattr(cli_module, "parse_args", lambda: make_args(diagnose_seo=True))
    monkeypatch.setattr(cli_module, "setup_logging", lambda verbose: None)
    monkeypatch.setattr(cli_module, "load_config", lambda: copy.deepcopy(config))
    monkeypatch.setattr(cli_module, "validate_config", lambda cfg: cfg)

    def fake_diagnose(cfg):
        calls["diagnose"] += 1

    monkeypatch.setattr(cli_module, "diagnose_seo_sources", fake_diagnose)

    result = cli_module.main()

    assert result == 0
    assert calls["diagnose"] == 1


def test_main_runs_connection_check_without_export(monkeypatch, capsys):
    config = config_module.validate_config(copy.deepcopy(make_config()))
    calls = {"check": 0}

    monkeypatch.setattr(cli_module, "parse_args", lambda: make_args(check_connection=True))
    monkeypatch.setattr(cli_module, "setup_logging", lambda verbose: None)
    monkeypatch.setattr(cli_module, "load_config", lambda: copy.deepcopy(config))
    monkeypatch.setattr(cli_module, "validate_config", lambda cfg: cfg)

    def fake_test_connection(cfg):
        calls["check"] += 1

    monkeypatch.setattr(cli_module, "test_connection", fake_test_connection)

    result = cli_module.main()

    assert result == 0
    assert calls["check"] == 1
    assert "Connection check passed" in capsys.readouterr().out


def test_main_runs_dry_run_without_writing_csv(monkeypatch, capsys):
    config = config_module.validate_config(copy.deepcopy(make_config()))
    observed = {}

    monkeypatch.setattr(cli_module, "parse_args", lambda: make_args(dry_run=True, products_only=True))
    monkeypatch.setattr(cli_module, "setup_logging", lambda verbose: None)
    monkeypatch.setattr(cli_module, "load_config", lambda: copy.deepcopy(config))
    monkeypatch.setattr(cli_module, "validate_config", lambda cfg: cfg)

    all_specs = [
        exporter_module.QuerySpec(name="products", sql="SELECT 1", entity_type="product"),
        exporter_module.QuerySpec(name="categories", sql="SELECT 2", entity_type="category"),
    ]
    monkeypatch.setattr(cli_module, "build_query_specs", lambda cfg: list(all_specs))

    def fake_dry_run_queries(cfg, specs):
        observed["spec_names"] = [spec.name for spec in specs]
        return {"products": 12}

    def fail_write_csv(rows, output_path):
        raise AssertionError("write_csv must not be called during dry run")

    monkeypatch.setattr(cli_module, "dry_run_queries", fake_dry_run_queries)
    monkeypatch.setattr(cli_module, "write_csv", fail_write_csv)

    result = cli_module.main()

    output = capsys.readouterr().out
    assert result == 0
    assert observed["spec_names"] == ["products"]
    assert "Dry run completed" in output
    assert "products: 12 row(s)" in output
    assert "Total rows: 12" in output


def test_load_config_exits_when_config_file_is_missing(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(config_module, "CONFIG_PATH", tmp_path / "missing-config.json")

    with pytest.raises(SystemExit) as exc_info:
        config_module.load_config()

    assert exc_info.value.code == 1
    assert "config.json not found" in capsys.readouterr().out
