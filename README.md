# ⏰ Time Awareness

> **Inspired by the macOS app [Pandan](https://sindresorhus.com/pandan) by Sindre Sorhus.**

Time Awareness is a productivity tool that tracks your computer usage sessions, providing daily summaries and statistics. It features a tray icon for Ubuntu, Debian, Fedora, CentOS, and other Linux desktops (with AyatanaAppIndicator3 support) that allows you to quickly view your current session, total time today, previous sessions, and more.

## ✨ Features

- Tracks active computer usage sessions automatically.
- Ends sessions after a configurable idle threshold.
- Tray applet for Ubuntu with session info and quick actions.
- **Dynamic tray icon that visually shows time spent as a circle progress indicator:**
  - 0 min → empty circle.
  - 15 min → 25% filled.
  - 1 hour → full circle.
  - Colors change with time \(_optional_\):
    - 0–59 min: blue.
    - 60–119 min: purple.
    - 120+ min: red.
- Session history and statistics (daily totals, averages, etc.).
- Persistent state and logging.

## 🛠️ Requirements

- **Python 3.7+**
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

Run this command to automatically install all dependencies, clone the project into `~/.time_awareness`, create a virtual environment, install Python packages, and set up autostart:

```bash
curl -sSL https://raw.githubusercontent.com/AndersFB/Time-Awareness/main/scripts/install.sh | bash
```

This will:
- Install required system packages.
- Clone the repository to `~/.time_awareness`.
- Create a Python virtual environment (`.venv`).
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

## 🚀 Setting Up Autostart on Ubuntu

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

- **Current session**: When it started and its duration.
- **Total today**: How much time you've spent today.
- **Previous session**: Details of your last session.
- **Disable**: Ends the current session.
- **New session**: Starts a new session.
- **History**: Shows summary statistics and session details.
- **Reset**: Clears all tracked data and resets the database.
- **Quit**: Cleans up and exits the tray app.

## 🧩 Troubleshooting

- **Log file:**  
  All errors and activity are logged to `~/.time_awareness/timeawareness.log`.  
  Check this file for details if the app fails to start or behaves unexpectedly.

- **Common issues:**
  - **Missing tray icon:**  
    Ensure you have installed all required system packages for your distribution (see Requirements).  
    On GNOME, make sure the AppIndicator extension is enabled (`gnome-extensions list | grep appindicator`).
  - **Python errors:**  
    Make sure you are using Python 3.7 or newer and have activated the virtual environment (`source ~/.time_awareness/.venv/bin/activate`).
  - **Idle detection not working:**  
    Confirm that `pydbus` is installed and D-Bus is running.  
    Some desktop environments may not support idle detection; check the log for warnings.
  - **Autostart not working:**  
    Verify that `~/.config/autostart/time_awareness.desktop` exists and is executable.  
    You can test autostart by running `gtk-launch time_awareness` or restarting your session.

- **Diagnosing problems:**
  - Run the app from a terminal to see live logs:
    ```bash
    ~/.time_awareness/.venv/bin/python ~/.time_awareness/app.py
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

## 📄 License

MIT License.
