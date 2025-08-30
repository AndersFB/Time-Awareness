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

spinner() {
  local pid=$1         # PID of the background job
  local message="$2"   # message to display
  local delay=0.1
  local spin='|/-\'
  local i=0

  while kill -0 "$pid" 2>/dev/null; do
    printf "\r[%c] %s" "${spin:i++%${#spin}:1}" "$message"
    sleep $delay
  done

  # when finished
  wait $pid
  local exit_code=$?

  if [ $exit_code -eq 0 ]; then
    printf "\r[✔] %s\n" "$message"
  else
    printf "\r[✖] %s (failed)\n" "$message"
    exit 1
  fi

  return $exit_code
}

echo "Welcome to the Time Awareness installer."
echo "This script will install required system and Python dependencies, clone the repository, and set up autostart."
echo

# Detect OS family (Debian/Ubuntu vs RHEL/CentOS)
if command -v apt-get >/dev/null 2>&1; then
  echo -n "Step 1: Update package list and install required packages using apt-get (requires sudo, you may be asked for your password)."
  ask_proceed

  sudo apt-get update -qq &
  spinner $! "Updating package list"

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
    sudo apt-get install -y "$pkg" >/dev/null 2>&1 &
    spinner $! "Installing $pkg"
  done
elif command -v yum >/dev/null 2>&1 || command -v dnf >/dev/null 2>&1; then
  # Check for GNOME desktop environment
  if [[ "$XDG_CURRENT_DESKTOP" != *GNOME* ]]; then
    echo "GNOME desktop environment is required to run this installer."
    exit 1
  fi

  echo -n "Step 1: Install required packages using dnf (requires sudo, you may be asked for your password)."
  ask_proceed

  if ! sudo dnf repolist enabled | grep -q '^crb'; then
    sudo dnf config-manager --set-enabled crb && sudo dnf makecache >/dev/null 2>&1 &
    spinner $! "Enabling CRB repository"
  fi

  PKGS=(
    python3-gobject
    libayatana-appindicator3
    libayatana-appindicator3-devel
    cairo
    cairo-devel
    cairo-gobject-devel
    libffi-devel
    glib2-devel
    dbus
    dbus-glib-devel
    gobject-introspection
    gobject-introspection-devel
    libjpeg-turbo
    libjpeg-turbo-devel
    gnome-shell
    gnome-extensions-app
  )
  for pkg in "${PKGS[@]}"; do
    sudo dnf install -y "$pkg" >/dev/null 2>&1 &
    spinner $! "Installing $pkg"
  done
else
  echo "Unsupported distribution. Install dependencies manually."
  exit 1
fi

echo
echo -n "Step 2: Clone or update the Time Awareness repository and create Python virtual environment."
ask_proceed

INSTALL_DIR="$HOME/.time_awareness/src"
if [ -d "$INSTALL_DIR" ]; then
  cd "$INSTALL_DIR" || { printf "\nFailed to change directory to $INSTALL_DIR\n" > /dev/tty; exit 1; }
  git pull >/dev/null 2>&1 &
  spinner $! "Pulling latest changes at $INSTALL_DIR"
else
  git clone https://github.com/AndersFB/Time-Awareness.git "$INSTALL_DIR" >/dev/null 2>&1 &
  spinner $! "Cloning repository to $INSTALL_DIR"

  cd "$INSTALL_DIR" || { printf "\nFailed to change directory to $INSTALL_DIR\n" > /dev/tty; exit 1; }

  if command -v yum >/dev/null 2>&1 || command -v dnf >/dev/null 2>&1; then
    EXT_STATUS=$(gnome-extensions info appindicatorsupport@rgcjonas.gmail.com 2>/dev/null | grep -F 'Enabled:' | awk '{print $2}')
    if [ "$EXT_STATUS" != "Yes" ]; then
      gnome-extensions install "$INSTALL_DIR/libs/appindicatorsupportrgcjonas.gmail.com.v60.shell-extension.zip" >/dev/null 2>&1 &
      spinner $! "Installing appindicator GNOME extension"

      echo "[NOTICE] Before you can enable the extension you may need to log out and log back in again or restart you computer."

      gnome-extensions enable "appindicatorsupport@rgcjonas.gmail.com" >/dev/null 2>&1 &
      spinner $! "Enabling appindicator GNOME extension"
    fi

    EXT_STATUS=$(gnome-extensions info appindicatorsupport@rgcjonas.gmail.com 2>/dev/null | grep -F 'Enabled:' | awk '{print $2}')
    if [ "$EXT_STATUS" != "Yes" ]; then
      echo
      echo "[WARNING] The appindicator GNOME extension is still not enabled!"
      echo "[WARNING] The app will not work correctly without this extension."
      echo "[WARNING] Try to log out and back in again or restart you computer and then rerun the install script."
      exit 1
    fi
  fi

  python3 -m venv .venv >/dev/null 2>&1 &
  spinner $! "Creating virtual environment in $INSTALL_DIR/.venv"
fi

echo
echo -n  "Step 3: Activate Python virtual environment and install Python dependencies."
ask_proceed

source .venv/bin/activate || { printf "\nFailed to activate Python virtual environment\n" > /dev/tty; exit 1; }

pip install --upgrade pip >/dev/null 2>&1 &
spinner $! "Upgrading pip"

PIP_REQUIREMENTS_FILE="requirements.txt"

if ! dpkg -s libgirepository-2.0-dev &>/dev/null; then
  echo "Pinning PyGObject to 3.50.1 due to missing libgirepository-2.0-dev."
  sed 's/^pygobject.*/pygobject==3.50.1/' requirements.txt > requirements_pinned.txt || { printf "\nFailed to pin PyGObject version\n" > /dev/tty; exit 1; }
  PIP_REQUIREMENTS_FILE="requirements_pinned.txt"
fi

pip install -U -r "$PIP_REQUIREMENTS_FILE" >/dev/null 2>&1 &
spinner $! "Installing Python dependencies from $INSTALL_DIR/$PIP_REQUIREMENTS_FILE"

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

gtk-launch time_awareness >/dev/null 2>&1 &
spinner $! "Launching the application"

echo
echo "Installation completed. The app will start automatically on next login. You can now close this terminal."
echo "You can uninstall the app by running the uninstall script $INSTALL_DIR/scripts/uninstall.sh."

if command -v yum >/dev/null 2>&1 || command -v dnf >/dev/null 2>&1; then
  echo
  echo "[NOTICE] If the app is not visible in the system tray, try to log out and back in again or restart you computer."
  echo "[NOTICE] Make sure the appindicator GNOME extension is enabled by running the command: gnome-extensions info appindicatorsupport@rgcjonas.gmail.com"
fi
