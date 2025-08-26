#!/usr/bin/env bash
set -e

# Detect OS family (Debian/Ubuntu vs RHEL/CentOS)
if command -v apt-get >/dev/null 2>&1; then
    echo "[INFO] Detected Debian/Ubuntu system."
    sudo apt-get update
    sudo apt-get install -y \
        python3-gi \
        gir1.2-ayatanaappindicator3-0.1 \
        libayatana-appindicator3-dev \
        dbus \
        libdbus-glib-1-dev \
        fonts-dejavu-core \
        git \
        python3-venv
elif command -v yum >/dev/null 2>&1 || command -v dnf >/dev/null 2>&1; then
    echo "[INFO] Detected RHEL/CentOS/Fedora system."
    sudo yum install -y \
        python3 \
        python3-gobject \
        dbus \
        dbus-glib-devel \
        git \
        dejavu-sans-fonts \
        gnome-extensions
else
    echo "[ERROR] Unsupported distribution. Install dependencies manually."
    exit 1
fi

# Check if running GNOME
if [[ "$XDG_CURRENT_DESKTOP" == *"GNOME"* ]]; then
    echo "[NOTICE] GNOME desktop detected."
    echo "GNOME does NOT show tray icons by default."
    echo "To enable tray icons, the 'AppIndicator Support' extension will be installed:"
    gnome-extensions install "appindicator@extensions.gnome.org"
fi

# Clone repository
INSTALL_DIR="$HOME/.time_awareness"
if [ -d "$INSTALL_DIR" ]; then
    echo "[INFO] Removing existing installation at $INSTALL_DIR"
    rm -rf "$INSTALL_DIR"
fi

echo "[INFO] Cloning repository to $INSTALL_DIR"
git clone https://github.com/AndersFB/Time-Awareness.git "$INSTALL_DIR"
cd "$INSTALL_DIR"

# Setup Python virtual environment
echo "[INFO] Creating Python virtual environment in .venv"
python3 -m venv .venv
source .venv/bin/activate

echo "[INFO] Installing Python dependencies"
pip install --upgrade pip
pip install -r requirements.txt

# Create autostart entry
AUTOSTART_DIR="$HOME/.config/autostart"
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

echo "[INFO] Installation completed."
echo "[INFO] The app will start automatically on next login."
