import pandas as pd
import matplotlib.pyplot as plt
from shiny import App, ui, render, reactive

# -------------------------
# RAW GITHUB CSV URLs
# -------------------------
QB_URL = "https://raw.githubusercontent.com/masonrmutz/INFO-4700-002/main/QBSTATScsv"
RUSH_URL = "https://raw.githubusercontent.com/masonrmutz/INFO-4700-002/main/RUSHSTATScsv"
RECV_URL = "https://raw.githubusercontent.com/masonrmutz/INFO-4700-002/main/CATCHSTATScsv"
FANTASY_URL = "https://raw.githubusercontent.com/masonrmutz/INFO-4700-002/main/SLEEPERAPIcsv"

CSV_URLS = {
    "QB Passing": QB_URL,
    "RB Rushing": RUSH_URL,
    "WR Receiving": RECV_URL,
}

# -------------------------
# FANTASY POINTS HELPER
# -------------------------
def add_fantasy_points(df: pd.DataFrame, stat_type: str) -> pd.DataFrame:
    """
    Adds FantasyPts and FantasyPtsPerGame to the dataframe.
    Scoring:
      - QB Passing: 1 pt per 25 pass yards, 4 pts per pass TD
      - RB/WR: 1 pt per 10 yards, 6 pts per TD, 1 pt per reception (PPR)
    """
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

    # ---- Load main stats CSV based on stat_type ----
    @reactive.Calc
    def df_raw():
        # make reactive on these
        input.stat_type()
        input.refresh()

        stat_type = input.stat_type()
        url = CSV_URLS.get(stat_type)

        try:
            df = pd.read_csv(url)
        except Exception as e:
            # If loading fails, return a tiny error dataframe instead of crashing
            return pd.DataFrame({"Error": [f"Failed to load {stat_type} data: {e}"]})

        df = add_fantasy_points(df, stat_type)
        return df

    # ---- Populate Player Dropdowns ----
    @reactive.effect
    def _populate_players():
        df = df_raw()
        if "Name" in df.columns:
            players = sorted(df["Name"].dropna().unique())
        else:
            players = []
        ui.update_select("player1", choices=players)
        ui.update_select("player2", choices=players)

    # ---- Filters (Team + Player Search) ----
    @reactive.Calc
    def df_filtered():
        df = df_raw().copy()

        # If we only have an Error column, just return it as-is
        if list(df.columns) == ["Error"]:
            return df

        # Filter by team
        if input.team_select() != "All" and "Team" in df.columns:
            df = df[df["Team"] == input.team_select()]

        # Filter by player name search
        if input.player_search() and "Name" in df.columns:
            df = df[df["Name"].str.contains(input.player_search(), case=False)]

        return df

    # ---- Data Table Output ----
    @output
    @render.data_frame
    def player_table():
        return df_filtered()

    # ---- WORKING CHART (Matplotlib) ----
    @output
    @render.plot
    def stat_plot():
        df = df_filtered()

        # If error dataframe, show error text instead of crashing
        if list(df.columns) == ["Error"]:
            fig, ax = plt.subplots()
            msg = df["Error"].iloc[0]
            ax.text(0.5, 0.5, msg, ha="center", va="center", fontsize=10, wrap=True)
            ax.axis("off")
            return fig

        if df.empty:
            fig, ax = plt.subplots()
            ax.text(0.5, 0.5, "No data to display.",
                    ha="center", va="center", fontsize=12)
            ax.axis("off")
            return fig

        # Pick which columns to plot based on stat type
        stat_type = input.stat_type()
        if stat_type == "QB Passing":
            x_stat, y_stat = "YDS", "TD"
            title = "QB Passing: Yards vs Touchdowns"
        elif stat_type == "RB Rushing":
            x_stat, y_stat = "YDS", "TD"
            title = "RB Rushing: Yards vs Touchdowns"
        else:
            x_stat, y_stat = "YDS", "REC"
            title = "WR Receiving: Yards vs Receptions"

        # Safety: only draw if those columns exist
        if x_stat not in df.columns or y_stat not in df.columns:
            fig, ax = plt.subplots()
            ax.text(
                0.5, 0.5,
                f"Columns {x_stat} and/or {y_stat} not found in data.",
                ha="center", va="center", fontsize=10,
            )
            ax.axis("off")
            return fig

        fig, ax = plt.subplots()
        ax.scatter(df[x_stat], df[y_stat])
        ax.set_xlabel(x_stat)
        ax.set_ylabel(y_stat)
        ax.set_title(title)

        # Optionally label a few points (top 5 by y_stat)
        try:
            top = df.sort_values(by=y_stat, ascending=False).head(5)
            if "Name" in top.columns:
                for _, row in top.iterrows():
                    ax.annotate(
                        row["Name"],
                        (row[x_stat], row[y_stat]),
                        textcoords="offset points",
                        xytext=(5, 5),
                        fontsize=8,
                    )
        except Exception:
            pass

        fig.tight_layout()
        return fig

    # ---- Player Comparison Table ----
    @output
    @render.data_frame
    def comparison_table():
        df = df_filtered()

        # If error dataframe, just return it
        if list(df.columns) == ["Error"]:
            return df

        p1 = input.player1()
        p2 = input.player2()

        if not p1 or not p2 or "Name" not in df.columns:
            return pd.DataFrame()

        return pd.concat([df[df["Name"] == p1], df[df["Name"] == p2]])

    # ---- Fantasy CSV Table (SLEEPER) ----
    @reactive.Calc
    def df_fantasy():
        try:
            return pd.read_csv(FANTASY_URL)
        except Exception as e:
            return pd.DataFrame({"Error": [f"Failed to load Sleeper data: {e}"]})

    @output
    @render.data_frame
    def fantasy_table():
        return df_fantasy()


# -------------------------
# Create App
# -------------------------
app = App(app_ui, server)
