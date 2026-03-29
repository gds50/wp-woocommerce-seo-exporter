# SEO Exporter для WordPress + WooCommerce + тема Bono

Этот проект изначально подготовлен как **открытый Python-скрипт** для сайта на **WordPress + WooCommerce** с темой **Bono**.

Назначение скрипта:
- подключиться к хостингу по SSH;
- поднять SSH-туннель до MySQL;
- забрать SEO-данные из БД;
- сохранить CSV-файл со столбцами:
  - `entity_type`
  - `id`
  - `url`
  - `seo_title`
  - `seo_description`

Скрипт уже умеет работать в универсальном режиме через SQL-запросы из `config.json`, а дальнейшая доработка до полноценного продукта должна идти **по milestone-плану**, без разрушения уже работающей базы.

---

## Целевой стек

- **CMS:** WordPress
- **E-commerce:** WooCommerce
- **Theme:** Bono
- **Доступ к данным:** SSH + MySQL
- **Язык скрипта:** Python 3
- **Формат выгрузки:** CSV

---

## Что считается SEO-данными в этом проекте

На текущем этапе экспортируются:
- SEO Title
- SEO Description
- человекоподобная ссылка страницы в браузере
- ID сущности для последующего обратного обновления в БД

Поддерживаются 2 типа сущностей:
- товары (`product`)
- категории (`category`)

---

## Почему проект пока не зашит жёстко под WP/WooCommerce

На WordPress + WooCommerce итоговые SEO-данные часто зависят не только от базовых таблиц WordPress/WooCommerce, но и от SEO-плагина.

Чаще всего встречаются варианты:
- Yoast SEO
- Rank Math
- AIOSEO
- кастомные поля темы/проекта

Кроме этого, URL товаров и категорий зависят от настроек permalink-структуры WordPress и WooCommerce. WooCommerce отдельно документирует product permalinks и product category taxonomy (`product_cat`). citeturn294537search0turn294537search2

Поэтому текущая реализация сделана безопасно:
- Python-код универсален;
- SQL хранится в `config.json`;
- логику получения данных можно постепенно адаптировать под конкретный WP/WooCommerce/Bono-проект.

---

## Установка

```bash
pip install -r requirements.txt
```

---

## Первичная настройка

```bash
python seo_exporter.py --init
```

или:

```bash
make init
```

Скрипт создаст `config.json` и добавит его в `.gitignore`.

---

## Запуск

```bash
python seo_exporter.py --run
```

или:

```bash
make run
```

По умолчанию результат сохраняется в `seo_export.csv`.

---

## Полезные флаги

```bash
python seo_exporter.py --run --products-only
python seo_exporter.py --run --categories-only
python seo_exporter.py --run --output=result.csv
python seo_exporter.py --run --verbose
```

---

## Как организовать проект в GitHub

Подробный план: [`docs/github-repo-plan.md`](docs/github-repo-plan.md)

Коротко:
- репозиторий хранит только код, шаблон конфига, документацию, тесты и milestone-план;
- `config.json` не коммитится;
- вся доработка делается через milestone-подход;
- Codex на сервере идёт по шагам из `docs/production-milestones.md`;
- существующая рабочая логика не ломается без веской причины.

Рекомендуемая структура:

```text
seo-exporter/
├── seo_exporter.py
├── config.example.json
├── requirements.txt
├── Makefile
├── README.md
├── CODEX.md
├── docs/
│   ├── github-repo-plan.md
│   └── production-milestones.md
└── tests/
```

---

## Правила развития проекта

1. Сначала milestone.
2. Потом точечная доработка.
3. Затем тесты.
4. Потом commit.
5. Только после этого следующий milestone.

Если архитектурно хочется что-то улучшить, но текущая версия уже работает, изменение переносится в **следующий milestone**, а не ломает текущий.

---

## Документы для дальнейшей работы

- `docs/github-repo-plan.md` — как оформить открытый репозиторий на GitHub
- `docs/production-milestones.md` — как довести проект до production пошагово
- `CODEX.md` — правила для Codex, чтобы он не ломал уже сделанное

---

## Примечание по WordPress / WooCommerce

WooCommerce использует post types и taxonomies, включая `product` и `product_cat`, а permalink-структура настраивается отдельно. Это важно для корректного получения человекоподобных URL товаров и категорий. citeturn294537search0turn294537search2turn294537search5
