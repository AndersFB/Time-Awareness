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

APP_DIR="$HOME/.time_awareness"
AUTOSTART_DESKTOP_ENTRY="$HOME/.config/autostart/time_awareness.desktop"
APPLICATIONS_DESKTOP_ENTRY="$HOME/.local/share/applications/time_awareness.desktop"

echo "Welcome to the Time Awareness uninstaller."
echo "This script will remove the application files and autostart entry."
echo
echo -n "Confirm uninstallation."
ask_proceed

echo -n "Closing the app "
pkill -f time_awareness || true && sleep 3 >/dev/null 2>&1 && progress_bar 5 || { echo " failed\n\n[ERROR] Failed to close the app" > /dev/tty; exit 1; }

echo -n "Removing application files in $APP_DIR "
rm -rf "$APP_DIR" >/dev/null 2>&1 && progress_bar 5 || { echo " failed\n\n[ERROR] Failed to remove application files" > /dev/tty; exit 1; }
echo -n "Removing autostart entry $AUTOSTART_DESKTOP_ENTRY "
rm -f "$AUTOSTART_DESKTOP_ENTRY" >/dev/null 2>&1 && progress_bar 5 || { echo " failed\n\n[ERROR] Failed to remove autostart entry" > /dev/tty; exit 1; }
echo -n "Removing applications menu entry $APPLICATIONS_DESKTOP_ENTRY "
rm -f "$APPLICATIONS_DESKTOP_ENTRY" >/dev/null 2>&1 && progress_bar 5 || { echo " failed\n\n[ERROR] Failed to remove applications menu entry" > /dev/tty; exit 1; }

echo "Uninstallation complete."
