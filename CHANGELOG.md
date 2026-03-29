# Changelog

## v1.0.0-rc1 - 2026-03-29

First public release candidate.

### Included

- stable CLI entrypoints for `--init`, `--run`, `--dry-run`, `--check-connection`, and `--diagnose-seo`
- WordPress + WooCommerce oriented presets for products and categories
- support for Yoast SEO and Rank Math priority with fallback fields
- table prefix support and config validation
- clearer runtime error handling and user-facing help
- unit and integration test coverage for the core pipeline
- clean release bundle for end users, separate from the development repository contents

### Runtime bundle contents

- `seo_exporter.py`
- `cli.py`
- `config.py`
- `db.py`
- `exporter.py`
- `requirements.txt`
- `config.example.json`
- release `README.md`

### Not included in the end-user bundle

- `tests/`
- `docs/`
- `CODEX.md`
- development cache and local artifacts

### Known limitations

- built-in SEO diagnostics focus on Yoast SEO and Rank Math
- custom SEO storage still requires custom SQL in `config.json`
- permalink bases that differ from the WooCommerce defaults must be adjusted in SQL
