# Changelog

## v1.0.1 - 2026-03-29

Patch release with corrected SEO field priority for sites that store metadata in theme or custom fields.

### Fixed

- default product export SQL now prioritizes `seo_meta_title` and `seo_meta_description` before plugin-specific fallbacks
- default category export SQL now prioritizes `seo_meta_title` and `seo_meta_description` before plugin-specific fallbacks
- SEO diagnostics now report theme/custom `seo_meta_*` usage alongside plugin-based sources

### Compatibility

- Python 3.x
- WordPress
- WooCommerce
- Bono theme
- theme/custom SEO meta fields via `seo_meta_title` and `seo_meta_description`
- Yoast SEO
- Rank Math
- fallback to standard WordPress / WooCommerce fields

## v1.0.0 - 2026-03-29

First stable open-source release.

### Stable release notes

- based on the verified `v1.0.0-rc1` release candidate
- runtime CLI contract is fixed for `--init`, `--run`, `--dry-run`, `--check-connection`, and `--diagnose-seo`
- CSV export format is stable:
  `entity_type,id,url,seo_title,seo_description`
- clean release bundle remains the supported distribution format for end users

### Compatibility

- Python 3.x
- WordPress
- WooCommerce
- Bono theme
- Yoast SEO
- Rank Math
- fallback to standard WordPress / WooCommerce fields

### Roadmap for v1.1+

- add built-in support for more SEO storages such as AIOSEO
- improve handling of custom permalink bases
- refine release automation around bundle publishing
- expand diagnostics for non-standard WordPress / WooCommerce schemas

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
