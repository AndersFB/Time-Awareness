#!/usr/bin/env bash

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

APP_DIR="$HOME/.time_awareness"
AUTOSTART_DESKTOP_ENTRY="$HOME/.config/autostart/time_awareness.desktop"
APPLICATIONS_DESKTOP_ENTRY="$HOME/.local/share/applications/time_awareness.desktop"

echo "Welcome to the Time Awareness uninstaller."
echo "This script will remove the application files and autostart entry."
echo

# Check for --yes argument
SKIP_CONFIRM=false
for arg in "$@"; do
  if [ "$arg" == "--yes" ]; then
    SKIP_CONFIRM=true
    break
  fi
done

if [ "$SKIP_CONFIRM" = false ]; then
  echo -n "Confirm uninstallation."
  ask_proceed
  echo
fi

pkill -f time_awareness || true && sleep 3 >/dev/null 2>&1 &
spinner $! "Waiting for the application to close"

rm -rf "$APP_DIR" >/dev/null 2>&1 &
spinner $! "Removing application files in $APP_DIR"

echo "Removing autostart entry $AUTOSTART_DESKTOP_ENTRY "
rm -f "$AUTOSTART_DESKTOP_ENTRY" >/dev/null 2>&1 || { printf "\nFailed to remove autostart entry\n" > /dev/tty; exit 1; }

echo -n "Removing applications menu entry $APPLICATIONS_DESKTOP_ENTRY "
rm -f "$APPLICATIONS_DESKTOP_ENTRY" >/dev/null 2>&1 || { printf "\nFailed to remove applications menu entry\n" > /dev/tty; exit 1; }

echo "Uninstallation complete."
