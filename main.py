import signal
import typer
from pathlib import Path
import time
from tracker_lock import TrackerAlreadyRunningError, owner_pid
from time_awareness import TimeAwareness

APP_DIR = Path.home() / ".time_awareness"

app = typer.Typer()
ta = None

def get_ta():
    global ta
    if ta is None:
        ta = TimeAwareness(APP_DIR)
    return ta

def require_no_tracker(action: str, force: bool):
    """
    Refuse a command that would fight a running tray app or daemon over the
    current session.

    Both processes keep their own in-memory session state, so whichever writes
    last wins and the other silently reverts it. Reading is always safe; only
    the commands that change session state are blocked.
    """
    if force:
        return
    pid = owner_pid(APP_DIR)
    if pid is None:
        return
    typer.echo(f"Time Awareness is already tracking in another process (PID {pid}).")
    typer.echo(f"'{action}' would overwrite the session that process is tracking.")
    typer.echo("Use the tray menu instead, or pass --force to do it anyway.")
    raise typer.Exit(code=1)

@app.command()
def start(force: bool = typer.Option(False, "--force", help="Run even if another process is tracking.")):
    """Start a new session."""
    require_no_tracker("start", force)
    get_ta().start_session()
    typer.echo("Session started.")

@app.command()
def stop(force: bool = typer.Option(False, "--force", help="Run even if another process is tracking.")):
    """Stop the current session."""
    require_no_tracker("stop", force)
    duration = get_ta().end_session()
    if duration is None:
        typer.echo("No active session.")
    else:
        typer.echo(f"Session stopped. Duration: {duration}")

@app.command()
def daemon():
    """Run the time awareness daemon."""
    ta = get_ta()
    # End the session cleanly when the system or user terminates the daemon.
    # The handler only flags the loop; the daemon closes the session once it has
    # left the iteration it was interrupted in, so no database call is re-entered.
    signal.signal(signal.SIGTERM, lambda *_: ta.request_daemon_stop())
    try:
        # No GLib main loop runs in CLI mode, so the daemon must pump GLib events
        # itself for D-Bus lock/sleep signals to be delivered.
        ta.run_daemon(pump_glib_events=True)
    except TrackerAlreadyRunningError as e:
        typer.echo(str(e))
        typer.echo("Quit the tray app or the other daemon first.")
        raise typer.Exit(code=1)

@app.command()
def history():
    """Print session history and stats."""
    h = get_ta().history()
    typer.echo(f"Days tracked: {h['days']}")
    typer.echo(f"Total today: {h['total_today']}")
    typer.echo(f"Total yesterday: {h['total_yesterday']}")
    typer.echo(f"7-day average: {h['seven_day_average']}")
    typer.echo(f"Weekday average: {h['weekday_average']}")
    typer.echo(f"Total average: {h['total_average']}")
    typer.echo("Session history:")
    for start, end, duration in h["sessions"]:
        typer.echo(f"  {start} - {end} ({duration})")

@app.command()
def current():
    """Show current session info."""
    try:
        session_info = get_ta().current_session_info()
        if session_info is None:
            typer.echo("No active session.")
            return
        start, now, duration = session_info
        typer.echo(f"Session started: {start}")
        typer.echo(f"Now: {now}")
        typer.echo(f"Duration: {duration}")
    except Exception as e:
        typer.echo(f"Error: {e}")

@app.command()
def live(interval: float = 1.0):
    """Continuously show current session info."""
    ta = get_ta()
    try:
        while True:
            try:
                ta.reload_state()  # Reload state to reflect daemon changes
                session_info = ta.current_session_info(verbose=False)
                if session_info is None:
                    typer.echo("\r\033[KNo active session. Taking a break ...", nl=False)
                else:
                    start, now, duration = session_info
                    typer.echo(f"\r\033[KSession started: {start} | Now: {now} | Duration: {duration}", nl=False)
            except Exception as e:
                typer.echo(f"\r\033[KError: {e}", nl=False)
            time.sleep(interval)
    except KeyboardInterrupt:
        typer.echo("\nLive session display stopped.")

@app.command()
def reset(force: bool = typer.Option(False, "--force", help="Run even if another process is tracking.")):
    """Reset the database (delete all sessions and metadata)."""
    require_no_tracker("reset", force)
    if typer.confirm("Are you sure you want to reset all time awareness data? This cannot be undone."):
        get_ta().reset()
        typer.echo("Database has been reset.")
    else:
        typer.echo("Reset cancelled.")

if __name__ == "__main__":
    app()
