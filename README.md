# Фид автозагрузки Авито — ATOMM.STORE

Каждый день GitHub Actions читает прайс поставщика из Telegram-канала, добавляет наценку (2%)
и собирает фид `docs/avito.xml`, который Авито забирает по ссылке.

- `scripts/run_daily.py` — ежедневный прогон (workflow «Обновление фида Авито»)
- `scripts/login.py` — одноразовый вход в Telegram (workflow «Вход в Telegram»)
- `docs/report.json` — отчёт последнего прогона: сколько объявлений, что не разобрано
