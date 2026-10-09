# Запись на консультации

- **Тестовая версия** (GitHub Pages, данные хранятся в браузере): [страница для клиентов](https://sk-strategy.github.io/zapis-konsultacii/) · [админка](https://sk-strategy.github.io/zapis-konsultacii/admin.html)
- **Рабочий сервис** — папка [`server/`](server/README.md): Flask + SQLite, вход для менеджеров, CRM.
- Тексты воронки (вопросы, ответы, оффер) — `server/funnel.json`.
- Пересобрать тестовую версию: `python tools/build_demo.py`.
