.PHONY: init run test clean help

init: ## Первоначальная настройка проекта (Initial project setup)
	@python seo_exporter.py --init

run: ## Запуск экспорта SEO в CSV (Run SEO export to CSV)
	@python seo_exporter.py --run $(ARGS)

test: ## Запуск unit-тестов и базовой проверки синтаксиса (Run unit tests and syntax check)
	@python -m py_compile seo_exporter.py
	@python -m pytest -q

clean: ## Очистка временных файлов (Clean temporary files)
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@find . -type f -name "*.pyc" -delete

help: ## Показать доступные команды (Show available commands)
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
