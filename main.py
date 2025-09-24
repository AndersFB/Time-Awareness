import typer
from pathlib import Path
import time
from time_awareness import TimeAwareness

app = typer.Typer()
ta = None

def get_ta():
    global ta
    if ta is None:
        app_dir = Path.home() / ".time_awareness"
        ta = TimeAwareness(app_dir)
    return ta

@app.command()
def start():
    """Start a new session."""
    get_ta().start_session()
    typer.echo("Session started.")

@app.command()
def stop():
    """Stop the current session."""
    try:
        duration = get_ta().end_session()
        typer.echo(f"Session stopped. Duration: {duration}")
    except Exception as e:
        typer.echo(f"Error: {e}")

@app.command()
def daemon():
    """Run the time awareness daemon."""
    get_ta()._daemon.run()

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
    for start, end, duration in h["history"]:
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
    try:
        while True:
            try:
                get_ta()._session_manager.load_state()  # Reload state to reflect daemon changes
                session_info = get_ta().current_session_info()
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
def reset():
    """Reset the database (delete all sessions and metadata)."""
    if typer.confirm("Are you sure you want to reset all time awareness data? This cannot be undone."):
        get_ta().reset()
        typer.echo("Database has been reset.")
    else:
        typer.echo("Reset cancelled.")

if __name__ == "__main__":
    app()
