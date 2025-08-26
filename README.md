# Time Awareness

> **Inspired by the macOS app [Pandan](https://sindresorhus.com/pandan) by Sindre Sorhus.**

Time Awareness is a productivity tool that tracks your computer usage sessions, providing daily summaries and statistics. It features a tray icon for Ubuntu (and other Linux desktops) that allows you to quickly view your current session, total time today, previous sessions, and more.

---

## Features

- Tracks active computer usage sessions automatically.
- Ends sessions after a configurable idle threshold.
- Tray applet for Ubuntu with session info and quick actions.
- **Dynamic tray icon that visually shows time spent as a circle progress indicator:**
  - 0 min → empty circle.
  - 15 min → 25% filled.
  - 1 hour → full circle.
  - Colors change with time:
    - 0–59 min: blue.
    - 60–119 min: purple.
    - 120+ min: red.
- Session history and statistics (daily totals, averages, etc.).
- Persistent state and logging.
- Graceful cleanup on `Ctrl+C`.

---

## Requirements

- **Python 3.7+**
- **Ubuntu (or Linux with AyatanaAppIndicator3 support)**
- **Python dependencies:** (installed via `requirements.txt`)
  - `pytest`
  - `pygobject`
  - `pydbus`
  - `pillow`
  - `loguru`
  - `peewee`
  - `typer`

- **System packages (Ubuntu):**
  ```bash
  sudo apt-get update
  sudo apt-get install \
      python3-gi \
      gir1.2-ayatanaappindicator3-0.1 \
      libayatana-appindicator3-dev \
      dbus \
      libdbus-glib-1-dev
  ```
  - `python3-gi` and `gir1.2-ayatanaappindicator3-0.1` → required for the tray app.
  - `libayatana-appindicator3-dev` → ensures AppIndicator works properly.
  - `dbus` and `libdbus-glib-1-dev` → needed for idle detection via D-Bus.

---

### Idle Detection
The application uses **GNOME's IdleMonitor** via **D-Bus** to detect inactivity.

---

## Quick Installation (Recommended)

Run this command to automatically install all dependencies, clone the project into `~/.time_awareness`, create a virtual environment, install Python packages, and set up autostart:

```bash
curl -sSL https://raw.githubusercontent.com/AndersFB/Time-Awareness/main/install.sh | bash
```

This will:
- Install required system packages.
- Clone the repository to `~/.time_awareness`.
- Create a Python virtual environment (`.venv`).
- Install Python dependencies from `requirements.txt`.
- Create an autostart entry so the tray app launches on login.

After installation, you can start the app immediately with:

```bash
~/.time_awareness/.venv/bin/python ~/.time_awareness/app.py
```

---

## Manual Installation

### 1. Clone the repository
```bash
git clone https://github.com/AndersFB/Time-Awareness.git time_awareness
cd time_awareness
```

### 2. Set up a Python virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Python dependencies
```bash
pip install -r requirements.txt
```

---

## Running the Tray App on Ubuntu

To start the tray app:
```bash
source venv/bin/activate
python app.py
```

You should see a **circle-based progress icon** in your system tray.  
- Right-click the icon to open the menu with:
  - Current session info
  - Total time today
  - Previous session details
  - Options to start/stop sessions
  - **Quit** (cleans up temporary icons and stops the background daemon)

**KeyboardInterrupt (`Ctrl+C`) is handled gracefully**: the app calls its `on_quit()` method to clean up before exiting.

---

## Setting Up Autostart on Ubuntu

If you did not use the automatic installer, you can set up autostart manually:

1. **Find paths to Python and the app script**
   ```bash
   which python
   pwd
   ```
2. **Create `~/.config/autostart/time_awareness.desktop`**:
   ```
   [Desktop Entry]
   Type=Application
   Exec=/full/path/to/python /full/path/to/app.py
   Hidden=false
   NoDisplay=false
   X-GNOME-Autostart-enabled=true
   Name=Time Awareness
   Comment=Track your computer usage sessions
   ```
3. Make it executable:
   ```bash
   chmod +x ~/.config/autostart/time_awareness.desktop
   ```

---

## Usage

- **Current session**: When it started and its duration.
- **Total today**: How much time you've spent today.
- **Previous session**: Details of your last session.
- **Disable**: Ends the current session.
- **New session**: Starts a new session.
- **History**: Shows summary statistics.
- **Quit**: Cleans up and exits the tray app.

---

## Troubleshooting

- If the tray icon does not appear:
  - Ensure `python3-gi` and `gir1.2-ayatanaappindicator3-0.1` are installed.
- If idle detection does not work:
  - Ensure `dbus` is installed.
- Logs are stored in `~/.time_awareness/timeawareness.log`.

---

## License
MIT License.
