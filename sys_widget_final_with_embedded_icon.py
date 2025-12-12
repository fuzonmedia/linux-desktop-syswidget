#!/usr/bin/env python3
"""
sys_widget_final_with_embedded_icon.py

Behavior fix: window will NOT be forced always-on-top by default.
 - WindowStaysOnTopHint is explicitly cleared on init so most WMs won't keep it above other apps.
 - Only when the user enables "Always on Top" (tray or context menu) will the hint be set.
 - When showing the window we avoid calling raise()/activateWindow() unless Always on Top is enabled,
   so other application windows can cover the widget.
 - All other features remain unchanged: tray icon, autostart toggle, GPU via nvidia-smi, themes, config autosave.
"""

import os
import sys
import json
import argparse
import subprocess
import shlex
import signal
from pathlib import Path

import psutil
from PyQt5.QtCore import Qt, QTimer, QPoint, QRect
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QProgressBar, QSystemTrayIcon, QMenu, QAction, QScrollArea,
    QFrame
)
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QCursor, QLinearGradient, QBrush

# -----------------------------
# Paths & Config
# -----------------------------
CONFIG_DIR = Path.home() / ".config" / "sys_widget"
CONFIG_FILE = CONFIG_DIR / "widget_config.json"
ICON_FILE = CONFIG_DIR / "icon.png"
AUTOSTART_DIR = Path.home() / ".config" / "autostart"
AUTOSTART_FILE = AUTOSTART_DIR / "sys_widget.desktop"

DEFAULT_SETTINGS = {
    "screen": 0,
    "x": 0,
    "y": 0,
    "width": 480,
    "height": 300,
    "interval": 1000,
    "theme": "dark",
    "transparent": False,
    "click_through": False,
    "core_orientation": "horizontal",
    "start_minimized": False,
    "always_on_top": False,
    "show_in_taskbar": False,
    "autostart_enabled": False,
    "show_cpu": True,
    "show_ram": True,
    "show_gpu_core": True,
    "show_gpu_vram": True,
    "show_gpu_meta": True
}

def load_settings():
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            for k, v in DEFAULT_SETTINGS.items():
                if k not in cfg:
                    cfg[k] = v
            return cfg
    except Exception:
        pass
    return DEFAULT_SETTINGS.copy()

def save_settings(cfg):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

# -----------------------------
# nvidia-smi parser
# -----------------------------
_SMI_QUERY = (
    "nvidia-smi --query-gpu=index,name,utilization.gpu,temperature.gpu,"
    "memory.total,memory.used,power.draw,fan.speed --format=csv,noheader,nounits"
)

def query_nvidia_smi():
    try:
        out = subprocess.check_output(shlex.split(_SMI_QUERY), stderr=subprocess.STDOUT, timeout=5)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []
    except Exception:
        return []
    text = out.decode("utf-8", errors="ignore").strip()
    if not text:
        return []
    gpus = []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for line in lines:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 8:
            continue
        idx_raw = parts[0]
        tail = parts[-6:]
        name_parts = parts[1: len(parts) - 6]
        name = ",".join(name_parts).strip() if name_parts else parts[1]
        try:
            index = int(idx_raw)
        except Exception:
            index = None
        try:
            util = int(tail[0]) if tail[0] != "" else None
        except Exception:
            util = None
        try:
            temp = int(tail[1]) if tail[1] != "" else None
        except Exception:
            temp = None
        try:
            mem_total = float(tail[2]) if tail[2] != "" else None
            mem_used = float(tail[3]) if tail[3] != "" else None
            mem_percent = (mem_used * 100.0 / mem_total) if (mem_total and mem_used is not None) else None
            if mem_percent is not None:
                mem_percent = float(mem_percent)
        except Exception:
            mem_total = mem_used = mem_percent = None
        try:
            power_w = float(tail[4]) if tail[4] != "" else None
        except Exception:
            power_w = None
        try:
            fan = int(tail[5]) if tail[5] != "" else None
        except Exception:
            fan = None
        gpus.append({
            "index": index,
            "name": name,
            "util": util,
            "temp": temp,
            "mem_total_mb": mem_total,
            "mem_used_mb": mem_used,
            "mem_percent": mem_percent,
            "power_w": power_w,
            "fan": fan
        })
    return gpus

# -----------------------------
# Embedded icon generator
# -----------------------------
def generate_and_save_icon(path: Path, size=128):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        grad = QLinearGradient(0, 0, size, size)
        grad.setColorAt(0.0, QColor(14,36,63))
        grad.setColorAt(1.0, QColor(18,102,160))
        p.setBrush(QBrush(grad)); p.setPen(Qt.NoPen)
        p.drawEllipse(0, 0, size, size)
        p.setPen(Qt.NoPen)
        stripe_brush = QBrush(QColor(255, 255, 255, 28))
        p.setBrush(stripe_brush)
        for i in range(3):
            rect_x = int(size * 0.18 + i * size * 0.12)
            p.drawRoundedRect(rect_x, int(size * 0.25), int(size * 0.14), int(size * 0.5), 4, 4)
        font = QFont("Sans Serif", int(size * 0.45))
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor(255, 255, 255, 230))
        p.drawText(pix.rect(), Qt.AlignCenter, "S")
        p.end()
        pix.save(str(path), "PNG")
        return str(path)
    except Exception:
        return None

def ensure_icon(path: Path):
    try:
        if path.exists():
            return str(path)
        return generate_and_save_icon(path, size=128)
    except Exception:
        return None

# -----------------------------
# Autostart helper
# -----------------------------
def is_autostart_enabled():
    return AUTOSTART_FILE.exists()

def enable_autostart(script_path: Path):
    try:
        AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
        exec_cmd = f'python3 "{script_path}" --tray'
        desktop_content = f"""[Desktop Entry]
Type=Application
Exec={exec_cmd}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=SysWidget
Comment=Start SysWidget tray monitor
"""
        AUTOSTART_FILE.write_text(desktop_content, encoding="utf-8")
        AUTOSTART_FILE.chmod(0o644)
        return True
    except Exception:
        return False

def disable_autostart():
    try:
        if AUTOSTART_FILE.exists():
            AUTOSTART_FILE.unlink()
        return True
    except Exception:
        return False

# -----------------------------
# Themes
# -----------------------------
THEMES = ["dark", "compact", "card", "neon", "minimal", "gradient"]

def theme_stylesheet(theme):
    if theme == "compact":
        sheet = """
        QWidget { background-color: rgba(20,20,20,230); color:#cfcfcf; font-family: Sans-Serif; font-size:10px; border-radius:6px; }
        QLabel#title { font-size:12px; font-weight:600; }
        QProgressBar { height:8px; border:1px solid #2d2d2d; border-radius:4px; background:#171717; }
        QProgressBar::chunk { background: #66bb6a; }
        """
        return sheet, {"spacing":4, "opacity":1.0}
    if theme == "card":
        sheet = """
        QWidget { background: rgba(12,14,19,255); color:#e6eef6; font-family: Inter, Sans-Serif; font-size:13px; }
        QLabel#title { font-size:18px; font-weight:800; margin-bottom:6px; }
        QProgressBar { height:12px; border:1px solid #2b2f36; border-radius:6px; background:#0f1318; }
        QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #42a5f5, stop:1 #1e88e5); }
        """
        return sheet, {"spacing":10, "opacity":1.0}
    sheet = """
    QWidget { background-color: rgba(18,18,18,240); color: #ddd; font-family: Sans-Serif; font-size:12px; border-radius:8px; }
    QLabel#title { font-size:14px; font-weight:bold; }
    QProgressBar { height:12px; border:1px solid #333; border-radius:5px; text-align:center; background:#222; }
    QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #4caf50, stop:1 #8bc34a); }
    """
    return sheet, {"spacing":6, "opacity":1.0}

# -----------------------------
# Layout helpers
# -----------------------------
RESIZE_MARGIN = 8
def _clear_layout(layout):
    if layout is None:
        return
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            try:
                widget.deleteLater()
            except Exception:
                pass
        if child_layout is not None:
            _clear_layout(child_layout)
            try:
                child_layout.deleteLater()
            except Exception:
                pass

# -----------------------------
# Main widget
# -----------------------------
class SysWidget(QWidget):
    def __init__(self, settings, script_path: Path):
        # Use Qt.Tool to avoid taskbar entry by default (unless user opted in).
        base_flag = Qt.Tool
        if settings.get("show_in_taskbar", False):
            base_flag = Qt.Window
        flags = base_flag | Qt.FramelessWindowHint
        super().__init__(flags=flags)

        # IMPORTANT FIX: explicitly clear WindowStaysOnTopHint at initialization.
        # Some desktop environments treat Tool windows as always-on-top; explicitly clear the hint
        # so we do not force top-most behavior by default.
        self.setWindowFlag(Qt.WindowStaysOnTopHint, False)

        self.settings = settings
        self.script_path = script_path

        # If user had always_on_top True in saved settings we re-apply it here intentionally.
        if bool(self.settings.get("always_on_top", False)):
            self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

        # ensure icon and set app icon
        icon_path = ensure_icon(ICON_FILE)
        if icon_path:
            app_icon = QIcon(icon_path)
            self.setWindowIcon(app_icon)

        # apply theme
        sheet, params = theme_stylesheet(self.settings.get("theme", "dark"))
        self.setStyleSheet(sheet)
        self.layout_spacing = params.get("spacing", 6)

        # layout
        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(10,10,10,10)
        self.main_layout.setSpacing(self.layout_spacing)
        self.setLayout(self.main_layout)

        self.title = QLabel("System Monitor")
        self.title.setObjectName("title")
        self.main_layout.addWidget(self.title)

        # CPU templates
        self.cpu_orientation = self.settings.get("core_orientation", DEFAULT_SETTINGS["core_orientation"])
        self._create_cpu_horizontal_strip()
        self._create_cpu_vertical_stack()

        self.ram_label = None
        self.ram_bar = None

        self.gpu_container_layout = None
        self.gpu_widgets = []

        # create tray early
        self.tray = None
        self.create_tray_icon()

        # build content
        self._rebuild_main_content_from_settings(initial=True)

        # transparency & click-through
        self.transparent_mode = self.settings.get("transparent", False)
        if self.transparent_mode:
            self.setWindowOpacity(0.6)
        self.click_through = self.settings.get("click_through", False)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, self.click_through)

        # move/resize helpers
        self.drag_active = False
        self.drag_pos = QPoint(0,0)
        self.resize_active = False
        self.resize_dir = None
        self.orig_geom = QRect()

        # geometry + timer
        self._apply_saved_geometry()
        self.interval = self.settings.get("interval", DEFAULT_SETTINGS["interval"])
        self.timer = QTimer(); self.timer.setInterval(self.interval)
        self.timer.timeout.connect(self.update_stats)
        self.update_stats(); self.timer.start()

        # context menu
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    # UI rebuild
    def _rebuild_main_content_from_settings(self, initial=False):
        while self.main_layout.count() > 1:
            it = self.main_layout.takeAt(1)
            widget = it.widget()
            child_layout = it.layout()
            if widget is not None:
                try:
                    widget.deleteLater()
                except Exception:
                    pass
            if child_layout is not None:
                _clear_layout(child_layout)
                try:
                    child_layout.deleteLater()
                except Exception:
                    pass

        if self.settings.get("show_cpu", True):
            if self.cpu_orientation == "horizontal":
                self._create_cpu_horizontal_strip()
                self.main_layout.addWidget(self.cpu_strip_title)
                self.main_layout.addWidget(self.cpu_scroll)
            else:
                self._create_cpu_vertical_stack()
                self.main_layout.addWidget(self.cpu_stack_title)
                self.main_layout.addWidget(self.cpu_vstack_container)

        if self.settings.get("show_ram", True):
            self.ram_label = QLabel("RAM:")
            self.ram_bar = QProgressBar(); self.ram_bar.setRange(0,100)
            self.main_layout.addWidget(self.ram_label)
            self.main_layout.addWidget(self.ram_bar)
        else:
            self.ram_label = None
            self.ram_bar = None

        self.gpu_container = QWidget()
        self.gpu_container_layout = QVBoxLayout()
        self.gpu_container_layout.setContentsMargins(0,0,0,0)
        self.gpu_container_layout.setSpacing(6)
        self.gpu_container.setLayout(self.gpu_container_layout)
        self.main_layout.addWidget(self.gpu_container)
        self.gpu_widgets = []

        if not initial:
            self.update_stats()

    def _create_cpu_horizontal_strip(self):
        self.cpu_strip_title = QLabel("CPU (per-core):")
        self.cpu_scroll = QScrollArea(); self.cpu_scroll.setWidgetResizable(True)
        self.cpu_scroll.setFixedHeight(96); self.cpu_scroll.setFrameShape(QFrame.NoFrame)
        self.cpu_inner = QWidget()
        self.cpu_hbox = QHBoxLayout()
        self.cpu_hbox.setContentsMargins(2,2,2,2); self.cpu_hbox.setSpacing(6)
        self.cpu_inner.setLayout(self.cpu_hbox)
        self.cpu_scroll.setWidget(self.cpu_inner)
        self.core_widgets_h = []
        cores = psutil.cpu_count(logical=True) or 1
        for i in range(cores):
            self._add_core_widget_horizontal(i)

    def _add_core_widget_horizontal(self, idx):
        col = QWidget(); col_layout = QVBoxLayout()
        col_layout.setContentsMargins(0,0,0,0); col_layout.setSpacing(2)
        col.setLayout(col_layout)
        vbar = QProgressBar(); vbar.setOrientation(Qt.Vertical); vbar.setRange(0,100)
        vbar.setFixedSize(16,64)
        lbl = QLabel("0%"); lbl.setAlignment(Qt.AlignCenter); lbl.setFixedHeight(14)
        f = lbl.font(); f.setPointSize(max(8, f.pointSize()-1)); lbl.setFont(f)
        col_layout.addWidget(vbar, alignment=Qt.AlignCenter); col_layout.addWidget(lbl, alignment=Qt.AlignCenter)
        self.cpu_hbox.addWidget(col)
        self.core_widgets_h.append((vbar, lbl))

    def _create_cpu_vertical_stack(self):
        self.cpu_stack_title = QLabel("CPU (per-core):")
        self.cpu_vstack_container = QWidget()
        self.cpu_vbox = QVBoxLayout(); self.cpu_vbox.setContentsMargins(2,2,2,2); self.cpu_vbox.setSpacing(4)
        self.cpu_vstack_container.setLayout(self.cpu_vbox)
        self.core_widgets_v = []
        cores = psutil.cpu_count(logical=True) or 1
        for i in range(cores):
            lbl = QLabel(f"Core {i}:"); bar = QProgressBar(); bar.setRange(0,100)
            self.cpu_vbox.addWidget(lbl); self.cpu_vbox.addWidget(bar)
            self.core_widgets_v.append((lbl, bar))

    # Tray & menus
    def create_tray_icon(self):
        icon_path = ensure_icon(ICON_FILE)
        if icon_path:
            icon = QIcon(icon_path)
        else:
            icon = QIcon.fromTheme("preferences-system-monitor")
            if icon.isNull():
                icon = QIcon()
        self.tray = QSystemTrayIcon(icon, parent=None)
        menu = QMenu()

        show_act = QAction("Show", menu); hide_act = QAction("Hide", menu)
        toggle_trans = QAction("Toggle Transparency", menu); toggle_click = QAction("Toggle Click-Through", menu)
        toggle_core_orient = QAction("Toggle Core Orientation", menu)
        always_top_act = QAction("Always on Top", menu); always_top_act.setCheckable(True)
        always_top_act.setChecked(bool(self.settings.get("always_on_top", False)))
        always_top_act.triggered.connect(self._on_always_top_toggle)

        autostart_act = QAction("Run at Startup", menu); autostart_act.setCheckable(True)
        autostart_act.setChecked(bool(self.settings.get("autostart_enabled", False)) or is_autostart_enabled())
        autostart_act.triggered.connect(self._on_autostart_toggle)

        display_sub = menu.addMenu("Display")
        self.display_actions = {}
        for key, label in [
            ("show_cpu", "CPU per-core"),
            ("show_ram", "RAM"),
            ("show_gpu_core", "GPU core util"),
            ("show_gpu_vram", "GPU VRAM"),
            ("show_gpu_meta", "GPU meta (temp|fan|power)")
        ]:
            act = QAction(label, display_sub); act.setCheckable(True)
            act.setChecked(bool(self.settings.get(key, DEFAULT_SETTINGS.get(key, True))))
            act.setData(key); act.triggered.connect(self._on_display_toggle)
            display_sub.addAction(act)
            self.display_actions[key] = act

        theme_sub = menu.addMenu("Theme")
        for t in THEMES:
            a = QAction(t.capitalize(), theme_sub); a.setData(t); a.triggered.connect(self._on_theme_action)
            theme_sub.addAction(a)

        show_taskbar_act = QAction("Show in Taskbar", menu); show_taskbar_act.setCheckable(True)
        show_taskbar_act.setChecked(bool(self.settings.get("show_in_taskbar", False)))
        show_taskbar_act.triggered.connect(self._on_show_in_taskbar_toggle)

        exit_act = QAction("Exit", menu)

        show_act.triggered.connect(self.show_from_tray)
        hide_act.triggered.connect(self.hide)
        toggle_trans.triggered.connect(self._toggle_transparency)
        toggle_click.triggered.connect(self._toggle_click_through)
        toggle_core_orient.triggered.connect(self._toggle_core_orientation)
        exit_act.triggered.connect(self.exit_app)

        menu.addAction(show_act); menu.addAction(hide_act); menu.addSeparator()
        menu.addAction(toggle_trans); menu.addAction(toggle_click); menu.addAction(toggle_core_orient)
        menu.addAction(always_top_act); menu.addAction(autostart_act); menu.addAction(show_taskbar_act); menu.addSeparator()
        menu.addMenu(display_sub); menu.addSeparator()
        menu.addMenu(theme_sub); menu.addSeparator(); menu.addAction(exit_act)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.setVisible(True)

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.isVisible():
                self.hide()
            else:
                self.show_from_tray()

    def _on_autostart_toggle(self):
        enabled = not bool(self.settings.get("autostart_enabled", False))
        if enabled:
            ok = enable_autostart(self.script_path)
            if ok:
                self.settings["autostart_enabled"] = True
            else:
                self.settings["autostart_enabled"] = False
        else:
            ok = disable_autostart()
            if ok:
                self.settings["autostart_enabled"] = False
            else:
                self.settings["autostart_enabled"] = False
        save_settings(self.settings)
        try:
            if self.tray:
                self.tray.hide()
                self.create_tray_icon()
        except Exception:
            pass

    def _on_always_top_toggle(self):
        val = not bool(self.settings.get("always_on_top", False))
        self.settings["always_on_top"] = val
        save_settings(self.settings)
        # Set or clear the hint; only call show() to reapply flags if visible.
        self.setWindowFlag(Qt.WindowStaysOnTopHint, bool(val))
        if self.isVisible():
            # apply change. Only raise/activate if user explicitly enabled always-on-top.
            if val:
                self.show()
                # optionally bring to front when user explicitly wants it
                try:
                    self.raise_()
                    self.activateWindow()
                except Exception:
                    pass
            else:
                self.show()

    def _on_show_in_taskbar_toggle(self):
        val = not bool(self.settings.get("show_in_taskbar", False))
        self.settings["show_in_taskbar"] = val
        save_settings(self.settings)
        # Change base flags without changing the WindowStaysOnTopHint state we already manage.
        if val:
            self.setWindowFlag(Qt.Tool, False)
            self.setWindowFlag(Qt.Window, True)
        else:
            self.setWindowFlag(Qt.Window, False)
            self.setWindowFlag(Qt.Tool, True)
        # Ensure top hint is cleared unless always_on_top True
        if not bool(self.settings.get("always_on_top", False)):
            self.setWindowFlag(Qt.WindowStaysOnTopHint, False)
        else:
            self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        if self.isVisible():
            self.show()

    def _on_display_toggle(self):
        act = self.sender()
        if not act:
            return
        key = act.data()
        if key is None:
            return
        self.settings[key] = bool(act.isChecked())
        save_settings(self.settings)
        self._rebuild_main_content_from_settings()

    def _on_theme_action(self):
        act = self.sender()
        if not act:
            return
        t = act.data()
        if t and t in THEMES:
            sheet, params = theme_stylesheet(t)
            self.setStyleSheet(sheet)
            self.main_layout.setSpacing(params.get("spacing", 6))
            self.setWindowOpacity(params.get("opacity", 1.0))
            self.settings["theme"] = t
            save_settings(self.settings)

    def show_context_menu(self, pos):
        menu = QMenu(self)
        t1 = menu.addAction("Toggle Transparency"); t2 = menu.addAction("Toggle Click-Through")
        t3 = menu.addAction("Toggle Core Orientation"); t4 = menu.addAction("Always on Top")
        t4.setCheckable(True); t4.setChecked(bool(self.settings.get("always_on_top", False)))
        t5 = menu.addAction("Run at Startup"); t5.setCheckable(True); t5.setChecked(bool(self.settings.get("autostart_enabled", False)) or is_autostart_enabled())
        dmenu = menu.addMenu("Display")
        for key, label in [
            ("show_cpu", "CPU per-core"),
            ("show_ram", "RAM"),
            ("show_gpu_core", "GPU core util"),
            ("show_gpu_vram", "GPU VRAM"),
            ("show_gpu_meta", "GPU meta (temp|fan|power)")
        ]:
            a = QAction(label, dmenu); a.setCheckable(True)
            a.setChecked(bool(self.settings.get(key, DEFAULT_SETTINGS.get(key, True))))
            a.setData(key); a.triggered.connect(self._on_display_toggle)
            dmenu.addAction(a)
        theme_menu = menu.addMenu("Theme")
        for t in THEMES:
            a = QAction(t.capitalize(), theme_menu); a.setData(t); a.triggered.connect(self._on_theme_action)
            theme_menu.addAction(a)
        exit_action = menu.addAction("Exit")
        action = menu.exec_(self.mapToGlobal(pos))
        if action == t1:
            self._toggle_transparency()
        elif action == t2:
            self._toggle_click_through()
        elif action == t3:
            self._toggle_core_orientation()
        elif action == t4:
            self._on_always_top_toggle()
        elif action == t5:
            self._on_autostart_toggle()
        elif action == exit_action:
            self.exit_app()

    def _toggle_transparency(self):
        self.transparent_mode = not self.transparent_mode
        self.setWindowOpacity(0.6 if self.transparent_mode else 1.0)
        self.settings["transparent"] = self.transparent_mode
        save_settings(self.settings)

    def _toggle_click_through(self):
        self.click_through = not self.click_through
        self.setAttribute(Qt.WA_TransparentForMouseEvents, self.click_through)
        self.settings["click_through"] = self.click_through
        save_settings(self.settings)

    def _toggle_core_orientation(self):
        new = "vertical" if self.cpu_orientation == "horizontal" else "horizontal"
        self.cpu_orientation = new
        self.settings["core_orientation"] = new
        save_settings(self.settings)
        if self.settings.get("show_cpu", True):
            self._rebuild_main_content_from_settings()

    def show_from_tray(self):
        # When restoring from tray, do not force window to front unless always_on_top is enabled.
        self.show()
        if bool(self.settings.get("always_on_top", False)):
            # re-apply top hint if saved true and bring forward
            self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
            self.show()
            try:
                self.raise_()
                self.activateWindow()
            except Exception:
                pass
        else:
            # Ensure top hint is cleared so it stays behind other windows
            self.setWindowFlag(Qt.WindowStaysOnTopHint, False)
            # Do not call raise_() or activateWindow() — let WM decide stacking
            self.show()

    def exit_app(self):
        self._save_geometry_to_settings()
        for k in ["show_cpu","show_ram","show_gpu_core","show_gpu_vram","show_gpu_meta"]:
            self.settings[k] = bool(self.settings.get(k, DEFAULT_SETTINGS[k]))
        self.settings["theme"] = self.settings.get("theme", DEFAULT_SETTINGS["theme"])
        self.settings["transparent"] = self.transparent_mode
        self.settings["click_through"] = self.click_through
        self.settings["core_orientation"] = self.cpu_orientation
        save_settings(self.settings)
        if self.tray:
            self.tray.hide()
        QApplication.quit()

    # geometry persistence
    def _apply_saved_geometry(self):
        screen_idx = int(self.settings.get("screen", 0))
        x = int(self.settings.get("x", 0)); y = int(self.settings.get("y", 0))
        w = int(self.settings.get("width", DEFAULT_SETTINGS["width"])); h = int(self.settings.get("height", DEFAULT_SETTINGS["height"]))
        self.resize(w, h)
        app = QApplication.instance()
        if app:
            screens = app.screens()
            if 0 <= screen_idx < len(screens):
                geo = screens[screen_idx].geometry()
                self.move(geo.x() + x, geo.y() + y)
            else:
                self.move(x, y)
        else:
            self.move(x, y)

    def _save_geometry_to_settings(self):
        geom = self.geometry()
        app = QApplication.instance()
        screen_idx = 0
        if app:
            for i, s in enumerate(app.screens()):
                if s.geometry().contains(geom.topLeft()):
                    screen_idx = i
                    break
        self.settings["screen"] = int(screen_idx)
        if app:
            geo = app.screens()[screen_idx].geometry()
            rel_x = geom.x() - geo.x(); rel_y = geom.y() - geo.y()
            self.settings["x"] = int(rel_x); self.settings["y"] = int(rel_y)
        else:
            self.settings["x"] = int(geom.x()); self.settings["y"] = int(geom.y())
        self.settings["width"] = int(geom.width()); self.settings["height"] = int(geom.height())
        save_settings(self.settings)

    # move & resize
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.pos(); rect = self.rect()
            dir = self._detect_resize_direction(pos, rect)
            if dir:
                self.resize_active = True; self.resize_dir = dir; self.orig_geom = self.geometry(); self.drag_pos = event.globalPos()
                event.accept(); return
            self.drag_active = True; self.drag_pos = event.globalPos() - self.frameGeometry().topLeft(); event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.pos(); rect = self.rect()
        if self.resize_active:
            self._perform_resize(event.globalPos()); event.accept(); return
        if self.drag_active:
            newpos = event.globalPos() - self.drag_pos; self.move(newpos); event.accept(); return
        dir = self._detect_resize_direction(pos, rect)
        if dir:
            cursor = self._cursor_for_direction(dir); self.setCursor(cursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.drag_active:
                self.drag_active = False; self._save_geometry_to_settings()
            if self.resize_active:
                self.resize_active = False; self.resize_dir = None; self._save_geometry_to_settings()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _detect_resize_direction(self, pos, rect):
        x, y, w, h = pos.x(), pos.y(), rect.width(), rect.height()
        left = x <= RESIZE_MARGIN; right = x >= w - RESIZE_MARGIN
        top = y <= RESIZE_MARGIN; bottom = y >= h - RESIZE_MARGIN
        if top and left: return "top-left"
        if top and right: return "top-right"
        if bottom and left: return "bottom-left"
        if bottom and right: return "bottom-right"
        if left: return "left"
        if right: return "right"
        if top: return "top"
        if bottom: return "bottom"
        return None

    def _cursor_for_direction(self, dir):
        mapping = {"left": Qt.SizeHorCursor, "right": Qt.SizeHorCursor, "top": Qt.SizeVerCursor, "bottom": Qt.SizeVerCursor,
                   "top-left": Qt.SizeFDiagCursor, "bottom-right": Qt.SizeFDiagCursor, "top-right": Qt.SizeBDiagCursor, "bottom-left": Qt.SizeBDiagCursor}
        return QCursor(mapping.get(dir, Qt.ArrowCursor))

    def _perform_resize(self, global_pos):
        dx = global_pos.x() - self.drag_pos.x(); dy = global_pos.y() - self.drag_pos.y()
        g = QRect(self.orig_geom); min_w = 160; min_h = 120
        if "left" in self.resize_dir:
            new_x = g.x() + dx; new_w = g.width() - dx
            if new_w >= min_w: g.setX(new_x); g.setWidth(new_w)
        if "right" in self.resize_dir:
            new_w = g.width() + dx
            if new_w >= min_w: g.setWidth(new_w)
        if "top" in self.resize_dir:
            new_y = g.y() + dy; new_h = g.height() - dy
            if new_h >= min_h: g.setY(new_y); g.setHeight(new_h)
        if "bottom" in self.resize_dir:
            new_h = g.height() + dy
            if new_h >= min_h: g.setHeight(new_h)
        self.setGeometry(g)

    # update loop
    def update_stats(self):
        try:
            try:
                per_core = psutil.cpu_percent(interval=None, percpu=True)
            except KeyboardInterrupt:
                QApplication.quit(); return
            except Exception:
                per_core = []

            if self.settings.get("show_cpu", True):
                if self.cpu_orientation == "horizontal":
                    if len(per_core) != len(self.core_widgets_h):
                        _clear_layout(self.cpu_hbox); self.core_widgets_h = []
                        for i in range(len(per_core)): self._add_core_widget_horizontal(i)
                    for i, val in enumerate(per_core):
                        if i < len(self.core_widgets_h):
                            vbar, lbl = self.core_widgets_h[i]; vbar.setValue(int(val)); lbl.setText(f"{int(val)}%")
                else:
                    if len(per_core) != len(self.core_widgets_v):
                        _clear_layout(self.cpu_vbox); self.core_widgets_v = []
                        for i in range(len(per_core)):
                            lbl = QLabel(f"Core {i}:"); bar = QProgressBar(); bar.setRange(0,100)
                            self.cpu_vbox.addWidget(lbl); self.cpu_vbox.addWidget(bar); self.core_widgets_v.append((lbl, bar))
                    for i, val in enumerate(per_core):
                        if i < len(self.core_widgets_v): lbl, bar = self.core_widgets_v[i]; lbl.setText(f"Core {i}: {val:.1f}%"); bar.setValue(int(val))

            if self.settings.get("show_ram", True) and self.ram_bar is not None and self.ram_label is not None:
                try:
                    mem = psutil.virtual_memory()
                    used_mib = mem.used // (1024**2); total_mib = mem.total // (1024**2)
                    self.ram_bar.setValue(int(mem.percent))
                    self.ram_label.setText(f"RAM: {used_mib} MiB / {total_mib} MiB ({mem.percent:.1f}%)")
                except Exception:
                    self.ram_label.setText("RAM: N/A")

            try:
                gpus = query_nvidia_smi()
            except KeyboardInterrupt:
                QApplication.quit(); return
            except Exception:
                gpus = []

            need_rebuild_gpu = (len(gpus) != len(self.gpu_widgets)) or (self.gpu_container_layout is None) or (self.gpu_container_layout.count() == 0)
            if need_rebuild_gpu:
                if self.gpu_container_layout is not None: _clear_layout(self.gpu_container_layout)
                self.gpu_widgets = []
                if not gpus:
                    lbl = QLabel("GPU: N/A (nvidia-smi not found or returned no GPUs)")
                    if self.gpu_container_layout is not None: self.gpu_container_layout.addWidget(lbl)
                    self.gpu_widgets.append((lbl,))
                else:
                    for g in gpus:
                        title = QLabel(f"{g.get('name','GPU')} (GPU {g.get('index')})")
                        core_lbl = QLabel("GPU Core Util:"); core_bar = QProgressBar(); core_bar.setRange(0,100)
                        vram_text = QLabel("VRAM: N/A"); vram_bar = QProgressBar(); vram_bar.setRange(0,100)
                        meta = QLabel("")
                        if self.gpu_container_layout is not None:
                            self.gpu_container_layout.addWidget(title)
                            if self.settings.get("show_gpu_core", True): self.gpu_container_layout.addWidget(core_lbl); self.gpu_container_layout.addWidget(core_bar)
                            if self.settings.get("show_gpu_vram", True): self.gpu_container_layout.addWidget(vram_text); self.gpu_container_layout.addWidget(vram_bar)
                            if self.settings.get("show_gpu_meta", True): self.gpu_container_layout.addWidget(meta)
                        self.gpu_widgets.append((title, core_lbl, core_bar, vram_text, vram_bar, meta))
            if gpus and self.gpu_widgets:
                for g, widgets in zip(gpus, self.gpu_widgets):
                    _, core_lbl, core_bar, vram_text, vram_bar, meta = widgets
                    util = g.get("util"); mem_used = g.get("mem_used_mb"); mem_total = g.get("mem_total_mb")
                    mem_pct = g.get("mem_percent"); temp = g.get("temp"); fan = g.get("fan"); power = g.get("power_w")
                    if self.settings.get("show_gpu_core", True):
                        core_bar.setValue(int(util) if util is not None else 0)
                        core_lbl.setText(f"GPU Core Util: {util}%" if util is not None else "GPU Core Util: N/A")
                    if self.settings.get("show_gpu_vram", True):
                        if mem_used is not None and mem_total is not None:
                            pct_txt = f"{mem_pct:.1f}%" if mem_pct is not None else "N/A"
                            vram_text.setText(f"VRAM: {mem_used:.0f} MiB / {mem_total:.0f} MiB ({pct_txt})")
                        else:
                            vram_text.setText("VRAM: N/A")
                        vram_bar.setValue(int(mem_pct) if mem_pct is not None else 0)
                    if self.settings.get("show_gpu_meta", True):
                        parts = []
                        parts.append(f"T:{temp}°C" if temp is not None else "T:N/A")
                        parts.append(f"Fan:{fan}%" if fan is not None else "Fan:N/A")
                        parts.append(f"P:{power:.1f}W" if power is not None else "P:N/A")
                        meta.setText(" | ".join(parts))

        except Exception:
            return

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self._save_geometry_to_settings()

# -----------------------------
# CLI & main
# -----------------------------
def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--tray", action="store_true", help="Start minimized to tray")
    p.add_argument("--force", action="store_true", help="Force CLI to override saved config")
    p.add_argument("--screen", type=int, help="screen index (0-based)")
    p.add_argument("--x", type=int, help="x offset")
    p.add_argument("--y", type=int, help="y offset")
    p.add_argument("--width", type=int, help="widget width")
    p.add_argument("--height", type=int, help="widget height")
    p.add_argument("--interval", type=int, help="update interval in ms")
    p.add_argument("--theme", type=str, help="theme name")
    return p.parse_args()

def main():
    script_path = Path(__file__).resolve()

    saved_present = CONFIG_FILE.exists()
    saved = load_settings()
    args = parse_args()

    if (not saved_present) or args.force:
        if args.screen is not None: saved["screen"] = int(args.screen)
        if args.x is not None: saved["x"] = int(args.x)
        if args.y is not None: saved["y"] = int(args.y)
        if args.width is not None: saved["width"] = int(args.width)
        if args.height is not None: saved["height"] = int(args.height)
        if args.interval is not None: saved["interval"] = int(args.interval)
        if args.theme is not None and args.theme in THEMES: saved["theme"] = args.theme
        save_settings(saved)

    if args.tray:
        saved["start_minimized"] = True
        save_settings(saved)

    for k, v in DEFAULT_SETTINGS.items():
        if k not in saved: saved[k] = v

    if is_autostart_enabled():
        saved["autostart_enabled"] = True

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv)
    signal.signal(signal.SIGINT, lambda sig, frame: QApplication.quit())

    ensure_icon(ICON_FILE)
    if ICON_FILE.exists():
        app.setWindowIcon(QIcon(str(ICON_FILE)))

    w = SysWidget(saved, script_path)

    if saved.get("start_minimized", False):
        w.hide()
    else:
        w.show()
    w._apply_saved_geometry()

    g = query_nvidia_smi()
    if g:
        print(f"GPU backend: nvidia-smi. GPUs detected: {len(g)}")
    else:
        print("GPU backend: nvidia-smi returned no GPUs or nvidia-smi not found.")

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
