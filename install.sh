#!/usr/bin/env bash
set -e

# Detect OS family (Debian/Ubuntu vs RHEL/CentOS)
if command -v apt-get >/dev/null 2>&1; then
  echo "[INFO] Detected Debian/Ubuntu system."
  sudo apt-get update
  sudo apt-get install -y \
    python3-gi \
    libgtk-3-bin \
    gir1.2-ayatanaappindicator3-0.1 \
    libayatana-appindicator3-dev \
    dbus libdbus-glib-1-dev \
    libgirepository1.0-dev libgirepository-2.0-dev gir1.2-glib-2.0 \
    gobject-introspection
elif command -v yum >/dev/null 2>&1 || command -v dnf >/dev/null 2>&1; then
  echo "[INFO] Detected RHEL/CentOS/Fedora system."
  sudo yum install -y \
    python3-gobject \
    cairo cairo-devel \
    libffi-devel glib2-devel \
    dbus dbus-glib-devel \
    gobject-introspection gobject-introspection-devel \
    libjpeg-turbo libjpeg-turbo-devel \
    gnome-extensions
else
  echo "[ERROR] Unsupported distribution. Install dependencies manually."
  exit 1
fi

# Clone repository
INSTALL_DIR="$HOME/.time_awareness/src"
if [ -d "$INSTALL_DIR" ]; then
  echo "[INFO] Updating existing installation at $INSTALL_DIR"
  cd "$INSTALL_DIR"
  git pull
else
  echo "[INFO] Cloning repository to $INSTALL_DIR"
  git clone https://github.com/AndersFB/Time-Awareness.git "$INSTALL_DIR"
  cd "$INSTALL_DIR"

  if command -v yum >/dev/null 2>&1 || command -v dnf >/dev/null 2>&1; then
    echo "[INFO] Installing appindicator GNOME extension $INSTALL_DIR/lib/appindicatorsupportrgcjonas.gmail.com.v60.shell-extension.zip"
    gnome-extensions install "$INSTALL_DIR/lib/appindicatorsupportrgcjonas.gmail.com.v60.shell-extension.zip"
    gnome-extensions enable "appindicatorsupport@rgcjonas.gmail.com"
  fi

  # Setup Python virtual environment
  echo "[INFO] Creating Python virtual environment in .venv"
  python3 -m venv .venv
fi

source .venv/bin/activate

echo "[INFO] Installing Python dependencies"
pip install --upgrade pip

if ! dpkg -s libgirepository-2.0-dev &>/dev/null; then
  echo "[NOTICE] libgirepository1.0-dev was installed. Pinning PyGObject to 3.50.1."
  # Replace existing pygobject entry
  sed 's/^pygobject.*/pygobject==3.50.1/' requirements.txt > requirements_pinned.txt
  pip install -U -r requirements_pinned.txt
else
  pip install -U -r requirements.txt
fi

AUTOSTART_DIR="$HOME/.config/autostart"

if [ ! -f "$AUTOSTART_DIR/time_awareness.desktop" ]; then
  echo "[INFO] Creating autostart entry"
  mkdir -p "$AUTOSTART_DIR"
  cat > "$AUTOSTART_DIR/time_awareness.desktop" <<EOL
[Desktop Entry]
Type=Application
Exec=$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/app.py
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=Time Awareness
Comment=Track active usage time
EOL
  chmod +x "$AUTOSTART_DIR/time_awareness.desktop"
fi

if [ ! -f "$HOME/.local/share/applications/time_awareness.desktop" ]; then
  ln -sf "$AUTOSTART_DIR/time_awareness.desktop" "$HOME/.local/share/applications/time_awareness.desktop"
fi

echo "[INFO] Installation completed. Starting app."
gtk-launch time_awareness

echo "[INFO] The app will start automatically on next login."
