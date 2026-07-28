import gi
gi.require_version('AyatanaAppIndicator3', '0.1')
from gi.repository import AyatanaAppIndicator3 as AppIndicator3
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
from PIL import Image, ImageDraw
from pathlib import Path
from loguru import logger
import datetime
import shutil
import signal
import tempfile

from time_awareness import TimeAwareness

APP_ID = "time_awareness_tray"
APP_DIR = Path.home() / ".time_awareness"

# The history dialog renders every session into a single text buffer. Cap it so
# a long-lived database cannot freeze the UI for seconds when the menu is used.
MAX_HISTORY_ROWS = 500

def format_duration(td: datetime.timedelta) -> str:
    if td is None:
        return "-"
    # Clamp: a negative delta (clock stepped backwards) would otherwise render
    # as nonsense like "-1h. 59m." because divmod rounds towards -infinity.
    total_seconds = max(0, int(td.total_seconds()))
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
    return dt.strftime("%d.%m.%Y")

class TrayApp:
    def __init__(self, update_app_interval: int = 10):
        """
        Initialize the tray application, indicator, and menu.
        """
        # Private per-run directory: a fixed /tmp path collides between users
        # and is open to squatting by other accounts.
        self._tmp_icon_dir = Path(tempfile.mkdtemp(prefix="time_awareness_icons_"))
        self._current_icon_file = None
        self._quit_done = False

        self._ta = TimeAwareness(APP_DIR, start_daemon=True, log_to_terminal=True)

        logger.info("Initializing TrayApp.")
        self.indicator = AppIndicator3.Indicator.new(APP_ID, "", AppIndicator3.IndicatorCategory.APPLICATION_STATUS)
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)

        self._menu = Gtk.Menu()
        self._menu_items = {}
        self.build_menu()
        self.indicator.set_menu(self._menu)

        self.update_icon()

        GLib.timeout_add_seconds(update_app_interval, self.refresh)  # update every update_app_interval second
        logger.info("TrayApp initialized.")

    def build_menu(self):
        """
        Build the tray menu with session info, controls, and history.
        """
        self._menu.foreach(lambda widget: self._menu.remove(widget))

        # Current session (dimmed/grey)
        label_current = Gtk.Label()
        label_current.set_markup('<span foreground="grey">Current session</span>')
        item_current = Gtk.MenuItem()
        item_current.add(label_current)
        item_current.set_sensitive(False)
        self._menu.append(item_current)

        session_info = self._ta.current_session_info()
        if session_info is not None:
            start, now, duration = session_info
            started_dur_label = format_duration(duration)
            started_date_label = f"Started at {format_time(start)}"
        else:
            started_dur_label = "-"
            started_date_label = "Not running"

        item_started_dur = Gtk.MenuItem(label=started_dur_label)
        item_started_dur.set_sensitive(False)
        self._menu.append(item_started_dur)
        self._menu_items["current_session_dur"] = item_started_dur

        item_started = Gtk.MenuItem(label=started_date_label)
        item_started.set_sensitive(False)
        self._menu.append(item_started)
        self._menu_items["current_session_date"] = item_started

        # Separator
        self._menu.append(Gtk.SeparatorMenuItem())

        # Total today (dimmed/grey)
        label_total_today = Gtk.Label()
        label_total_today.set_markup('<span foreground="grey">Total today</span>')
        item_total_today = Gtk.MenuItem()
        item_total_today.add(label_total_today)
        item_total_today.set_sensitive(False)
        self._menu.append(item_total_today)

        total_today_label = format_duration(self._ta.total_time_today())
        item_total_today_value = Gtk.MenuItem(label=total_today_label)
        item_total_today_value.set_sensitive(False)
        self._menu.append(item_total_today_value)
        self._menu_items["total_today"] = item_total_today_value

        # Separator
        self._menu.append(Gtk.SeparatorMenuItem())

        # Previous session (dimmed/grey)
        label_prev = Gtk.Label()
        label_prev.set_markup('<span foreground="grey">Previous session</span>')
        item_prev = Gtk.MenuItem()
        item_prev.add(label_prev)
        item_prev.set_sensitive(False)
        self._menu.append(item_prev)

        previous_session_info = self._ta.previous_session()
        if previous_session_info is not None:
            prev_start, prev_end, prev_duration = previous_session_info
            prev_dur_label = format_duration(prev_duration)
            prev_date_label = f"{format_date(prev_start)} {format_time(prev_start)}–{format_time(prev_end)}"
        else:
            prev_dur_label = "-"
            prev_date_label = "-"

        item_prev_dur = Gtk.MenuItem(label=prev_dur_label)
        item_prev_dur.set_sensitive(False)
        self._menu.append(item_prev_dur)
        self._menu_items["prev_dur"] = item_prev_dur

        item_prev_date = Gtk.MenuItem(label=prev_date_label)
        item_prev_date.set_sensitive(False)
        self._menu.append(item_prev_date)
        self._menu_items["prev_date"] = item_prev_date

        # Separator
        self._menu.append(Gtk.SeparatorMenuItem())

        # Disable
        item_disable = Gtk.MenuItem(label="Disable")
        item_disable.connect("activate", self.on_disable)
        self._menu.append(item_disable)

        # New session
        item_new = Gtk.MenuItem(label="New session")
        item_new.connect("activate", self.on_new_session)
        self._menu.append(item_new)

        # History
        item_history = Gtk.MenuItem(label="History")
        item_history.connect("activate", self.on_history)
        self._menu.append(item_history)

        # Reset (new button below History)
        item_reset = Gtk.MenuItem(label="Reset")
        item_reset.connect("activate", self.on_reset)
        self._menu.append(item_reset)

        # Separator
        self._menu.append(Gtk.SeparatorMenuItem())

        # Quit
        item_quit = Gtk.MenuItem(label="Quit")
        item_quit.connect("activate", self.on_quit)
        self._menu.append(item_quit)

        self._menu.show_all()

    def update_menu_items(self):
        """
        Update dynamic menu items with current session and history data.
        """
        session_info = self._ta.current_session_info()
        if session_info is not None:
            start, now, duration = session_info
            started_dur_label = format_duration(duration)
            started_date_label = f"Started at {format_time(start)}"
        else:
            started_dur_label = "-"
            started_date_label = "Not running"
        self._menu_items["current_session_dur"].set_label(started_dur_label)
        self._menu_items["current_session_date"].set_label(started_date_label)

        total_today_label = format_duration(self._ta.total_time_today())
        self._menu_items["total_today"].set_label(total_today_label)

        previous_session_info = self._ta.previous_session(verbose=False)
        if previous_session_info is not None:
            prev_start, prev_end, prev_duration = previous_session_info
            prev_dur_label = format_duration(prev_duration)
            prev_date_label = f"{format_date(prev_start)} {format_time(prev_start)}–{format_time(prev_end)}"
        else:
            prev_dur_label = "-"
            prev_date_label = "-"
        self._menu_items["prev_dur"].set_label(prev_dur_label)
        self._menu_items["prev_date"].set_label(prev_date_label)

    def render_icon(self, td: datetime.timedelta) -> Path:
        """
        Render a tray icon as a circular progress indicator for time spent.

        Args:
            td (timedelta): Duration to display.

        Returns:
            Path: Path to the generated icon image.
        """
        total_minutes = (td.total_seconds() / 60) % 60

        text_filename = f"{int(total_minutes)}m"
        icon_file = self._tmp_icon_dir / f"tray_icon_{text_filename}.png"

        if icon_file.exists():
            #logger.debug(f"Using existing icon image for {format_duration(td)} (time delta: {td}): {icon_file}")
            return icon_file

        # Determine fill percentage (1 hour = full circle, 1.5 hour = half circle etc.)
        fill_fraction = min(total_minutes / 60.0, 1.0)  # Max 1.0 (100%)
        fill_color = (200, 200, 200, 255)  # White

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
        draw.ellipse(outer_bbox, outline=(200, 200, 200, 255), width=6)

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
        session_info = self._ta.current_session_info()
        if session_info is not None:
            _, _, duration = session_info
        else:
            duration = datetime.timedelta(seconds=0)

        current_icon_file = self.render_icon(duration)
        # The icon only changes once a minute while the refresh runs every few
        # seconds; re-setting the same path makes the indicator redraw for nothing.
        if current_icon_file == self._current_icon_file:
            return
        self.indicator.set_icon_full(current_icon_file.as_posix(), "App Icon")
        self._current_icon_file = current_icon_file

    def refresh(self):
        """
        Refresh the tray icon and menu items.

        Returns:
            bool: True to continue periodic refresh.
        """
        # Never let an exception escape into GLib: an uncaught error in a
        # timeout callback removes the source, which would silently freeze the
        # tray icon and menu for the rest of the session.
        try:
            self.update_icon()
            self.update_menu_items()
        except Exception as e:
            logger.exception("Tray refresh failed: {}", e)
        return True  # continue timer

    def on_disable(self, widget):
        """
        End the current session via the tray menu.
        """
        self._ta.end_session()
        logger.info("Session ended via tray menu.")
        self.refresh()

    def on_new_session(self, widget):
        """
        Start a new session via the tray menu.
        """
        self._ta.start_session()
        logger.info("New session started via tray menu.")
        self.refresh()

    def on_history(self, widget):
        """
        Show a dialog with session history and statistics.
        """
        hist = self._ta.history()
        number_of_sessions = len(hist['sessions'])
        number_of_sessions_digits = len(str(number_of_sessions)) if number_of_sessions > 0 else 1
        logger.info("History dialog opened. Sessions: {}", len(hist['sessions']))

        msg = (
            f"Days tracked: {hist['days']}\n"
            f"Total today: {format_duration(hist['total_today'])}\n"
            f"Total yesterday: {format_duration(hist['total_yesterday'])}\n"
            f"7-day avg: {format_duration(hist['seven_day_average'])}\n"
            f"Weekday avg: {format_duration(hist['weekday_average'])}\n"
            f"Total avg: {format_duration(hist['total_average'])}\n"
            f"Sessions: {number_of_sessions}\n\n"
        )

        shown_sessions = hist['sessions'][:MAX_HISTORY_ROWS]
        if len(shown_sessions) < number_of_sessions:
            msg += f"Showing the {len(shown_sessions)} most recent sessions.\n\n"

        session_lines = []
        for i, session_info in enumerate(shown_sessions, start=1):
            session_start, session_end, session_duration = session_info
            if session_duration.total_seconds() < 60 * 60 * 24:
                session_date = f"{format_date(session_start)} {format_time(session_start)}–{format_time(session_end)}"
            else:
                session_date = f"{format_date(session_start)} {format_time(session_start)} – {format_date(session_end)} {format_time(session_end)}"
            session_dur = format_duration(session_duration)
            session_lines.append(f"({str(i).rjust(number_of_sessions_digits)}/{number_of_sessions}) {session_date} ({session_dur})")
        msg += "\n".join(session_lines) if session_lines else "No previous sessions."

        dialog = Gtk.Dialog(
            title="Session History",
            transient_for=None,
            modal=True
        )
        dialog.add_button("OK", Gtk.ResponseType.OK)
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
            self._ta.reset()
            logger.info("Database reset via tray menu.")
            self.refresh()

    def quit(self):
        # SIGTERM during shutdown and the Quit menu item can both land here.
        if self._quit_done:
            return
        self._quit_done = True
        self._ta.stop_daemon()  # Stop the daemon thread if running
        logger.info("Cleaning up icons in {}", self._tmp_icon_dir)
        shutil.rmtree(self._tmp_icon_dir, ignore_errors=True)

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

        def on_termination_signal():
            logger.info("Termination signal received; quitting.")
            app.quit()
            Gtk.main_quit()
            return GLib.SOURCE_REMOVE

        # System shutdown/logout sends SIGTERM; without this the process is
        # killed with the session still open. GLib.unix_signal_add is required
        # because plain Python signal handlers don't run while Gtk.main()
        # blocks in C code.
        GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGTERM, on_termination_signal)
        GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGINT, on_termination_signal)

        Gtk.main()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt detected, quitting...")
    except Exception:
        logger.exception("Unexpected exception in tray app; shutting down.")
    finally:
        # Always run cleanup, so a crash still closes and flushes the session
        # instead of leaving it dangling in the database.
        if app:
            app.quit()

if __name__ == "__main__":
    main()
