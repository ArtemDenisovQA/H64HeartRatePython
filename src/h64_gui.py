import asyncio
import csv
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal, QSettings
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from qasync import QEventLoop, asyncSlot
from bleak import BleakClient

# Берём BLE-логику из src/h64_logger.py (он лежит рядом, в той же папке src)
from h64_logger import HR_SERVICE, HR_CHAR, BAT_CHAR, parse_hr, scan, service_uuids_lower

WINDOW_SEC = 60.0


@dataclass
class Sample:
    t: float   # epoch seconds
    bpm: int


def default_out_path() -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("logs") / f"h64_hr_log_{ts}.csv"


class MainWindow(QMainWindow):
    sample_signal = Signal(float, int)   # (timestamp, bpm)
    battery_signal = Signal(int)
    status_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Magene H64 — Heart Rate Logger (Python)")
        self.resize(980, 600)

        # ---- persistent settings ----
        self.settings = QSettings("ArtemDenisovQA", "H64HeartRatePythonGUI")

        # ---- BLE state ----
        self.client: Optional[BleakClient] = None
        self.connected_address: Optional[str] = None
        self.battery: Optional[int] = None

        # ---- logging state ----
        self.log_path: Path = default_out_path()
        self.log_file = None
        self.log_writer = None

        # ---- plot state ----
        self.samples: list[Sample] = []
        self.bin_counts: dict[int, int] = {}
        self.total_samples = 0

        # ---- UI ----
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        grid = QGridLayout()
        root.addLayout(grid)

        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(520)

        self.address_edit = QLineEdit()
        self.address_edit.setPlaceholderText("Address (UUID). Можно подключаться без Scan.")

        saved_addr = (self.settings.value("last_address", "") or "").strip()
        if saved_addr:
            self.address_edit.setText(saved_addr)

        self.scan_timeout = QSpinBox()
        self.scan_timeout.setRange(3, 60)
        self.scan_timeout.setValue(12)
        self.scan_timeout.setSuffix(" s")

        self.btn_scan = QPushButton("Scan")
        self.btn_connect = QPushButton("Connect")
        self.btn_disconnect = QPushButton("Disconnect")
        self.btn_disconnect.setEnabled(False)

        self.btn_choose_log = QPushButton("Choose log file…")
        self.log_label = QLabel(str(self.log_path))
        self.log_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        # row 0
        grid.addWidget(QLabel("Device (from scan):"), 0, 0)
        grid.addWidget(self.device_combo, 0, 1, 1, 4)
        grid.addWidget(QLabel("Scan timeout:"), 0, 5)
        grid.addWidget(self.scan_timeout, 0, 6)
        grid.addWidget(self.btn_scan, 0, 7)

        # row 1
        grid.addWidget(QLabel("Address (no scan):"), 1, 0)
        grid.addWidget(self.address_edit, 1, 1, 1, 4)
        grid.addWidget(self.btn_connect, 1, 6)
        grid.addWidget(self.btn_disconnect, 1, 7)

        # row 2
        grid.addWidget(QLabel("Log file:"), 2, 0)
        grid.addWidget(self.log_label, 2, 1, 1, 6)
        grid.addWidget(self.btn_choose_log, 2, 7)

        info = QHBoxLayout()
        root.addLayout(info)

        self.status_lbl = QLabel("Status: idle")
        self.bpm_lbl = QLabel("BPM: —")
        self.battery_lbl = QLabel("Battery: —")
        self.range_lbl = QLabel("Most common 10-range: —")

        for w in (self.status_lbl, self.bpm_lbl, self.battery_lbl, self.range_lbl):
            w.setTextInteractionFlags(Qt.TextSelectableByMouse)

        info.addWidget(self.status_lbl, 3)
        info.addWidget(self.bpm_lbl, 1)
        info.addWidget(self.battery_lbl, 1)
        info.addWidget(self.range_lbl, 3)

        # ---- Plot (real time axis) ----
        self.plot = pg.PlotWidget(axisItems={"bottom": pg.DateAxisItem(orientation="bottom")})
        self.plot.setLabel("left", "BPM")
        self.plot.setLabel("bottom", "Time")
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.curve = self.plot.plot([], [])
        root.addWidget(self.plot, 1)

        # ---- Signals ----
        self.sample_signal.connect(self._on_sample_ui)
        self.battery_signal.connect(self._on_battery_ui)
        self.status_signal.connect(self._on_status_ui)

        # ---- Buttons ----
        self.btn_scan.clicked.connect(self.on_scan_clicked)
        self.btn_connect.clicked.connect(self.on_connect_clicked)
        self.btn_disconnect.clicked.connect(self.on_disconnect_clicked)
        self.btn_choose_log.clicked.connect(self.on_choose_log)

    # ---------------- UI slots ----------------

    def _on_status_ui(self, text: str):
        self.status_lbl.setText(f"Status: {text}")

    def _on_battery_ui(self, percent: int):
        self.battery_lbl.setText(f"Battery: {percent}%")

    def _on_sample_ui(self, ts: float, bpm: int):
        self.bpm_lbl.setText(f"BPM: {bpm}")

        # keep last WINDOW_SEC seconds
        self.samples.append(Sample(t=ts, bpm=bpm))
        start = ts - WINDOW_SEC
        self.samples = [s for s in self.samples if s.t >= start]

        xs = [s.t for s in self.samples]   # epoch seconds -> DateAxisItem shows real time
        ys = [s.bpm for s in self.samples]
        self.curve.setData(xs, ys)

        # x window follows "now"
        self.plot.setXRange(start, ts, padding=0)

        # auto-scale Y (not flat)
        if ys:
            ymin = min(ys)
            ymax = max(ys)
            if ymin == ymax:
                ymin -= 5
                ymax += 5
            pad = max(3, int((ymax - ymin) * 0.15))
            self.plot.setYRange(ymin - pad, ymax + pad)

        # update “most common 10-bpm range since connect”
        b0 = (bpm // 10) * 10
        self.bin_counts[b0] = self.bin_counts.get(b0, 0) + 1
        self.total_samples += 1
        best_bin = max(self.bin_counts.items(), key=lambda kv: kv[1])[0]
        best_cnt = self.bin_counts[best_bin]
        pct = (best_cnt / max(1, self.total_samples)) * 100.0
        self.range_lbl.setText(f"Most common 10-range: {best_bin}–{best_bin+9} ({pct:.1f}%)")

        # write to CSV
        self._write_log_row(bpm)

    def _write_log_row(self, bpm: int):
        if not self.log_writer:
            return
        ts = datetime.now().isoformat(timespec="seconds")
        self.log_writer.writerow([ts, bpm, "" if self.battery is None else self.battery])
        self.log_file.flush()

    def on_choose_log(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Choose CSV log file",
            str(self.log_path),
            "CSV Files (*.csv)",
        )
        if path:
            self.log_path = Path(path)
            self.log_label.setText(str(self.log_path))

    # ---------------- BLE actions (async) ----------------

    @asyncSlot()
    async def on_scan_clicked(self):
        self.status_signal.emit("scanning…")
        self.device_combo.clear()

        try:
            found = await scan(timeout=float(self.scan_timeout.value()))
        except Exception as e:
            self.status_signal.emit(f"scan error: {e}")
            return

        items = []
        for addr, (dev, adv) in found.items():
            uuids = service_uuids_lower(adv)
            is_hr = (HR_SERVICE in uuids)
            name = dev.name or ""
            title = f"{name} ({addr})"
            items.append((0 if is_hr else 1, title, addr))

        items.sort(key=lambda x: (x[0], x[1]))

        for _, title, addr in items:
            self.device_combo.addItem(title, userData=addr)

        # if saved address exists and present -> select it
        saved = (self.settings.value("last_address", "") or "").strip()
        if saved:
            for i in range(self.device_combo.count()):
                if (self.device_combo.itemData(i) or "").lower() == saved.lower():
                    self.device_combo.setCurrentIndex(i)
                    break

        self.status_signal.emit(f"scan done: {len(items)} device(s)")

    @asyncSlot()
    async def on_connect_clicked(self):
        if self.client:
            self.status_signal.emit("already connected")
            return

        # priority: manual address -> selected from scan
        address = self.address_edit.text().strip()
        if not address:
            address = self.device_combo.currentData()

        if not address:
            self.status_signal.emit("no address (paste it or Scan)")
            return

        # reset stats
        self.samples = []
        self.bin_counts = {}
        self.total_samples = 0
        self.battery = None
        self.battery_lbl.setText("Battery: —")
        self.range_lbl.setText("Most common 10-range: —")
        self.bpm_lbl.setText("BPM: —")

        # open log file (new file per connection unless user selected specific)
        if not self.log_path:
            self.log_path = default_out_path()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            self.log_file = open(self.log_path, "w", newline="", encoding="utf-8")
            self.log_writer = csv.writer(self.log_file)
            self.log_writer.writerow(["timestamp", "bpm", "battery_percent"])
            self.log_file.flush()
        except Exception as e:
            self.status_signal.emit(f"log file error: {e}")
            self.log_file = None
            self.log_writer = None
            return

        self.status_signal.emit(f"connecting to {address}…")

        self.client = BleakClient(address)
        try:
            await self.client.connect()
        except Exception as e:
            self.status_signal.emit(f"connect failed: {e}")
            await self._cleanup_after_disconnect()
            return

        self.connected_address = address
        # save address for next launches (auto-fill)
        self.settings.setValue("last_address", address)

        # try read battery immediately
        try:
            data = await self.client.read_gatt_char(BAT_CHAR)
            if data:
                self.battery = int(data[0])
                self.battery_signal.emit(self.battery)
        except Exception:
            pass

        # battery notify (optional)
        def on_battery(_sender: int, data: bytearray):
            if data:
                self.battery = int(data[0])
                self.battery_signal.emit(self.battery)

        try:
            await self.client.start_notify(BAT_CHAR, on_battery)
        except Exception:
            pass

        # HR notify
        def on_hr(_sender: int, data: bytearray):
            bpm = parse_hr(data)
            if bpm is None:
                return
            ts = time.time()
            self.sample_signal.emit(ts, bpm)

        try:
            await self.client.start_notify(HR_CHAR, on_hr)
        except Exception as e:
            self.status_signal.emit(f"notify failed: {e}")
            await self._disconnect_internal()
            return

        self.btn_connect.setEnabled(False)
        self.btn_disconnect.setEnabled(True)
        self.status_signal.emit(f"connected: {address} (logging → {self.log_path})")

    @asyncSlot()
    async def on_disconnect_clicked(self):
        await self._disconnect_internal()

    async def _disconnect_internal(self):
        if not self.client:
            return

        self.status_signal.emit("disconnecting…")
        try:
            try:
                await self.client.stop_notify(HR_CHAR)
            except Exception:
                pass
            try:
                await self.client.stop_notify(BAT_CHAR)
            except Exception:
                pass
            await self.client.disconnect()
        finally:
            await self._cleanup_after_disconnect()
            self.status_signal.emit("disconnected")

    async def _cleanup_after_disconnect(self):
        self.client = None
        self.connected_address = None

        if self.log_file:
            try:
                self.log_file.close()
            except Exception:
                pass
        self.log_file = None
        self.log_writer = None

        self.btn_connect.setEnabled(True)
        self.btn_disconnect.setEnabled(False)

    def closeEvent(self, event):
        # graceful disconnect on window close
        if self.client:
            asyncio.create_task(self._disconnect_internal())
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    pg.setConfigOptions(antialias=True)

    win = MainWindow()
    win.show()

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
