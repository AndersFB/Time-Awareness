import gi
gi.require_version('AyatanaAppIndicator3', '0.1')
from gi.repository import AyatanaAppIndicator3 as AppIndicator3
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
from loguru import logger
import datetime

from time_awareness import TimeAwareness

APP_ID = "time_awareness_tray"
APP_DIR = Path.home() / ".time_awareness"

def format_duration(td: datetime.timedelta) -> str:
    if td is None:
        return "-"
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes = (remainder // 60)
    if hours > 0:
        return f"{hours}h. {minutes}m."
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
    def __init__(self, update_app_interval: int = 10):
        """
        Initialize the tray application, indicator, and menu.
        """
        self.tmp_icon_dir = Path("/tmp/time_awareness/")
        if not self.tmp_icon_dir.exists():
            self.tmp_icon_dir.mkdir(parents=True)

        self.ta = TimeAwareness(APP_DIR, start_daemon=True, log_to_terminal=True)
        logger.info("Initializing TrayApp.")

        self.indicator = AppIndicator3.Indicator.new(
            APP_ID, "", AppIndicator3.IndicatorCategory.APPLICATION_STATUS
        )
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.menu = Gtk.Menu()
        self.menu_items = {}
        self.build_menu()
        self.indicator.set_menu(self.menu)

        self.update_icon()

        GLib.timeout_add_seconds(update_app_interval, self.refresh)  # update every refresh_icon second
        logger.info("TrayApp initialized.")

    def build_menu(self):
        """
        Build the tray menu with session info, controls, and history.
        """
        self.menu.foreach(lambda widget: self.menu.remove(widget))

        # Current session (dimmed/grey)
        label_current = Gtk.Label()
        label_current.set_markup('<span foreground="grey">Current session</span>')
        item_current = Gtk.MenuItem()
        item_current.add(label_current)
        item_current.set_sensitive(False)
        self.menu.append(item_current)

        session_info = self.ta.current_session_info()
        if session_info is not None:
            start, now, duration = session_info
            started_dur_label = format_duration(duration)
            started_date_label = f"Started at {format_time(start)}"
        else:
            started_dur_label = "-"
            started_date_label = "Not running"

        item_started_dur = Gtk.MenuItem(label=started_dur_label)
        item_started_dur.set_sensitive(False)
        self.menu.append(item_started_dur)
        self.menu_items["current_session_dur"] = item_started_dur

        item_started = Gtk.MenuItem(label=started_date_label)
        item_started.set_sensitive(False)
        self.menu.append(item_started)
        self.menu_items["current_session_date"] = item_started

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

        previous_session_info = self.ta.previous_session()
        if previous_session_info is not None:
            prev_start, prev_end, prev_duration = previous_session_info
            prev_dur_label = format_duration(prev_duration)
            prev_date_label = f"{format_date(prev_start)} {format_time(prev_start)}–{format_time(prev_end)}"
        else:
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

        # Reset (new button below History)
        item_reset = Gtk.MenuItem(label="Reset")
        item_reset.connect("activate", self.on_reset)
        self.menu.append(item_reset)

        # Separator
        self.menu.append(Gtk.SeparatorMenuItem())

        # Quit
        item_quit = Gtk.MenuItem(label="Quit")
        item_quit.connect("activate", self.on_quit)
        self.menu.append(item_quit)

        self.menu.show_all()

    def update_menu_items(self):
        """
        Update dynamic menu items with current session and history data.
        """
        session_info = self.ta.current_session_info()
        if session_info is not None:
            start, now, duration = session_info
            started_dur_label = format_duration(duration)
            started_date_label = f"Started at {format_time(start)}"
        else:
            started_dur_label = "-"
            started_date_label = "Not running"
        self.menu_items["current_session_dur"].set_label(started_dur_label)
        self.menu_items["current_session_date"].set_label(started_date_label)

        total_today_label = format_duration(self.ta.total_time_today())
        self.menu_items["total_today"].set_label(total_today_label)

        previous_session_info = self.ta.previous_session(verbose=False)
        if previous_session_info is not None:
            prev_start, prev_end, prev_duration = previous_session_info
            prev_dur_label = format_duration(prev_duration)
            prev_date_label = f"{format_date(prev_start)} {format_time(prev_start)}–{format_time(prev_end)}"
        else:
            prev_dur_label = "-"
            prev_date_label = "-"
        self.menu_items["prev_dur"].set_label(prev_dur_label)
        self.menu_items["prev_date"].set_label(prev_date_label)

    def render_icon(self, td: datetime.timedelta) -> Path:
        """
        Render a tray icon as a circular progress indicator for time spent.

        Args:
            td (timedelta): Duration to display.

        Returns:
            Path: Path to the generated icon image.
        """
        # Total seconds spent
        total_minutes = td.total_seconds() / 60

        text_filename = f"{int(total_minutes)}m"
        icon_file = self.tmp_icon_dir / f"tray_icon_{text_filename}.png"

        if icon_file.exists():
            return icon_file

        # Determine fill percentage (1 hour = full circle, 1.5 hour = half circle etc.)
        fill_fraction = min((total_minutes % 60.0) / 60.0, 1.0)  # Max 1.0 (100%)

        # Determine color based on time
        if total_minutes < 60:
            fill_color = (0, 122, 255, 255)  # Blue
        elif total_minutes < 120:
            fill_color = (128, 0, 128, 255)  # Purple
        else:
            fill_color = (255, 0, 0, 255)  # Red

        # Icon size
        size = 128
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Circle bounds
        padding = 8
        bbox = [padding, padding, size - padding, size - padding]

        # Draw outer white circle (thicker than border)
        outer_padding = padding - 4  # slightly outside
        outer_bbox = [outer_padding, outer_padding, size - outer_padding, size - outer_padding]
        draw.ellipse(outer_bbox, outline=(255, 255, 255, 255), width=6)

        # Draw main grey border
        draw.ellipse(bbox, outline=(200, 200, 200, 255), width=8)

        # Draw the filled arc (progress)
        if fill_fraction > 0:
            # Start angle at -90 (12 o'clock), sweep clockwise
            end_angle = -90 + (360 * fill_fraction)
            draw.pieslice(bbox, start=-90, end=end_angle, fill=fill_color)

        # Save icon
        logger.debug(f"Rendering icon image for {format_duration(td)} (time delta: {td}): {icon_file}")
        img.save(icon_file.as_posix())
        return icon_file

    def update_icon(self):
        """
        Update the tray icon to reflect the current session duration.
        """
        session_info = self.ta.current_session_info()
        if session_info is not None:
            _, _, duration = session_info
        else:
            duration = datetime.timedelta(seconds=0)

        total_minutes = duration.total_seconds() / 60
        if total_minutes > 180:
            # The icon will not change after 180 minutes
            return

        current_icon_file = self.render_icon(duration)

        # Set the new icon
        self.indicator.set_icon_full(current_icon_file.as_posix(), "App Icon")

    def refresh(self):
        """
        Refresh the tray icon and menu items.

        Returns:
            bool: True to continue periodic refresh.
        """
        self.update_icon()
        self.update_menu_items()
        return True  # continue timer

    def on_disable(self, widget):
        """
        End the current session via the tray menu.
        """
        try:
            self.ta.end_session()
            logger.info("Session ended via tray menu.")
        except Exception:
            logger.warning("Tried to end session via tray menu, but no session was active.")
        self.refresh()

    def on_new_session(self, widget):
        """
        Start a new session via the tray menu.
        """
        self.ta.start_session()
        logger.info("New session started via tray menu.")
        self.refresh()

    def on_history(self, widget):
        """
        Show a dialog with session history and statistics.
        """
        hist = self.ta.history()
        logger.info("History dialog opened. Sessions: {}", len(hist['sessions']))

        msg = (
            f"Days tracked: {hist['days']}\n"
            f"Total today: {format_duration(hist['total_today'])}\n"
            f"Total yesterday: {format_duration(hist['total_yesterday'])}\n"
            f"7-day avg: {format_duration(hist['seven_day_average'])}\n"
            f"Weekday avg: {format_duration(hist['weekday_average'])}\n"
            f"Total avg: {format_duration(hist['total_average'])}\n"
            f"Sessions: {len(hist['sessions'])}\n\n"
        )

        session_lines = []
        for session_info in hist['sessions']:
            session_start, session_end, session_duration = session_info
            session_date = f"{format_date(session_start)} {format_time(session_start)}–{format_time(session_end)}"
            session_dur = format_duration(session_duration)
            session_lines.append(f"{session_date} ({session_dur})")
        msg += "\n".join(session_lines) if session_lines else "No previous sessions."

        dialog = Gtk.Dialog(
            title="Session History",
            transient_for=None,
            modal=True
        )
        dialog.add_button(Gtk.STOCK_OK, Gtk.ResponseType.OK)
        dialog.set_default_size(400, 300)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        textview = Gtk.TextView()
        textview.set_editable(False)
        textview.get_buffer().set_text(msg)
        scrolled.add(textview)

        box = dialog.get_content_area()
        box.pack_start(scrolled, True, True, 0)
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def on_reset(self, widget):
        """
        Prompt the user to confirm before resetting the database.
        """
        dialog = Gtk.MessageDialog(
            transient_for=None,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Reset Database"
        )
        dialog.format_secondary_text(
            "Are you sure you want to reset all tracked data? This cannot be undone."
        )
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.YES:
            self.ta.reset()
            logger.info("Database reset via tray menu.")
            self.refresh()

    def quit(self):
        self.ta.quit_daemon()  # Stop the daemon thread if running
        logger.info("Cleaning up icons in {}", self.tmp_icon_dir)
        for icon_file in self.tmp_icon_dir.glob("tray_icon_*.png"):
            icon_file.unlink(missing_ok=True)

    def on_quit(self, widget):
        """
        Quit the tray application and clean up resources.
        """
        logger.info("Tray app quitting via menu.")
        self.quit()
        Gtk.main_quit()

def main():
    """
    Entry point for the tray application.
    """
    app = None
    try:
        app = TrayApp()
        Gtk.main()
    except KeyboardInterrupt:
        print("KeyboardInterrupt detected, quitting...")
        if app:
            app.quit()
    except Exception as e:
        print(f"Unexpected exception: {e}")

if __name__ == "__main__":
    main()
