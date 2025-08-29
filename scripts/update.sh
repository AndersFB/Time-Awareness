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

echo "Welcome to the Time Awareness updater."
echo "This script will update the application to the latest version."
echo

APP_DIR="$HOME/.time_awareness/src"
if [ ! -d "$APP_DIR" ]; then
  echo "[ERROR] Application directory $APP_DIR does not exist. Please run the installer first." > /dev/tty
  exit 1
fi

echo -n "Confirm update."
ask_proceed

cd "$APP_DIR" || { echo "\n[ERROR] Failed to access application directory $APP_DIR" > /dev/tty; exit 1; }
echo -n "Fetching latest changes from repository "
git fetch origin >/dev/null 2>&1 && progress_bar 10 || { echo " failed\n\n[ERROR] Failed to fetch updates from repository" > /dev/tty; exit 1; }
LOCAL=$(git rev-parse @)
REMOTE=$(git rev-parse @{u})
if [ "$LOCAL" = "$REMOTE" ]; then
  echo "Already up to date."
  exit 0
fi

echo -n "Merging latest changes "
git pull origin main >/dev/null 2>&1 && progress_bar 10 || { echo " failed\n\n[ERROR] Failed to merge updates" > /dev/tty; exit 1; }
echo "Update complete."

echo -n "Restarting the app "
pkill -f time_awareness || true && sleep 1 && gtk-launch time_awareness >/dev/null 2>&1 && progress_bar 5 || { echo " failed\n\n[ERROR] Failed to restart the app" > /dev/tty; exit 1; }

echo
echo "Updating completed. You can now close this terminal."
