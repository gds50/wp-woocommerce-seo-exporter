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

## Документация

- [`docs/github-repo-plan.md`](docs/github-repo-plan.md) - подготовка открытого GitHub-репозитория
- [`docs/production-milestones.md`](docs/production-milestones.md) - поэтапное развитие без поломки текущей базы
- `CODEX.md` - рабочие правила для дальнейших изменений

## Ограничения

- core logic текущего скрипта не должна меняться без отдельного milestone
- формат CSV должен оставаться стабильным
- SQL-логика зависит от конкретной структуры WordPress, WooCommerce, Bono и используемого SEO-плагина
