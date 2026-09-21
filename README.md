# 🚀 GigaChat to OpenAI Proxy Manager (gigaToOpenAi)

Удобный графический менеджер (GUI на PyQt6) и прокси-сервер для подключения моделей **GigaChat** (Сбер) в популярные AI-расширения и редакторы кода: **Continue.dev**, **OpenAI Codex**, **VS Code**, **Antigravity IDE / CLI** и любые другие клиенты с поддержкой OpenAI API.

---

## 🌟 Основные возможности

1. **Графический интерфейс на PyQt6**:
   - Управление запуском, остановкой и перезапуском сервера в один клик.
   - Выбор активной модели GigaChat (`GigaChat-3-Ultra`, `GigaChat-Max`, `GigaChat-Pro`, `GigaChat-Lite`) через выпадающий список.
   - Тестирование учетных данных и автоматическое получение списка доступных аккаунту моделей.
   - Живой просмотр логов HTTP-запросов и ответов.

2. **Защита от "зомби-процессов" (Free Port 8090)**:
   - Автоматическое и ручное освобождение порта `8090` при запуске/перезапуске.
   - Сканирование сетевых соединений (`netstat`) и полное завершение дерева зависших процессов (`taskkill /F /T`).
   - Исключает ошибку `Port 8090 is already in use on localhost. Possible zombie process`.

3. **Интеграция с Continue.dev**:
   - **Установка в 1 клик**: прямо из интерфейса (через VS Code CLI `code --install-extension` или переход в [Visual Studio Marketplace](https://marketplace.visualstudio.com/items?itemName=Continue.continue)).
   - **Автопатчинг `config.yaml`**: автоматическая генерация и добавление секций моделей GigaChat с ролями `chat`, `edit`, `apply` и поддержкой инструментов (`tool_use`).
   - Кнопка быстрого отката/восстановления резервной копии.

4. **Глубокая интеграция с OpenAI Codex**:
   - Автоматическая настройка `~/.codex/config.toml` и переменных окружения Windows (`OPENAI_BASE_URL`, `OPENAI_API_KEY`).
   - Патчинг расширения Codex в VS Code (обход жесткой проверки провайдеров в JS-бандлах).
   - Миграция истории сессий SQLite (`state_5.sqlite`, `codex-dev.db`) и `.jsonl` файлов на новый провайдер `gpt2giga`.

5. **Автоматический SSL-обход**:
   - Встроенный обход проверки самоподписанных TLS-сертификатов Сбера/Минцифры для предотвращения ошибок `[SSL: CERTIFICATE_VERIFY_FAILED]` при потоковом стриминге.

---

## 📦 Быстрый старт

### Вариант 1: Запуск скомпилированного .exe (без установки Python)
Скачайте готовый `GigaChatProxyManager.exe` из папки `dist/` или релизов и запустите.

### Вариант 2: Запуск из исходного кода

```bash
# 1. Клонируйте репозиторий
git clone https://github.com/serresident/gigaToOpenAi.git
cd gigaToOpenAi

# 2. Установите зависимости
pip install -r requirements.txt

# 3. Запустите GUI
python proxy_manager.py
```

---

## ⚙️ Настройка и первый запуск

1. Запустите **GigaChat Proxy Manager**.
2. В поле **GigaChat Credentials** введите ваш ключ авторизации (Base64-строка из личного кабинета GigaChat API: `Client ID:Client Secret`).
3. Нажмите кнопку **"Test Connection"**:
   - Программа проверит подключение к OAuth GigaChat.
   - Загрузит список моделей, доступных вашему аккаунту.
4. Выберите желаемую модель (для написания кода и агентов рекомендуется **GigaChat-3-Ultra** или **GigaChat-Max**).
5. Нажмите **"Start Server"**. Сервер запустится локально по адресу `http://localhost:8090/v2`.

---

## 🧩 Подключение к Continue.dev

1. В блоке **Patch & Backup Configs** нажмите:
   - **🌐 Install Continue.dev** — установит расширение в VS Code автоматически или откроет страницу [Continue в VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=Continue.continue).
   - **⚙️ Patch Continue.dev** — автоматически запишет конфигурацию модели в `%USERPROFILE%\.continue\config.yaml`.
2. Откройте VS Code. На панели Continue выберите модель `GigaChat (...)`.
3. Модель сразу готова к генерации, рефакторингу и применению diff-правок прямо в файлах!

---

## 🛠️ Сборка в EXE

Для самостоятельной сборки приложения в один `.exe` файл используется `PyInstaller`:

```bash
pyinstaller --noconsole --onefile --name GigaChatProxyManager proxy_manager.py
```

Готовый файл появится в папке `dist/GigaChatProxyManager.exe`.

---

## 📄 Лицензия

MIT License.
