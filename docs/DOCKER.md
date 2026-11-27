# Запуск BCC Business Shield в Docker

Локальный запуск бэкенда (FastAPI) и фронтенда (Next.js) через Docker Compose в двух режимах: **демо** (по умолчанию, состояние в памяти) и **рабочем (`prod`)** (авторизация, роли, SQLite в именованном томе).

## Требования

- **Docker Desktop** (Windows/macOS) или **Docker Engine** (Linux) с включённым BuildKit (по умолчанию в актуальных версиях).
- **Docker Compose v2.24+** (используется `env_file` с `required: false`). Проверить версию: `docker compose version`.
- Свободные порты `3000` и `8000` (можно переопределить переменными окружения).

## Быстрый старт (демо-режим)

Из корня репозитория:

```bash
docker compose up --build
```

Запустятся только сервисы `backend-demo` и `frontend-demo`:

- Интерфейс: <http://localhost:3000>
- Документация API (Swagger): <http://localhost:8000/docs>

Для запуска в фоне добавьте `-d`: `docker compose up --build -d`.

## Рабочий режим (`prod`)

Оба режима используют одинаковые порты хоста (`3000` и `8000`), поэтому перед переключением остановите демо:

```bash
docker compose down
docker compose --profile prod up --build backend-prod frontend-prod
```

> Указывайте имена сервисов `backend-prod frontend-prod` явно: демо-сервисы не привязаны к профилю, поэтому команда `docker compose --profile prod up --build` без списка сервисов попытается поднять оба стека одновременно и упрётся в конфликт портов.

- Интерфейс: <http://localhost:3000> (вход на `/login`)
- Документация API (Swagger): <http://localhost:8000/docs>

В `prod`-режиме браузер обращается к API по тому же origin (`http://localhost:3000/api/v1/*`, `/api/invoice/*`, `/api/explain`), а Next.js проксирует запросы на `backend-prod:8000` через `rewrites`, поэтому сессионные cookie работают на одном домене. Порт `8000` дополнительно опубликован для Swagger UI и прямой диагностики API.

При желании можно показать на странице `/login` кнопки быстрой подстановки логинов (`accountant`, `director`, `analyst`; пароль всё равно вводится вручную), передав build-аргумент `NEXT_PUBLIC_DEMO_LOGINS=1`:

```bash
# bash / zsh
NEXT_PUBLIC_DEMO_LOGINS=1 docker compose --profile prod up --build backend-prod frontend-prod
```

```powershell
# PowerShell
$env:NEXT_PUBLIC_DEMO_LOGINS="1"
docker compose --profile prod up --build backend-prod frontend-prod
```

## Где найти пароли пользователей (`prod`)

При первом запуске, когда файла БД `/app/var/shield.db` в томе `shield-prod-data` ещё нет, entrypoint автоматически выполняет:

```text
python -m app.prod.seed --reset --with-queue
```

Случайные пароли для `accountant`, `director` и `analyst` выводятся в логи контейнера `backend-prod` **один раз** при инициализации БД.

Просмотр всех логов `backend-prod`:

```bash
docker compose --profile prod logs backend-prod
```

Поиск строк с паролями:

```bash
# bash / zsh
docker compose --profile prod logs backend-prod | grep "Generated seed password"
```

```powershell
# PowerShell
docker compose --profile prod logs backend-prod | Select-String "Generated seed password"
```

При первом входе со сгенерированным паролем приложение потребует сменить его. Если нужны заранее известные пароли для локального тестирования, задайте `SHIELD_SEED_PASSWORD_ACCOUNTANT`, `SHIELD_SEED_PASSWORD_DIRECTOR`, `SHIELD_SEED_PASSWORD_ANALYST` (или общий `SHIELD_SEED_PASSWORD`) в `backend/.env` **до** первого создания БД.

## Сброс базы данных (`prod`)

База SQLite хранится в именованном Docker-томе `shield-prod-data` (смонтирован в `/app/var`). Чтобы полностью сбросить БД и заново выполнить seed:

```bash
docker compose --profile prod down -v
docker compose --profile prod up --build backend-prod frontend-prod
```

Флаг `-v` удаляет том `shield-prod-data`; при следующем запуске БД создастся заново, а в логах появятся новые пароли.

## Необязательный `ANTHROPIC_API_KEY` через `backend/.env`

Ядро проверки платежей работает полностью локально без внешних сетевых вызовов. Вспомогательные эндпоинты `/api/invoice/extract` и `/api/explain` работают и без ключа (локальные шаблоны), но могут использовать внешний API, если задать `ANTHROPIC_API_KEY`.

Файл `backend/.env` **никогда не копируется в образ** (исключён в `backend/.dockerignore`), а подключается только при запуске контейнера через `env_file` с `required: false`. Если файла нет — запуск проходит без ошибок.

Пример `backend/.env`:

```dotenv
ANTHROPIC_API_KEY=your-api-key-here
```

После добавления или изменения `backend/.env` перезапустите контейнер бэкенда (`docker compose up -d` или `docker compose --profile prod up -d backend-prod frontend-prod`) — пересобирать образы не нужно. Не добавляйте в `backend/.env` настройку `SHIELD_COOKIE_SECURE=1` при локальном запуске по `http://localhost` (см. раздел «Решение проблем»).

## Смена портов

Порты на хосте задаются переменными `FRONTEND_PORT` (по умолчанию `3000`) и `BACKEND_PORT` (по умолчанию `8000`).

- **В `prod`-режиме** браузер ходит в API через прокси Next.js на порту фронтенда, поэтому достаточно сменить порты при запуске:

  ```bash
  # bash / zsh
  FRONTEND_PORT=3001 BACKEND_PORT=8001 docker compose --profile prod up backend-prod frontend-prod
  ```

  ```powershell
  # PowerShell
  $env:FRONTEND_PORT="3001"; $env:BACKEND_PORT="8001"
  docker compose --profile prod up backend-prod frontend-prod
  ```

- **В демо-режиме** браузер обращается к бэкенду напрямую по адресу `NEXT_PUBLIC_API_URL` (по умолчанию `http://localhost:8000`). Эта переменная встраивается в клиентский бандл Next.js **на этапе сборки**, поэтому при изменении `BACKEND_PORT` нужно пересобрать `frontend-demo` с новым `NEXT_PUBLIC_API_URL`:

  ```bash
  # bash / zsh
  BACKEND_PORT=8001 FRONTEND_PORT=3001 NEXT_PUBLIC_API_URL=http://localhost:8001 docker compose up --build
  ```

  ```powershell
  # PowerShell
  $env:BACKEND_PORT="8001"; $env:FRONTEND_PORT="3001"; $env:NEXT_PUBLIC_API_URL="http://localhost:8001"
  docker compose up --build
  ```

## Остановка и пересборка

Остановка контейнеров (том БД `shield-prod-data` сохраняется):

```bash
# Демо
docker compose down

# Prod
docker compose --profile prod down
```

Пересборка после изменения кода или build-аргументов (`NEXT_PUBLIC_*`, `BACKEND_URL`):

```bash
# Демо
docker compose up --build

# Prod
docker compose --profile prod up --build backend-prod frontend-prod
```

Полная пересборка без кэша слоёв:

```bash
# Демо
docker compose build --no-cache && docker compose up

# Prod
docker compose --profile prod build --no-cache backend-prod frontend-prod
docker compose --profile prod up backend-prod frontend-prod
```

## Решение проблем

- **Порт уже занят (`port is already allocated` / `address already in use`)**
  Проверьте, не запущен ли другой режим (демо/prod) или локальный dev-сервер. Остановите предыдущий стек (`docker compose down` или `docker compose --profile prod down`) либо задайте другие `FRONTEND_PORT` и `BACKEND_PORT`.

- **Бэкенд в статусе `unhealthy` (`dependency failed to start`)**
  Проверьте логи: `docker compose logs backend-demo` или `docker compose --profile prod logs backend-prod`. В `prod`-режиме первый старт применяет миграции и заполняет БД — healthcheck ждёт до ~110 секунд (`start_period: 10s`, 20 попыток каждые 5 с). Частая причина немедленного падения — конфликт переменных `SHIELD_COOKIE_INSECURE=1` и `SHIELD_COOKIE_SECURE=1` в `backend/.env`.

- **Не удаётся войти / сбрасывается сессия на `http://localhost` (`prod`)**
  По умолчанию в `prod`-режиме бэкенд выставляет cookie с флагом `Secure` и префиксом `__Host-`, которые браузеры отклоняют по обычному HTTP. В `docker-compose.yml` для локального запуска уже задан `SHIELD_COOKIE_INSECURE=1`. Убедитесь, что вы открываете приложение через фронтенд (<http://localhost:3000>), а в `backend/.env` нет `SHIELD_COOKIE_SECURE=1`. При развёртывании за HTTPS-прокси переопределите `SHIELD_COOKIE_INSECURE=0`.

- **Docker daemon не запущен (`Cannot connect to the Docker daemon`)**
  Запустите Docker Desktop (Windows/macOS) или службу `docker` (Linux) и дождитесь ответа от `docker info`.

- **Изменение `BACKEND_URL` (или `NEXT_PUBLIC_*`) не применяется**
  В `frontend/next.config.ts` функция `rewrites()` читает `NEXT_PUBLIC_APP_MODE` и `BACKEND_URL` на этапе `next build` и запекает маршруты в `.next/routes-manifest.json`, а переменные `NEXT_PUBLIC_*` встраиваются в клиентский JS-бандл. После изменения любой из них обязательна пересборка фронтенда с флагом `--build`.

- **Окончания строк в Windows (`CRLF`)**
  Если Git на Windows настроен с `core.autocrlf=true`, текстовые файлы могут выгружаться с `CRLF`. В `backend/Dockerfile` встроенный `/usr/local/bin/entrypoint.sh` автоматически очищается от `\r` (`sed -i 's/\r$//'`), однако для `backend/.env` лучше сохранять файл в формате `LF`, чтобы в конце значений ключей не появлялся лишний символ `\r`.
