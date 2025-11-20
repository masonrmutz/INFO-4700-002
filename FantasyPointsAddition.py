import pandas as pd
import matplotlib.pyplot as plt
import altair as alt  # not used yet, but fine to keep
from shiny import App, ui, render, reactive

# -------------------------
# RAW GITHUB CSV URLs
# -------------------------
QB_URL = "https://raw.githubusercontent.com/masonrmutz/INFO-4700-002/main/QBSTATScsv"
RUSH_URL = "https://raw.githubusercontent.com/masonrmutz/INFO-4700-002/main/RUSHSTATScsv"
RECV_URL = "https://raw.githubusercontent.com/masonrmutz/INFO-4700-002/main/CATCHSTATScsv"
FANTASY_URL = "https://raw.githubusercontent.com/masonrmutz/INFO-4700-002/main/SLEEPERAPIcsv"

# Load CSVs once
CSV_DATA = {
    "QB Passing": pd.read_csv(QB_URL),
    "RB Rushing": pd.read_csv(RUSH_URL),
    "WR Receiving": pd.read_csv(RECV_URL),
}
FANTASY_DATA = pd.read_csv(FANTASY_URL)

# -------------------------
# TEAMS LIST
# -------------------------
TEAMS = ["All"] + sorted([
    "BUF", "MIA", "NYJ", "NE",
    "BAL", "CIN", "PIT", "CLE",
    "TEN", "IND", "JAX", "HOU",
    "KC", "LAC", "LV", "DEN",
    "PHI", "DAL", "NYG", "WAS",
    "GB", "MIN", "DET", "CHI",
    "TB", "NO", "ATL", "CAR",
    "SF", "SEA", "LAR", "ARI",
])

# -------------------------
# FANTASY POINTS HELPER
# -------------------------
def add_fantasy_points(df: pd.DataFrame, stat_type: str) -> pd.DataFrame:
    # Adds FantasyPts and FantasyPtsPerGame to the dataframe
    # Scoring:
    #   QB: 1 pt / 25 pass yards, 4 pts / pass TD
    #   RB/WR: 1 pt / 10 yards, 6 pts / TD, 1 pt / reception (PPR)
    df = df.copy()

    if stat_type == "QB Passing":
        yds = df["YDS"] if "YDS" in df.columns else 0
        tds = df["TD"] if "TD" in df.columns else 0
        df["FantasyPts"] = (yds / 25.0) + (tds * 4.0)

    elif stat_type in ["RB Rushing", "WR Receiving"]:
        yds = df["YDS"] if "YDS" in df.columns else 0
        tds = df["TD"] if "TD" in df.columns else 0
        rec = df["REC"] if "REC" in df.columns else 0
        df["FantasyPts"] = (yds / 10.0) + (tds * 6.0) + (rec * 1.0)

    # Fantasy points per game if a games-played column exists
    games_col = None
    for g_col in ["G", "GP", "Games"]:
        if g_col in df.columns:
            games_col = g_col
            break

    if games_col:
        df["FantasyPtsPerGame"] = df["FantasyPts"] / df[games_col]
    else:
        df["FantasyPtsPerGame"] = pd.NA

    return df

# -------------------------
# UI
# -------------------------
app_ui = ui.page_navbar(
    ui.nav_panel("Data Table", ui.output_data_frame("player_table")),
    ui.nav_panel("Interactive Chart", ui.output_plot("stat_plot")),
    ui.nav_panel("Player Comparison", ui.output_data_frame("comparison_table")),
    ui.nav_panel("Fantasy League", ui.output_data_frame("fantasy_table")),
    title="🏈 ESPN NFL Player Stats Dashboard",
    sidebar=ui.sidebar(
        ui.input_select("stat_type", "Select Stat Type:", ["QB Passing", "RB Rushing", "WR Receiving"]),
        ui.input_select("team_select", "Filter by Team:", TEAMS),
        ui.input_text("player_search", "Search Player:"),
        ui.input_select("player1", "Compare Player 1:", []),
        ui.input_select("player2", "Compare Player 2:", []),
        ui.input_action_button("refresh", "🔄 Refresh Data"),
    ),
    selected="Data Table",
)

# -------------------------
# Server
# -------------------------
def server(input, output, session):

    # ---- MAIN DATAFRAME (AUTO-SWITCHES BASED ON STAT TYPE) ----
    @reactive.Calc
    @reactive.event(input.refresh, input.stat_type)
    def df_raw():
        base = CSV_DATA[input.stat_type()].copy()
        base = add_fantasy_points(base, input.stat_type())
        return base

    # ---- Populate Player Dropdowns ----
    @reactive.effect
    def _populate_players():
        df = df_raw()
        players = sorted(df["Name"].dropna().unique()) if "Name" in df.columns else []
        ui.update_select("player1", choices=players)
        ui.update_select("player2", choices=players)

    # ---- Filters (Team + Player Search) ----
    @reactive.Calc
    def df_filtered():
        df = df_raw().copy()

        # Filter by team
        if input.team_select() != "All" and "Team" in df.columns:
