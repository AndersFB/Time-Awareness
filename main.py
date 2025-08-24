import typer
from pathlib import Path
import time
from time_awareness import TimeAwareness

app = typer.Typer()
ta = None

def get_ta():
    global ta
    if ta is None:
        ta = TimeAwareness(app_dir=Path.home() / ".time_awareness")
        ta.load_state()
    return ta

@app.command()
def start():
    """Start a new session."""
    get_ta().start_session()
    get_ta().save_state()
    typer.echo("Session started.")

@app.command()
def stop():
    """Stop the current session."""
    try:
        duration = get_ta().end_session()
        get_ta().save_state()
        typer.echo(f"Session stopped. Duration: {duration}")
    except Exception as e:
        typer.echo(f"Error: {e}")

@app.command()
def daemon(poll_interval: float = 5.0):
    """Run the time awareness daemon."""
    get_ta().run_daemon(poll_interval=poll_interval)
    get_ta().save_state()

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
        start, now, duration = get_ta().get_current_session()
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
                start, now, duration = get_ta().get_current_session()
                typer.echo(f"\rSession started: {start} | Now: {now} | Duration: {duration}", nl=False)
            except Exception as e:
                typer.echo(f"\rError: {e}                          ", nl=False)
            time.sleep(interval)
    except KeyboardInterrupt:
        typer.echo("\nLive session display stopped.")

if __name__ == "__main__":
    app()
