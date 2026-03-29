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
- сохранение результата в CSV
- запуск через CLI и `Makefile`

## Структура репозитория

```text
.
├── seo_exporter.py
├── config.example.json
├── requirements.txt
├── Makefile
├── README.md
├── CODEX.md
├── docs/
└── tests/
```

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
python seo_exporter.py --run --verbose
```

По умолчанию результат сохраняется в `seo_export.csv`.

## Make targets

- `make init` - интерактивно создать `config.json`
- `make run` - выполнить экспорт
- `make test` - проверить синтаксис скрипта
- `make help` - показать доступные команды

## Конфигурация

Проект не хранит реальные креды в коде. Все параметры подключения выносятся в `config.json`.

Шаблон `config.example.json` содержит только безопасные примерные значения:
- SSH host / port / username
- путь к приватному ключу или SSH password
- MySQL user / password / database
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

Что именно считается fallback:

- для товаров: `post_excerpt`, затем `post_content`, затем `post_title`
- для категорий: `description`, затем `name`

Ограничения по URL:

- дефолтные SQL строят человекоподобные URL через стандартные WooCommerce bases: `product/` и `product-category/`
- если на сайте используется нестандартный prefix таблиц вместо `wp_`, его нужно заменить в SQL
- если на сайте изменены permalink bases, их тоже нужно заменить в SQL в `config.json`

## Документация

- [`docs/github-repo-plan.md`](docs/github-repo-plan.md) - подготовка открытого GitHub-репозитория
- [`docs/production-milestones.md`](docs/production-milestones.md) - поэтапное развитие без поломки текущей базы
- `CODEX.md` - рабочие правила для дальнейших изменений

## Ограничения

- core logic текущего скрипта не должна меняться без отдельного milestone
- формат CSV должен оставаться стабильным
- SQL-логика зависит от конкретной структуры WordPress, WooCommerce, Bono и используемого SEO-плагина
