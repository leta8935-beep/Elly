# ZeBot

Объединённая версия ZeBot с упрощёнными slash-командами, внешним хранением медиа и быстрым HTML-рендером.

## Что изменено

- Паспорт и его дизайн сохранены.
- Экономика, работа, магазин и рынок объединены в `/game`.
- Профиль, рейтинг и паспорт объединены в `/profile`.
- Настройка, модерация и админ-команды объединены в `/admin`.
- Персонажи сокращены до `/char`.
- Организации, партии и выборы остаются отдельными понятными разделами.
- Приветствия новых участников включаются и настраиваются через `/admin setup`.
- Медиа организаций/партий/выборов не хранится в папке бота: сохраняются URL внешнего хранилища.
- Chromium запускается один раз на процесс и переиспользуется.
- У HTML-рендера есть жёсткий таймаут; `networkidle` удалён, поэтому внешние картинки не могут повесить команду навсегда.

## Основные команды

- `/game balance`, `/game pay`, `/game work`, `/game daily`, `/game crime`
- `/game shop`, `/game buy`, `/game inventory`, `/game sell`
- `/game market`, `/game list`, `/game unlist`, `/game take`
- `/profile show`, `/profile top`, `/profile passport`
- `/admin setup`, `/admin purge` и остальные административные команды
- `/char create`, `/char list`, `/char switch`, `/char off`
- `/org ...`, `/party ...`, `/election ...`

## Docker / Playwright

Docker-образ и пакет Playwright синхронизированы на **1.64.1**:

`mcr.microsoft.com/playwright/python:v1.64.1-jammy`

Это устраняет ошибку `Executable doesn't exist ... chrome-headless-shell`, которая возникала из-за образа 1.40.0 при установленном Playwright 1.64.1.

## Запуск

1. Создайте `.env`:

```env
DISCORD_TOKEN=...
DATABASE_URL=postgresql://...
MEDIA_STORAGE_URL=https://your-storage.example
MEDIA_STORAGE_TOKEN=...
```

2. Запустите Docker Compose/контейнер с этим проектом.
3. Для Discord включите **Server Members Intent** — он нужен приветствиям.
4. Откройте `/admin setup`, включите приветствия и выберите канал.

Если внешний storage не настроен, бот не создаёт локальную папку `flags` и не складывает пользовательские данные рядом с кодом.
