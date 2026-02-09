# Magene H64 — Heart Rate Logger (Python)

Проект для **macOS**, который подключается по **Bluetooth LE** к нагрудному датчику пульса **Magene H64** и логирует данные.

## Что есть в проекте
- **CLI**: `src/h64_logger.py`
- **GUI**: `src/h64_gui.py` (график BPM в реальном времени, ось X = текущее время)

## Возможности GUI
- Scan устройств (по BLE)
- Connect / Disconnect
- Подключение **по адресу без сканирования** (вставь UUID в поле Address)
- CSV-лог: `timestamp,bpm,battery_percent`
- Статистика: самый частый диапазон 10 BPM (“Most common 10-range”)

> На macOS (Bleak/CoreBluetooth) “address” часто выглядит как UUID (`1F14F124-...`).
> Обычно он стабилен на одном и том же Mac для одного устройства, но иногда может измениться (сброс/forget Bluetooth и т.п.).
> Поэтому GUI **сохраняет последний успешный address** и подставляет его при следующем запуске.

---

## Требования
- macOS
- Python 3.12+
- Датчик должен быть активен (обычно “просыпается”, когда надет)

## Установка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

## Запуск

### GUI

```bash
source .venv/bin/activate
python src/h64_gui.py
```

**Как подключаться:**
1. Если поле **Address** уже заполнено (подставился последний адрес) → нажми **Connect**
2. Если адрес неизвестен → нажми **Scan**, выбери устройство, затем **Connect**
3. Можно вставить address вручную и подключаться **без Scan**

CSV по умолчанию пишется в папку `logs/` (или выбери путь кнопкой **Choose log file…**).

### CLI

Сканировать устройства рядом:

```bash
source .venv/bin/activate
python src/h64_logger.py --list --scan-timeout 12
```

Подключиться и писать CSV:

```bash
source .venv/bin/activate
python src/h64_logger.py --address "ВАШ_UUID_АДРЕС" --scan-timeout 12
```

Остановка: `Ctrl+C`.

---

## Права Bluetooth на macOS

macOS может спросить доступ к Bluetooth. Разреши доступ для:
- **Terminal** (если запускаешь из терминала)
- или **VS Code** (если запускаешь из VS Code / встроенного терминала)

Если доступ был запрещён:
System Settings → Privacy & Security → Bluetooth → включи доступ для нужного приложения.

---

## Troubleshooting

### Датчик не находится
- надень датчик/ремень (H64 “спит”, если не надет)
- убедись, что он не подключён к другой программе (Zwift/сканер и т.п.)
- увеличь scan timeout

### После Connect “ничего не происходит”
- проверь права Bluetooth (Terminal/VS Code)
- попробуй CLI `--list` и возьми address оттуда
- если address изменился — сделай Scan и подключись снова (GUI сохранит новый)

---

## Дисклеймер
Учебный проект. Не медицинское ПО.
