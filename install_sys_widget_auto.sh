#!/usr/bin/env bash
set -euo pipefail

# install_sys_widget_auto.sh
# Installs dependencies for the SysWidget python script, creates autostart by default,
# and starts the widget immediately (visible). Supports --no-autostart and --no-run.
#
# Place this installer in the same directory as sys_widget_final_with_embedded_icon.py
# or edit PY_SCRIPT variable below to match your script name.

PY_SCRIPT="sys_widget_final_with_embedded_icon.py"   # <-- change if your filename differs
LAUNCH_ARGS=""   # empty = show by default; use "--tray" if you prefer start minimized
USE_PYTHON="python3"

# Flags
NO_AUTOSTART=0
NO_RUN=0
INSTALL_LOCAL=0  # set to 1 to copy script to ~/.local/bin (optional)

# parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-autostart) NO_AUTOSTART=1; shift ;;
    --no-run) NO_RUN=1; shift ;;
    --install-local) INSTALL_LOCAL=1; shift ;;
    --help|-h) echo "Usage: $0 [--no-autostart] [--no-run] [--install-local]"; exit 0 ;;
    *) echo "Unknown arg: $1"; echo "Use --help for usage"; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_PATH="${SCRIPT_DIR}/${PY_SCRIPT}"

if [ ! -f "${SCRIPT_PATH}" ]; then
  echo "Error: ${PY_SCRIPT} not found in ${SCRIPT_DIR}."
  echo "Place the Python widget file in this directory or edit PY_SCRIPT in this installer."
  exit 1
fi

echo "Installer running for script: ${SCRIPT_PATH}"
echo

# 1) System packages (Debian/Ubuntu via apt)
if command -v apt >/dev/null 2>&1; then
  echo "Detected apt. Installing system packages (may prompt for sudo)..."
  sudo apt update
  sudo apt install -y python3 python3-pip python3-pyqt5 python3-pyqt5.qtwidgets || {
    echo "Warning: apt install failed or partial. Please ensure python3 and PyQt5 are installed."
  }
else
  echo "apt not found. Please ensure Python3 and PyQt5 are installed for your distribution."
fi

# 2) Python packages to user site
if ! command -v "${USE_PYTHON}" >/dev/null 2>&1; then
  echo "Error: ${USE_PYTHON} not found. Install Python3 and re-run."
  exit 1
fi

echo "Installing python packages to user site: psutil"
"${USE_PYTHON}" -m pip install --user --upgrade pip setuptools wheel
"${USE_PYTHON}" -m pip install --user --upgrade psutil

echo "Python packages installed to user site."

# 3) Optional: copy to ~/.local/bin for convenience
if [ "${INSTALL_LOCAL}" -eq 1 ]; then
  echo "Installing a local copy to ~/.local/bin ..."
  mkdir -p "${HOME}/.local/bin"
  cp -f "${SCRIPT_PATH}" "${HOME}/.local/bin/sys_widget.py"
  chmod +x "${HOME}/.local/bin/sys_widget.py"
  LAUNCH_PATH="${HOME}/.local/bin/sys_widget.py"
  echo "Local copy created at ${LAUNCH_PATH}"
else
  LAUNCH_PATH="${SCRIPT_PATH}"
fi

# 4) Autostart (DEFAULT: enabled) unless --no-autostart passed
AUTOSTART_DIR="${HOME}/.config/autostart"
AUTOSTART_FILE="${AUTOSTART_DIR}/sys_widget.desktop"

if [ "${NO_AUTOSTART}" -eq 0 ]; then
  echo "Creating autostart entry so the widget runs on login..."
  mkdir -p "${AUTOSTART_DIR}"
  # Choose the launch command; don't use --tray here because user wanted it shown by default.
  EXEC_CMD="${USE_PYTHON} \"${LAUNCH_PATH}\" ${LAUNCH_ARGS}"
  cat > "${AUTOSTART_FILE}" <<EOF
[Desktop Entry]
Type=Application
Exec=${EXEC_CMD}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=SysWidget
Comment=Start SysWidget tray monitor
EOF
  chmod 644 "${AUTOSTART_FILE}"
  echo "Autostart file created: ${AUTOSTART_FILE}"
else
  echo "Skipped creating autostart (user requested --no-autostart)."
fi

# 5) Launch now (unless --no-run)
LOG_DIR="${HOME}/.config/sys_widget"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/sys_widget.log"

if [ "${NO_RUN}" -eq 0 ]; then
  echo "Starting widget now (visible by default). Logs: ${LOG_FILE}"
  # Use nohup to detach; run in background
  nohup bash -c "${USE_PYTHON} \"${LAUNCH_PATH}\" ${LAUNCH_ARGS} >> \"${LOG_FILE}\" 2>&1 &" >/dev/null 2>&1 || true
  sleep 1
  echo "Widget started (check ${LOG_FILE} for output)."
else
  echo "Installation completed; not starting the widget now (user requested --no-run)."
fi

cat <<EOF

Installation complete.

Autostart behavior:
 - By default the installer created ${AUTOSTART_FILE} so the widget will run on next login
   and show by default.
 - If you ran the installer with --no-autostart the autostart entry was NOT created.

Change autostart later:
 - Use the widget tray menu -> "Run at Startup" to toggle autostart on/off (this will create/remove ${AUTOSTART_FILE}).
 - Or remove the file manually:
     rm -f "${AUTOSTART_FILE}"

To run the program manually:
 - ${USE_PYTHON} "${LAUNCH_PATH}"
 - or run the copy in ~/.local/bin if you used --install-local:
     python3 "${HOME}/.local/bin/sys_widget.py"

To uninstall autostart:
 - rm -f "${AUTOSTART_FILE}"

To stop a running instance:
 - pkill -f "${PY_SCRIPT}"    # caution: will kill processes matching the name

If you prefer a systemd user service instead of the .desktop autostart file, I can provide that variant.

EOF

exit 0
