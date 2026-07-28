# ⏰ Time Awareness

> **Inspired by the macOS app [Pandan](https://sindresorhus.com/pandan) by Sindre Sorhus.**

Time Awareness is a productivity tool that tracks your computer usage sessions, providing daily summaries and statistics. It features a tray icon for Ubuntu, Debian, Fedora, CentOS, and other Linux desktops (with AyatanaAppIndicator3 support) that allows you to quickly view your current session, total time today, previous sessions, and more.

## ✨ Features

- Tracks active computer usage sessions automatically.
- Ends sessions after an idle threshold (10 minutes).
- Ends the session when the screen locks or the system suspends, and starts a new one on unlock/resume.
- Distinguishes an app restart from a shutdown/reboot: after a quick restart (e.g. an update) the running session is resumed, while after a shutdown or reboot the previous session is closed at the last moment the app was seen running — no phantom time while the machine was off.
- Tray applet for Ubuntu with session info and quick actions.
- **Dynamic tray icon that visually shows time spent as a monochrome circle progress indicator:**
  - 0 min → empty circle.
  - 15 min → 25% filled.
  - 60 min → full circle (then it starts over for the next hour).
- Sessions never span midnight: a session crossing midnight is stored split at the day boundary, so daily totals and statistics stay accurate.
- Does not record time you were not there: starting while you are already away waits for activity instead of opening a session.
- Session history and statistics (daily totals, averages, etc.).
- Persistent state and logging.
- Command line interface alongside the tray applet.
- Configurable through a plain `config.ini`; only one instance tracks at a time,
  so the tray app and the CLI can never overwrite each other's session.

## 🛠️ Requirements

- **Python 3.10+** (set by the current releases of the Python dependencies below;
  the application code itself needs only 3.7+)
- **Linux desktop with AyatanaAppIndicator3 support (Ubuntu, Debian, Fedora, CentOS, etc.)**
- **Python dependencies:** (installed via `requirements.txt`)
  - `pytest`
  - `pygobject`
  - `pydbus`
  - `pillow`
  - `loguru`
  - `peewee`
  - `typer`

- **System packages:**

  **Ubuntu/Debian:**
  ```bash
  sudo apt-get update
  sudo apt-get install \
      python3-gi \
      libgtk-3-bin \
      gir1.2-ayatanaappindicator3-0.1 \
      libayatana-appindicator3-dev \
      dbus \
      libdbus-glib-1-dev \
      libgirepository1.0-dev \
      libgirepository-2.0-dev \
      gir1.2-glib-2.0 \
      gobject-introspection
  ```

  **RHEL/CentOS/Fedora (GNOME required):**
  > **Note:** You may need to enable the CRB repository first:
  > ```bash
  > sudo dnf config-manager --set-enabled crb
  > sudo dnf makecache
  > ```
  ```bash
  sudo dnf install -y \
      python3-gobject \
      libayatana-appindicator3 \
      libayatana-appindicator3-devel \
      cairo \
      cairo-devel \
      cairo-gobject-devel \
      libffi-devel \
      glib2-devel \
      dbus \
      dbus-glib-devel \
      gobject-introspection \
      gobject-introspection-devel \
      libjpeg-turbo \
      libjpeg-turbo-devel \
      gnome-shell \
      gnome-extensions-app
  ```

  **Note:**  
  - For PyGObject > 3.50.1, you need `libgirepository-2.0-dev` (Debian/Ubuntu).  
  - For PyGObject <= 3.50.1, you need `libgirepository1.0-dev` (Debian/Ubuntu).
  - On RHEL/CentOS/Fedora, GNOME desktop is required for tray icon support.

### 💤 Idle Detection
The application uses **GNOME's IdleMonitor** via **D-Bus** to detect inactivity.

## ⚡ Quick Installation

Run this command to automatically install all dependencies, clone the project into `~/.time_awareness/src`, create a virtual environment, install Python packages, and set up autostart:

```bash
curl -sSL https://raw.githubusercontent.com/AndersFB/Time-Awareness/main/scripts/install.sh | bash
```

This will:
- Install required system packages.
- Clone the repository to `~/.time_awareness/src`.
- Create a Python virtual environment (`~/.time_awareness/src/.venv`).
- Install Python dependencies from `requirements.txt`.
- Create an autostart entry so the tray app launches on login.
- Launch the tray app immediately after installation.

## 📝 Manual Installation

1. Clone the repository
    ```bash
    git clone https://github.com/AndersFB/Time-Awareness.git time_awareness
    cd time_awareness
    ```

2. Set up a Python virtual environment
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3. Install Python dependencies
    ```bash
    pip install -r requirements.txt
    ```

4. **If you are on RHEL/CentOS/Fedora (GNOME):**

    - Install the AppIndicator GNOME extension from the provided zip file:
      ```bash
      gnome-extensions install libs/appindicatorsupportrgcjonas.gmail.com.v60.shell-extension.zip
      ```
    - **Log out and log in again.**
    - Enable the extension:
      ```bash
      gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com
      ```
    - **Log out and log in again.**
    - _The tray icon will not work unless this extension is installed and enabled._

5. Launch the tray app
    ```bash
    gtk-launch time_awareness
    ```

    You should see a **circle-based progress icon** in your system tray.  

## 🔄 Updating the Application

To update Time Awareness to the latest version, use the provided update script:

```bash
bash ~/.time_awareness/scripts/update.sh
```

**What it does:**
- Fetches the latest changes from the repository.
- Merges updates if available.
- Restarts the tray app automatically.

Use this script whenever you want to upgrade to the newest release without reinstalling.

## 🚀 Setting Up Autostart

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

4. Launch the app:
    ```bash
    gtk-launch time_awareness
    ```

## 🕹️ Usage

### Tray menu

- **Current session**: When it started and its duration.
- **Total today**: How much time you've spent today, including the session running right now.
- **Previous session**: Details of your last session.
- **Disable**: Ends the current session. Tracking resumes after you have been idle past the idle threshold and come back.
- **New session**: Starts a new session.
- **History**: Shows summary statistics and session details.
- **Reset**: Clears all tracked data and resets the database.
- **Quit**: Cleans up and exits the tray app.

### What the statistics mean

| Value | Meaning |
|---|---|
| **Total today** | Today's completed sessions plus the part of the running session that falls on today |
| **Total yesterday** | Sum of yesterday's sessions |
| **7-day average** | Average time per day over the last 7 calendar days, counting only the days you actually used the computer |
| **Weekday average** | Average daily total for each weekday, then averaged across the weekdays that have data |
| **Total average** | Average length of a single session across your whole history |

### Command line

The CLI is a second front end onto the same database, useful without a tray or
over SSH:

```bash
python main.py current     # show the running session
python main.py live        # keep printing the running session (Ctrl+C to stop)
python main.py history     # statistics and full session history
python main.py start       # start a session
python main.py stop        # stop the running session
python main.py daemon      # run the tracker in the foreground, without a GUI
python main.py reset       # delete all data (asks for confirmation)
```

Only one process may track your time at a time, so the tray app and a CLI daemon
cannot fight over the same session. `current`, `live` and `history` are
read-only and always work. `start`, `stop` and `reset` refuse to run while the
tray app is tracking, since they would overwrite the session it holds:

```
$ python main.py stop
Time Awareness is already tracking in another process (PID 4711).
'stop' would overwrite the session that process is tracking.
Use the tray menu instead, or pass --force to do it anyway.
```

Pass `--force` if you really want to override.

## ⚙️ Configuration

Settings live in `~/.time_awareness/config.ini`, which is created with the
defaults and a comment for each setting the first time the app runs. Edit it and
restart the app; delete it to go back to the defaults.

| Setting | Default | What it does |
|---|---|---|
| `idle_threshold_minutes` | `10` | Minutes without keyboard or mouse activity before the session ends |
| `poll_interval_seconds` | `5` | How often idle time is checked |
| `sleep_detection_threshold_seconds` | `30` | A gap larger than this between two checks counts as the machine having been suspended |
| `monitor_lock_and_sleep` | `true` | End the session on screen lock and suspend, resume on unlock (needs D-Bus) |
| `tray_refresh_seconds` | `10` | How often the tray icon and menu update |
| `max_history_rows` | `500` | Sessions listed in the History dialog; `0` for no limit |
| `verbose` | `false` | Log every idle check, for troubleshooting |

Bad values do not stop the app: anything unparsable falls back to its default,
values below a sensible minimum are raised to it, and
`sleep_detection_threshold_seconds` is pushed above `poll_interval_seconds` if
you set it lower (otherwise every ordinary check would look like a suspend). All
corrections are logged.

## 🧩 Troubleshooting

- **Log file:**  
  All errors and activity are logged to `~/.time_awareness/timeawareness.log`.  
  Check this file for details if the app fails to start or behaves unexpectedly.
  Set `verbose = true` in `config.ini` for per-check detail.

- **Common issues:**
  - **Missing tray icon:**  
    Ensure you have installed all required system packages for your distribution (see Requirements).  
    On GNOME, make sure the AppIndicator extension is enabled (`gnome-extensions list | grep appindicator`).
  - **Python errors:**  
    Make sure you are using Python 3.7 or newer and have activated the virtual environment (`source ~/.time_awareness/src/.venv/bin/activate`).
  - **Idle detection not working:**  
    Confirm that `pydbus` is installed and D-Bus is running.  
    Some desktop environments may not support idle detection; check the log for warnings.  
    Without idle detection the app assumes you are always active, so sessions
    only end on lock, suspend or quit.
  - **Autostart not working:**  
    Verify that `~/.config/autostart/time_awareness.desktop` exists and is executable.  
    You can test autostart by running `gtk-launch time_awareness` or restarting your session.
  - **"Time Awareness is already running":**  
    Another instance already owns tracking, usually because autostart launched it
    and you started it again by hand. Quit the one in the tray first.
    The lock is `~/.time_awareness/tracker.lock`; it is released automatically
    when the owning process exits, including when it is killed.

- **Diagnosing problems:**
  - Run the app from a terminal to see live logs:
    ```bash
    ~/.time_awareness/src/.venv/bin/python ~/.time_awareness/src/app.py
    ```
  - Check for missing dependencies:
    ```bash
    python3 -m pip check
    ```
  - Reinstall system packages if you see import errors for `gi`, `pygobject`, or `dbus`.

## 🗑️ Uninstall

To fully remove Time Awareness if you installed via the quick install script, you can use the automated script:

```bash
bash ~/.time_awareness/scripts/uninstall.sh
```

This script deletes the app directory, removes the autostart entry, and deletes the application symlink.

Alternatively, you can manually run these commands:

1. **Delete the app directory:**
   ```bash
   rm -rf ~/.time_awareness
   ```

2. **Remove the autostart entry:**
   ```bash
   rm -f ~/.config/autostart/time_awareness.desktop
   ```

3. **Remove the application symlink (if present):**
   ```bash
   rm -f ~/.local/share/applications/time_awareness.desktop
   ```

This will remove all files and autostart entries created by the quick install script.

## 🧪 Development

Run the test suite from the repository root:

```bash
python -m pytest tests/ -v
```

`pygobject` and `pydbus` need system GTK and D-Bus libraries. On a headless
machine you can install just the subset the core tests need:

```bash
pip install pytest peewee pillow loguru typer
```

The GUI tests in `tests/test_app.py` are skipped when `AyatanaAppIndicator3` is
unavailable; everything else runs without a desktop. See
[`CLAUDE.md`](CLAUDE.md) for the architecture, the invariants behind the session
tracking, and the project conventions.

## 📄 License

MIT License.
