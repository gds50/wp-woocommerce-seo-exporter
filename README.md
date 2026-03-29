# SEO Exporter for WordPress + WooCommerce + Bono

Открытый Python-проект для выгрузки SEO-данных из удаленной базы сайта через SSH.

Проект ориентирован на сайты на базе:
- WordPress
- WooCommerce
- темы Bono

Скрипт подключается к серверу по SSH, поднимает SSH-туннель к MySQL, выполняет SQL-запросы из `config.json` и сохраняет CSV с фиксированным форматом:

```text
entity_type,id,url,seo_title,seo_description
```

## Возможности

- интерактивная инициализация `config.json`
- подключение к MySQL через SSH-туннель
- экспорт товаров и категорий
- диагностика доступных SEO-источников перед экспортом
- сохранение результата в CSV
- запуск через CLI и `Makefile`

## Структура репозитория

```text
.
├── cli.py
├── config.py
├── db.py
├── exporter.py
├── seo_exporter.py
├── config.example.json
├── requirements.txt
├── Makefile
├── README.md
├── CODEX.md
├── docs/
└── tests/
```

Точка входа CLI остаётся прежней: `python seo_exporter.py ...`

## Установка

Требуется Python 3.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Примечание: `sshtunnel` в текущем проекте требует `paramiko < 4`, это уже зафиксировано в `requirements.txt`.

## Настройка

Создайте локальный конфиг:

```bash
make init
```

Альтернатива без `Makefile`:

```bash
python seo_exporter.py --init
```

Во время инициализации будет создан `config.json`. Этот файл не должен попадать в Git, потому что содержит параметры доступа.

Для ориентира в репозитории есть шаблон:

```text
config.example.json
```

## Запуск

Основной сценарий:

```bash
make run
```

Альтернатива:

```bash
python seo_exporter.py --run
```

Дополнительные примеры:

```bash
python seo_exporter.py --run --products-only
python seo_exporter.py --run --categories-only
python seo_exporter.py --run --output=result.csv
python seo_exporter.py --check-connection
python seo_exporter.py --dry-run
python seo_exporter.py --dry-run --products-only
python seo_exporter.py --diagnose-seo
python seo_exporter.py --run --verbose
```

По умолчанию результат сохраняется в `seo_export.csv`.

Для безопасной проверки перед боевым экспортом доступны отдельные режимы:

- `--check-connection` - проверяет `config.json`, SSH-туннель и подключение к MySQL без выполнения экспортных SQL
- `--dry-run` - выполняет выбранные export SQL и показывает количество строк без записи CSV
- `--run` - выполняет полноценный экспорт и сохраняет CSV

## Make targets

- `make init` - интерактивно создать `config.json`
- `make run` - выполнить экспорт
- `make test` - запустить unit-тесты и базовую проверку синтаксиса
- `make help` - показать доступные команды

## Тесты

После установки зависимостей можно запустить:

```bash
make test
```

или напрямую:

```bash
python -m pytest -q
```

## Конфигурация

Проект не хранит реальные креды в коде. Все параметры подключения выносятся в `config.json`.

Шаблон `config.example.json` содержит только безопасные примерные значения:
- SSH host / port / username
- путь к приватному ключу или SSH password
- MySQL user / password / database
- `table_prefix` для WordPress-таблиц
- SQL-запросы для товаров и категорий

## WordPress + WooCommerce notes

По умолчанию проект теперь использует SQL, ориентированный на стандартную структуру WordPress и WooCommerce:

- товары берутся из `wp_posts` с `post_type = 'product'`
- SEO-мета для товаров читается из `wp_postmeta`
- категории товаров берутся из `wp_terms` + `wp_term_taxonomy`
- категории фильтруются по `taxonomy = 'product_cat'`
- SEO-мета категорий читается из `wp_termmeta`

Запросы по умолчанию пытаются заполнить SEO-поля в таком порядке:

- Yoast SEO
- Rank Math
- fallback на стандартные поля WordPress / WooCommerce

Это и есть текущая встроенная стратегия выбора источника SEO-данных:

- если для сущности есть SEO-мета Yoast, используется она;
- если Yoast-мета нет, проверяется Rank Math;
- если ни один из этих источников не найден, используются стандартные поля WordPress / WooCommerce;
- если сайт хранит SEO в другой схеме, нужно задать свой SQL в `config.json`.

Что именно считается fallback:

- для товаров: `post_excerpt`, затем `post_content`, затем `post_title`
- для категорий: `description`, затем `name`

Ограничения по URL:

- дефолтные SQL строят человекоподобные URL через стандартные WooCommerce bases: `product/` и `product-category/`
- если на сайте используется нестандартный prefix таблиц вместо `wp_`, можно поменять `export.table_prefix`
- если на сайте изменены permalink bases, их тоже нужно заменить в SQL в `config.json`

## Config flexibility

В `config.json` теперь поддерживаются оба сценария:

- поменять `export.table_prefix`, если таблицы сайта используют не `wp_`, а другой prefix, например `wp2_`
- задать полностью свои SQL в `export.queries.products.sql` и `export.queries.categories.sql`

Поведение по умолчанию остается совместимым:

- если `table_prefix` не указан, используется `wp_`
- если `queries` или конкретный `sql` не заданы, скрипт подставляет стандартные WordPress/WooCommerce запросы
- если в SQL есть токен `{table_prefix}`, он заменяется на значение `export.table_prefix` во время запуска
- старые конфиги с уже прописанными SQL продолжают работать без изменений

На старте скрипт валидирует конфиг до подключения к SSH:

- обязательные секции `ssh`, `database`, `export`
- обязательные ключи подключения и `export.base_url`
- корректность `export.table_prefix`
- корректность структуры `export.queries`

## SEO diagnostics

Для безопасной проверки источников SEO перед экспортом можно использовать:

```bash
python seo_exporter.py --diagnose-seo
```

Этот режим:

- не записывает CSV;
- не меняет поведение `--run`;
- показывает, найдены ли в базе типовые SEO meta keys для Yoast SEO и Rank Math;
- показывает базовое количество товаров и товарных категорий для проверки структуры WooCommerce.

Ограничения:

- встроенный экспорт и диагностика ориентированы на Yoast SEO и Rank Math;
- `AIOSEO` пока не определяется встроенно;
- если сайт хранит SEO в `AIOSEO` или в кастомной схеме, следует использовать собственный SQL в `config.json`.

## Safe checks

Проверка соединения без запуска экспортных SQL:

```bash
python seo_exporter.py --check-connection
```

Проверка export SQL без записи CSV:

```bash
python seo_exporter.py --dry-run
python seo_exporter.py --dry-run --products-only
```

В `--dry-run` скрипт:

- использует тот же `config.json` и те же query presets / custom SQL;
- выполняет SQL и валидирует структуру строк;
- показывает количество строк по каждому выбранному query;
- не создаёт и не перезаписывает CSV-файл.

## Документация

- [`docs/github-repo-plan.md`](docs/github-repo-plan.md) - подготовка открытого GitHub-репозитория
- [`docs/production-milestones.md`](docs/production-milestones.md) - поэтапное развитие без поломки текущей базы
- `CODEX.md` - рабочие правила для дальнейших изменений

## Ограничения

- core logic текущего скрипта не должна меняться без отдельного milestone
- формат CSV должен оставаться стабильным
- SQL-логика зависит от конкретной структуры WordPress, WooCommerce, Bono и используемого SEO-плагина
