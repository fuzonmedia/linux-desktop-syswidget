# linux-desktop-syswidget – A Customizable Desktop System Monitor for Linux

SysWidget is a modern, floating, borderless, theme-able desktop widget for Linux systems built using **Python 3 + PyQt5**.

It displays **real-time CPU usage**, **RAM usage**, **per-core utilization**, and **NVIDIA GPU metrics** including:

- GPU utilization
- VRAM usage
- Temperature
- Fan speed
- Power draw

SysWidget is lightweight, visually flexible, always resizable, and can live either on the desktop background or in the system tray — **without appearing in the taskbar**.

---

## Features

### ✔ Real-Time System Metrics
- Per-core CPU usage (vertical or horizontal layout)
- RAM usage (absolute + percentage)
- NVIDIA GPU metrics via `nvidia-smi`

### ✔ Fully Customizable UI
- Six themes: Dark, Compact, Card, Neon, Minimal, Gradient
- Adjustable transparency
- Click-through mode
- Resizable by dragging edges/corners
- Movable by dragging anywhere
- Remove or add modules from right-click menu

### ✔ Persistent Config System
Automatically saves:
- Widget position  
- Size  
- Visible metrics  
- Theme  
- Orientation  
- Transparency & click-through  
- Always-on-top mode  
- Taskbar visibility  

No “Save” button required — all changes are remembered.

### ✔ System Tray Integration
- Show / Hide widget  
- Toggle autostart  
- Toggle transparency  
- Toggle click-through  
- Switch themes  
- Enable/Disable Always on Top  
- Exit application  

### ✔ Autostart Support
The installer script automatically:
- Installs dependencies  
- Creates autostart entry (`~/.config/autostart/sys_widget.desktop`)  
- Starts the widget immediately  

Users can disable autostart through the tray menu.

### ✔ GPU Monitoring Without Extra Python Packages
No `pynvml` required — uses `nvidia-smi` for excellent compatibility.

---

## Installation

Clone the repo:

```bash
git clone https://github.com/fuzonmedia/linux-desktop-syswidget.git
cd syswidget
```

Run installer:

```bash
chmod +x install_sys_widget.sh
./install_sys_widget.sh
```

Options:

| Flag | Description |
|------|-------------|
| `--no-autostart` | Install but do not run at system startup |
| `--no-run` | Do not start widget immediately after installation |
| `--install-local` | Copy tool to `~/.local/bin` |

---

## Running Manually

```bash
python3 sys_widget_final_with_embedded_icon.py
```

To start minimized to tray:

```bash
python3 sys_widget_final_with_embedded_icon.py --tray
```

---

## Configuration Storage

SysWidget stores settings automatically in:

```
~/.config/sys_widget/widget_config.json
```

No manual editing is necessary — but power users may tweak values.

---

## Autostart File

Located at:

```
~/.config/autostart/sys_widget.desktop
```

Remove it manually to disable autostart:

```bash
rm ~/.config/autostart/sys_widget.desktop
```

---

## Uninstallation

```bash
rm -f ~/.config/autostart/sys_widget.desktop
rm -rf ~/.config/sys_widget
pkill -f sys_widget_final_with_embedded_icon.py
```

---
<img width="773" height="1365" alt="image" src="https://github.com/user-attachments/assets/7e749e20-86c8-4620-92f5-36755b1e155c" />
<img width="764" height="1362" alt="image" src="https://github.com/user-attachments/assets/f03c6d18-d1bc-4305-afad-caa9f8a4c5ad" />









## Roadmap

- Additional themes  
- KDE/Wayland-optimized stacking behavior  
- Optional AMD GPU support (`rocminfo` parser)  
- Plugin system for adding custom metrics  

---

## License

MIT License — free for personal and commercial use.

---

## Credits

Designed & developed by **Niladri Dey**.
