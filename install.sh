#!/usr/bin/env bash
set -e

function ask_proceed() {
  echo -n "Proceed? [Y/n]: "
  # Flush output to ensure prompt is visible
  fflush() { true; } 2>/dev/null || true
  read -r answer < /dev/tty
  if [[ "$answer" =~ ^[Nn]$ ]]; then
    echo "Aborted."
    exit 1
  fi
}

function progress_bar() {
  local total=$1
  local current=0
  while [ $current -lt $total ]; do
    echo -n "."
    sleep 0.2
    current=$((current + 1))
  done
  echo " done"
}

echo "Welcome to the Time Awareness installer."
echo "This script will install required system and Python dependencies, clone the repository, and set up autostart."
echo
ask_proceed

# Detect OS family (Debian/Ubuntu vs RHEL/CentOS)
if command -v apt-get >/dev/null 2>&1; then
  echo "Step 1: Update package list (requires sudo, you may be asked for your password)."
  ask_proceed
  sudo apt-get update -qq
  echo "Step 2: Install required packages (requires sudo, you may be asked for your password)."
  ask_proceed
  PKGS=(
    python3-gi
    libgtk-3-bin
    gir1.2-ayatanaappindicator3-0.1
    libayatana-appindicator3-dev
    dbus
    libdbus-glib-1-dev
    libgirepository1.0-dev
    libgirepository-2.0-dev
    gir1.2-glib-2.0
    gobject-introspection
  )
  for pkg in "${PKGS[@]}"; do
    echo -n "Installing $pkg "
    sudo apt-get install -y "$pkg" >/dev/null 2>&1 && progress_bar 10
  done
elif command -v yum >/dev/null 2>&1 || command -v dnf >/dev/null 2>&1; then
  echo "Step 1: Install required packages (requires sudo, you may be asked for your password)."
  ask_proceed
  PKGS=(
    python3-gobject
    cairo
    cairo-devel
    libffi-devel
    glib2-devel
    dbus
    dbus-glib-devel
    gobject-introspection
    gobject-introspection-devel
    libjpeg-turbo
    libjpeg-turbo-devel
    gnome-extensions
  )
  for pkg in "${PKGS[@]}"; do
    echo -n "Installing $pkg "
    sudo yum install -y "$pkg" >/dev/null 2>&1 && progress_bar 10
  done
else
  echo "[ERROR] Unsupported distribution. Install dependencies manually."
  exit 1
fi

echo "Step 3: Clone or update the Time Awareness repository."
ask_proceed
INSTALL_DIR="$HOME/.time_awareness/src"
if [ -d "$INSTALL_DIR" ]; then
  echo "Updating existing installation at $INSTALL_DIR"
  cd "$INSTALL_DIR"
  git pull >/dev/null 2>&1 && progress_bar 10
else
  echo "Cloning repository to $INSTALL_DIR"
  git clone https://github.com/AndersFB/Time-Awareness.git "$INSTALL_DIR" >/dev/null 2>&1 && progress_bar 10
  cd "$INSTALL_DIR"

  if command -v yum >/dev/null 2>&1 || command -v dnf >/dev/null 2>&1; then
    echo "Step 3.1: Install appindicator GNOME extension."
    ask_proceed
    gnome-extensions install "$INSTALL_DIR/lib/appindicatorsupportrgcjonas.gmail.com.v60.shell-extension.zip" >/dev/null 2>&1 && progress_bar 10
    gnome-extensions enable "appindicatorsupport@rgcjonas.gmail.com" >/dev/null 2>&1 && progress_bar 5
  fi

  echo "Step 3.2: Create Python virtual environment."
  ask_proceed
  python3 -m venv .venv >/dev/null 2>&1 && progress_bar 10
fi

echo "Step 4: Activate Python virtual environment and install Python dependencies."
ask_proceed
source .venv/bin/activate
pip install --upgrade pip >/dev/null 2>&1 && progress_bar 5

if ! dpkg -s libgirepository-2.0-dev &>/dev/null; then
  echo "Pinning PyGObject to 3.50.1 due to missing libgirepository-2.0-dev."
  sed 's/^pygobject.*/pygobject==3.50.1/' requirements.txt > requirements_pinned.txt
  pip install -U -r requirements_pinned.txt >/dev/null 2>&1 && progress_bar 10
else
  pip install -U -r requirements.txt >/dev/null 2>&1 && progress_bar 10
fi

AUTOSTART_DIR="$HOME/.config/autostart"
AUTOSTART_DESKTOP_ENTRY="$AUTOSTART_DIR/time_awareness.desktop"

echo "Step 5: Create autostart entry."
ask_proceed
if [ ! -f "$AUTOSTART_DESKTOP_ENTRY" ]; then
  mkdir -p "$AUTOSTART_DIR"
  cat > "$AUTOSTART_DESKTOP_ENTRY" <<EOL
[Desktop Entry]
Type=Application
Exec=$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/app.py
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=Time Awareness
Comment=Track active usage time
EOL
  chmod +x "$AUTOSTART_DESKTOP_ENTRY"
fi

if [ ! -f "$HOME/.local/share/applications/time_awareness.desktop" ]; then
  ln -sf "$AUTOSTART_DESKTOP_ENTRY" "$HOME/.local/share/applications/time_awareness.desktop"
fi

echo "Step 6: Launching the app."
ask_proceed
gtk-launch time_awareness

echo "Installation completed. The app will start automatically on next login. You can now close this terminal."
