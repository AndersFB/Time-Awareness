import datetime

import gi
gi.require_version('AppIndicator3', '0.1')
gi.require_version('Gtk', '3.0')
from gi.repository import AppIndicator3, Gtk, GLib
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
from loguru import logger

from time_awareness import TimeAwareness

APP_ID = "time_awareness_tray"
APP_DIR = Path.home() / ".time_awareness"

# Setup loguru logger to APP_DIR/app.log
logger.remove()
logger.add(str(APP_DIR / "app.log"), rotation="10 MB", retention="10 days")
logger.info("Ubuntu tray app started. Logging to {}", APP_DIR / "app.log")

def format_duration(td: datetime.timedelta) -> str:
    if td is None:
        return "-"
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes = (remainder // 60)
    if hours > 0:
        return f"{hours}h {minutes}m."
    else:
        return f"{minutes}m."

def format_time(dt: datetime.datetime) -> str:
    if dt is None:
        return "-"
    return dt.strftime("%H:%M")

def format_date(dt: datetime.datetime) -> str:
    if dt is None:
        return "-"
    return dt.strftime("%m.%d.%Y")

class TrayApp:
    def __init__(self):
        self.ta = TimeAwareness(APP_DIR, start_daemon=True)
        self.indicator = AppIndicator3.Indicator.new(
            APP_ID, "", AppIndicator3.IndicatorCategory.APPLICATION_STATUS
        )
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.menu = Gtk.Menu()
        # Store references to menu items for efficient updates
        self.menu_items = {}
        self.icon_file = Path("/tmp/time_awareness_tray_icon.png")
        self.build_menu()
        self.indicator.set_menu(self.menu)
        self.update_icon()
        GLib.timeout_add_seconds(10, self.refresh)  # update every 10s
        logger.info("TrayApp initialized.")

    def build_menu(self):
        self.menu.foreach(lambda widget: self.menu.remove(widget))

        # Current session (dimmed/grey)
        label_current = Gtk.Label()
        label_current.set_markup('<span foreground="grey">Current session</span>')
        item_current = Gtk.MenuItem()
        item_current.add(label_current)
        item_current.set_sensitive(False)
        self.menu.append(item_current)

        try:
            start, now, duration = self.ta.get_current_session()
            started_label = f"Started at {format_time(start)}"
        except Exception:
            started_label = "Not running"

        item_started = Gtk.MenuItem(label=started_label)
        item_started.set_sensitive(False)
        self.menu.append(item_started)
        self.menu_items["current_session"] = item_started

        # Separator
        self.menu.append(Gtk.SeparatorMenuItem())

        # Total today (dimmed/grey)
        label_total_today = Gtk.Label()
        label_total_today.set_markup('<span foreground="grey">Total today</span>')
        item_total_today = Gtk.MenuItem()
        item_total_today.add(label_total_today)
        item_total_today.set_sensitive(False)
        self.menu.append(item_total_today)

        total_today_label = format_duration(self.ta.total_time_today())
        item_total_today_value = Gtk.MenuItem(label=total_today_label)
        item_total_today_value.set_sensitive(False)
        self.menu.append(item_total_today_value)
        self.menu_items["total_today"] = item_total_today_value

        # Separator
        self.menu.append(Gtk.SeparatorMenuItem())

        # Previous session (dimmed/grey)
        label_prev = Gtk.Label()
        label_prev.set_markup('<span foreground="grey">Previous session</span>')
        item_prev = Gtk.MenuItem()
        item_prev.add(label_prev)
        item_prev.set_sensitive(False)
        self.menu.append(item_prev)

        try:
            prev_start, prev_end, prev_duration = self.ta.previous_session()
            prev_dur_label = format_duration(prev_duration)
            prev_date_label = f"{format_date(prev_start)} {format_time(prev_start)}–{format_time(prev_end)}"
        except Exception:
            prev_dur_label = "-"
            prev_date_label = "-"

        item_prev_dur = Gtk.MenuItem(label=prev_dur_label)
        item_prev_dur.set_sensitive(False)
        self.menu.append(item_prev_dur)
        self.menu_items["prev_dur"] = item_prev_dur

        item_prev_date = Gtk.MenuItem(label=prev_date_label)
        item_prev_date.set_sensitive(False)
        self.menu.append(item_prev_date)
        self.menu_items["prev_date"] = item_prev_date

        # Separator
        self.menu.append(Gtk.SeparatorMenuItem())

        # Disable
        item_disable = Gtk.MenuItem(label="Disable")
        item_disable.connect("activate", self.on_disable)
        self.menu.append(item_disable)

        # New session
        item_new = Gtk.MenuItem(label="New session")
        item_new.connect("activate", self.on_new_session)
        self.menu.append(item_new)

        # History
        item_history = Gtk.MenuItem(label="History")
        item_history.connect("activate", self.on_history)
        self.menu.append(item_history)

        # Separator
        self.menu.append(Gtk.SeparatorMenuItem())

        # Quit
        item_quit = Gtk.MenuItem(label="Quit")
        item_quit.connect("activate", self.on_quit)
        self.menu.append(item_quit)

        self.menu.show_all()

    def update_menu_items(self):
        # Update only relevant menu items
        try:
            start, now, duration = self.ta.get_current_session()
            started_label = f"Started at {format_time(start)}"
        except Exception:
            started_label = "Not running"
        self.menu_items["current_session"].set_label(started_label)

        total_today_label = format_duration(self.ta.total_time_today())
        self.menu_items["total_today"].set_label(total_today_label)

        try:
            prev_start, prev_end, prev_duration = self.ta.previous_session()
            prev_dur_label = format_duration(prev_duration)
            prev_date_label = f"{format_date(prev_start)} {format_time(prev_start)}–{format_time(prev_end)}"
        except Exception:
            prev_dur_label = "-"
            prev_date_label = "-"
        self.menu_items["prev_dur"].set_label(prev_dur_label)
        self.menu_items["prev_date"].set_label(prev_date_label)

    def render_icon(self, td: datetime.timedelta) -> Path:
        # Format as "15 m." or "1h 15m."
        text = format_duration(td)
        # Create image
        img = Image.new('RGBA', (64, 64), (0,0,0,0))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", 32)
        except IOError:
            font = ImageFont.load_default()
        w, h = draw.textsize(text, font=font)
        draw.text(((64-w)/2,(64-h)/2), text, font=font, fill=(255,255,255,255))

        img.save(self.icon_file.as_posix())
        return self.icon_file

    def update_icon(self):
        try:
            _, _, duration = self.ta.get_current_session()
        except Exception:
            duration = datetime.timedelta(seconds=0)
        icon_path = self.render_icon(duration)
        self.indicator.set_icon(icon_path)

    def refresh(self):
        self.update_icon()
        self.update_menu_items()
        return True  # continue timer

    def on_disable(self, widget):
        try:
            self.ta.end_session()
            logger.info("Session ended via tray menu.")
        except Exception:
            logger.warning("Tried to end session via tray menu, but no session was active.")
        self.refresh()

    def on_new_session(self, widget):
        self.ta.start_session()
        logger.info("New session started via tray menu.")
        self.refresh()

    def on_history(self, widget):
        hist = self.ta.history()
        logger.info("History dialog opened. Sessions: {}", len(hist['history']))
        # Show a simple dialog with history summary
        msg = (
            f"Days tracked: {hist['days']}\n"
            f"Total today: {format_duration(hist['total_today'])}\n"
            f"Total yesterday: {format_duration(hist['total_yesterday'])}\n"
            f"7-day avg: {format_duration(hist['seven_day_average'])}\n"
            f"Weekday avg: {format_duration(hist['weekday_average'])}\n"
            f"Total avg: {format_duration(hist['total_average'])}\n"
            f"Sessions: {len(hist['history'])}"
        )
        dialog = Gtk.MessageDialog(
            None, 0, Gtk.MessageType.INFO, Gtk.ButtonsType.OK, "Session History"
        )
        dialog.format_secondary_text(msg)
        dialog.run()
        dialog.destroy()

    def on_quit(self, widget):
        logger.info("Tray app quitting via menu.")
        self.ta.quit_daemon()  # Stop the daemon thread if running
        Gtk.main_quit()
        if self.icon_file.exists():
            self.icon_file.unlink()

def main():
    TrayApp()
    Gtk.main()

if __name__ == "__main__":
    main()
