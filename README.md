# Time Awareness

> **Inspired by the MacOS app [Pandan](https://sindresorhus.com/pandan) by Sindre Sorhus.**

Time Awareness is a simple productivity tool that tracks your computer usage sessions, providing daily summaries and statistics. It features a tray icon for Ubuntu (and other Linux desktops) that allows you to quickly view your current session, total time today, previous sessions, and more.

## Features

- Tracks active computer usage sessions automatically.
- Ends sessions after a configurable idle threshold.
- Tray applet for Ubuntu with session info and quick actions.
- Session history and statistics (daily totals, averages, etc.).
- Persistent state and logging.

## Requirements

- Python 3.7+
- Ubuntu (or other Linux with AppIndicator3 support)
- The following Python packages:
  - `PyGObject` (`gi`)
  - `loguru`
- For idle detection:
  - On Linux: `xprintidle` (install via your package manager)
  - On macOS: `ioreg` (pre-installed)

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/time_awareness.git
cd time_awareness
```

### 2. Set up a Python virtual environment

It is recommended to use a virtual environment to manage dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

#### On Ubuntu, you may also need system packages:

```bash
sudo apt-get install python3-gi gir1.2-appindicator3-0.1 xprintidle
```

- `python3-gi` and `gir1.2-appindicator3-0.1` are required for the tray app.
- `xprintidle` is required for idle time detection.

## Running the Tray App on Ubuntu

To start the tray app:

```bash
source venv/bin/activate
python ubuntu_tray_app.py
```

You should see a tray icon appear, showing your current session duration. Right-click or left-click the icon to access the menu, where you can view session stats, start/end sessions, and quit the app.

## Setting Up Autostart on Ubuntu

To make Time Awareness start automatically when you log in:

1. **Find the full path to your Python and the app script**  
   Activate your virtual environment and run:
   ```bash
   which python
   pwd
   ```
   Note the output (e.g., `/home/youruser/PycharmProjects/time_awareness/venv/bin/python` and `/home/youruser/PycharmProjects/time_awareness`).

2. **Create an autostart entry**  
   Create a file named `time_awareness.desktop` in `~/.config/autostart/` with the following content (replace the paths as needed):

   ```
   [Desktop Entry]
   Type=Application
   Exec=/home/youruser/PycharmProjects/time_awareness/venv/bin/python /home/youruser/PycharmProjects/time_awareness/ubuntu_tray_app.py
   Hidden=false
   NoDisplay=false
   X-GNOME-Autostart-enabled=true
   Name=Time Awareness
   Comment=Track your computer usage sessions
   ```

3. **Make sure the file is executable**  
   ```bash
   chmod +x ~/.config/autostart/time_awareness.desktop
   ```

The app will now start automatically each time you log in to your Ubuntu desktop.

## Usage

- **Current session**: Shows when your current tracked session started.
- **Total today**: Shows how much time you've spent today.
- **Previous session**: Shows details of your last session.
- **Disable**: Ends the current session.
- **New session**: Starts a new session.
- **History**: Shows a summary of your tracked sessions and statistics.
- **Quit**: Exits the tray app.

## Troubleshooting

- If the tray icon does not appear, ensure you have all required system packages installed.
- If you see errors about missing `gi` or `AppIndicator3`, check that `python3-gi` and `gir1.2-appindicator3-0.1` are installed.
- For idle detection to work, `xprintidle` must be installed and available in your PATH.

## Logging

Logs are written to `~/.time_awareness/app.log` and `~/.time_awareness/timeawareness.log`.

## License

MIT License. See [LICENSE](LICENSE) for details.
