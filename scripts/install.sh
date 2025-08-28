#!/usr/bin/env bash
set -e

function ask_proceed() {
  echo -n " Proceed? [Y/n]: " > /dev/tty
  read -r answer < /dev/tty
  if [[ "$answer" =~ ^[Nn]$ ]]; then
    echo "Aborted." > /dev/tty
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

# Detect OS family (Debian/Ubuntu vs RHEL/CentOS)
if command -v apt-get >/dev/null 2>&1; then
  echo -n "Step 1: Update package list and install required packages (requires sudo, you may be asked for your password)."
  ask_proceed
  sudo apt-get update -qq
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
  echo -n "Step 1: Install required packages (requires sudo, you may be asked for your password)."
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

echo
echo -n "Step 2: Clone or update the Time Awareness repository and create Python virtual environment."
ask_proceed
INSTALL_DIR="$HOME/.time_awareness/src"
if [ -d "$INSTALL_DIR" ]; then
  echo -n "Updating existing installation at $INSTALL_DIR "
  cd "$INSTALL_DIR"
  git pull >/dev/null 2>&1 && progress_bar 10
else
  echo -n "Cloning repository to $INSTALL_DIR "
  git clone https://github.com/AndersFB/Time-Awareness.git "$INSTALL_DIR" >/dev/null 2>&1 && progress_bar 10
  cd "$INSTALL_DIR"

  if command -v yum >/dev/null 2>&1 || command -v dnf >/dev/null 2>&1; then
    echo -n "Installing appindicator GNOME extension "
    gnome-extensions install "$INSTALL_DIR/lib/appindicatorsupportrgcjonas.gmail.com.v60.shell-extension.zip" >/dev/null 2>&1 && progress_bar 10
    echo -n "Enabling appindicator GNOME extension "
    gnome-extensions enable "appindicatorsupport@rgcjonas.gmail.com" >/dev/null 2>&1 && progress_bar 5
  fi

  echo -n "Creating Python virtual environment in $INSTALL_DIR/.venv "
  python3 -m venv .venv >/dev/null 2>&1 && progress_bar 10
fi

echo
echo -n  "Step 3: Activate Python virtual environment and install Python dependencies."
ask_proceed
source .venv/bin/activate
echo -n "Upgrading pip "
pip install --upgrade pip >/dev/null 2>&1 && progress_bar 5

PIP_REQUIREMENTS_FILE="requirements.txt"

if ! dpkg -s libgirepository-2.0-dev &>/dev/null; then
  echo "Pinning PyGObject to 3.50.1 due to missing libgirepository-2.0-dev."
  sed 's/^pygobject.*/pygobject==3.50.1/' requirements.txt > requirements_pinned.txt
  PIP_REQUIREMENTS_FILE="requirements_pinned.txt"
fi

echo -n "Installing Python dependencies from $INSTALL_DIR/$PIP_REQUIREMENTS_FILE "
pip install -U -r "$PIP_REQUIREMENTS_FILE" >/dev/null 2>&1 && progress_bar 10

AUTOSTART_DESKTOP_ENTRY="$HOME/.config/autostart/time_awareness.desktop"
APPLICATIONS_DESKTOP_ENTRY="$HOME/.local/share/applications/time_awareness.desktop"

echo
echo -n "Step 4: Create autostart entry and launch the app."
ask_proceed
if [ ! -f "$AUTOSTART_DESKTOP_ENTRY" ]; then
  echo "Creating autostart entry at $AUTOSTART_DESKTOP_ENTRY"
  mkdir -p "$(dirname "$AUTOSTART_DESKTOP_ENTRY")"
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

if [ ! -f "$APPLICATIONS_DESKTOP_ENTRY" ]; then
  echo "Creating application desktop entry at $APPLICATIONS_DESKTOP_ENTRY"
  mkdir -p "$(dirname "$APPLICATIONS_DESKTOP_ENTRY")"
  ln -sf "$AUTOSTART_DESKTOP_ENTRY" "$APPLICATIONS_DESKTOP_ENTRY"
fi

echo -n "Launching the app "
gtk-launch time_awareness >/dev/null 2>&1 && progress_bar 5

echo
echo "Installation completed. The app will start automatically on next login. You can now close this terminal."
echo "You can uninstall the app by running the uninstall script $INSTALL_DIR/scripts/uninstall.sh."
