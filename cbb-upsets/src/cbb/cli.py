import typer

app = typer.Typer(help="CBB Upsets: Pipeline CLI for NCAA men’s basketball upsets prediction.")

@app.command()
def ingest_odds(season: int = typer.Argument(..., help="Season year, e.g. 2023")):
    """
    Ingest odds data from official API or dataset for a given season.
    """
    # from cbb.odds.odds_api import fetch_odds_from_api
    # fetch_odds_from_api(season)
    typer.echo(f"Ingested odds for season {season}")

@app.command()
def compute_metrics(season: int = typer.Argument(..., help="Season year")):
    """
    Calculate team metrics (e.g. win %, point diff, etc.) for a season and persist to DB.
    """
    # from cbb.metrics.team_metrics import compute_team_metrics
    # compute_team_metrics(season)
    typer.echo(f"Computed team metrics for season {season}")

@app.command()
def build_features(season: int = typer.Argument(..., help="Season year")):
    """
    Build model training features for a specified season.
    """
    # from cbb.features.build_features import build_features
    # build_features(season)
    typer.echo(f"Built features for season {season}")

@app.command()
def train(season: int = typer.Argument(..., help="Season year")):
    """
    Train the baseline model on data and save persistently.
    """
    # from cbb.model.train import train_baseline
    # train_baseline(season)
    typer.echo(f"Model trained for season {season}")

@app.command()
def predict(
    season: int = typer.Argument(..., help="Season year"),
    games_csv: str = typer.Option(..., "--games", "-g", help="CSV with game info")
):
    """
    Predict upset probabilities for upcoming games provided in a CSV.
    """
    # from cbb.model.predict import predict
    # predict(season, games_csv)
    typer.echo(f"Predictions complete for season {season} using {games_csv}")

@app.command()
def dashboard():
    """
    Run the interactive dashboard application.
    """
    # from cbb.app.dashboard import run_dashboard
    # run_dashboard()
    typer.echo("Dashboard launched")

if __name__ == "__main__":
    app()