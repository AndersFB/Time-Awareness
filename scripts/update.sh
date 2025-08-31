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

echo "Welcome to the Time Awareness updater."
echo "This script will update the application to the latest version."
echo

APP_DIR="$HOME/.time_awareness/src"
if [ ! -d "$APP_DIR" ]; then
  echo "Application directory $APP_DIR does not exist. Please run the installer first." > /dev/tty
  exit 1
fi

echo -n "Confirm update."
ask_proceed

cd "$APP_DIR" || { printf "\nFailed to access application directory $APP_DIR\n" > /dev/tty; exit 1; }
git fetch origin >/dev/null 2>&1 &
spinner $! "Fetching latest changes from repository"

LOCAL=$(git rev-parse @)
REMOTE=$(git rev-parse @{u})
if [ "$LOCAL" = "$REMOTE" ]; then
  echo "Already up to date."
  exit 0
fi

git pull origin main >/dev/null 2>&1 &
spinner $! "Merging latest changes"

pkill -f time_awareness || true && sleep 3 && gtk-launch time_awareness >/dev/null 2>&1 &
spinner $! "Restarting the application"

echo
echo "Updating completed. You can now close this terminal."
