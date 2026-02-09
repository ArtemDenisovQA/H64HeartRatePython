# H64HeartRatePython

Пэт‑проект на **Python** для **macOS**, который подключается к BLE‑датчику пульса **Magene H64**, получает **BPM** (Heart Rate Measurement), по возможности читает **Battery Level**, и **сохраняет данные в CSV‑файл**.

Репозиторий: https://github.com/ArtemDenisovQA/H64HeartRatePython

---

## Возможности

- Поиск BLE‑устройств и вывод списка (`--list`)
- Подключение к датчику по **адресу** (самый надёжный способ) или по подсказке имени (`--name`)
- Вывод BPM в реальном времени в терминал
- Чтение Battery Level (если датчик поддерживает характеристику 0x2A19)
- Логирование в CSV в папку `logs/`
- Изоляция зависимостей через виртуальное окружение `.venv`

---

## Требования

- macOS с поддержкой Bluetooth LE
- Python **3.12+** (рекомендуется через `pyenv`)
- Разрешение Bluetooth для приложения, из которого запускаете скрипт (Terminal / VS Code)

---

## Быстрый старт

### 1) Клонирование

```bash
git clone https://github.com/ArtemDenisovQA/H64HeartRatePython.git
cd H64HeartRatePython
```

### 2) Виртуальное окружение

```bash
python -m venv .venv
source .venv/bin/activate
```

Проверка (должно быть `.venv/bin/python`):

```bash
which python
python --version
```

### 3) Установка зависимостей

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Использование

> Перед запуском **наденьте ремень/датчик**, чтобы Magene H64 «проснулся».

### Показать список ближайших BLE‑устройств

```bash
python src/h64_logger.py --list --scan-timeout 15
```

В списке ищите устройство, помеченное `*HR*` (рекламирует Heart Rate Service), либо похожее по имени.

### Запуск логирования (рекомендуется по адресу)

```bash
python src/h64_logger.py --address "YOUR_DEVICE_ADDRESS" --scan-timeout 15
```

### Запуск по подсказке имени

```bash
python src/h64_logger.py --name "h64" --scan-timeout 15
```

Остановить запись: **Ctrl + C** (скрипт корректно закрывает файл).

---

## Файлы логов

По умолчанию создаются файлы:

- `logs/h64_hr_log_YYYYMMDD_HHMMSS.csv`

Колонки CSV:

- `timestamp` — ISO‑время (секунды)
- `bpm` — текущий пульс
- `battery_percent` — заряд батареи (%), если доступно (иначе пусто)

---

## Разрешения Bluetooth на macOS

Если сканирование/подключение не работает, проверьте:

- **System Settings → Privacy & Security → Bluetooth**  
  Разрешите Bluetooth для **Terminal** и/или **Visual Studio Code** (в зависимости от того, где запускаете скрипт).

---

## Замечания

- Имя датчика в рекламе может быть нестабильным — **подключение по адресу** обычно самое надёжное.
- Battery Level зависит от прошивки/реализации датчика: некоторые устройства дают 0x2A19 всегда, некоторые — только иногда или не дают вовсе.

---

## Лицензия

Пока не выбрана. Можно добавить `MIT` (или другую) при необходимости.
