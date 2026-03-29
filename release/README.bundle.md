# SEO Exporter {{VERSION}}

Clean runtime bundle for exporting SEO data from a remote WordPress + WooCommerce database over SSH.

## Included files

- `seo_exporter.py`
- `cli.py`
- `config.py`
- `db.py`
- `exporter.py`
- `requirements.txt`
- `config.example.json`

## Quick start

1. Create a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Create your local config:

```bash
python seo_exporter.py --init
```

3. Verify access before export:

```bash
python seo_exporter.py --check-connection
python seo_exporter.py --dry-run
```

4. Run the export:

```bash
python seo_exporter.py --run
```

## Notes

- `config.json` is not included in this bundle and must stay local.
- CSV format remains stable:

```text
entity_type,id,url,seo_title,seo_description
```

- Built-in SEO support targets Yoast SEO and Rank Math first, with fallback to standard WordPress / WooCommerce fields.
