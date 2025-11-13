import pandas as pd
import altair as alt
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

# If your CSVs have different column names, tell me & I’ll adjust everything.


# -------------------------
# TEAMS LIST (EDIT IF NEEDED)
# -------------------------
TEAMS = ["All"] + sorted([
    "BUF", "MIA", "NYJ", "NE",
    "BAL", "CIN", "PIT", "CLE",
    "TEN", "IND", "JAX", "HOU",
    "KC", "LAC", "LV", "DEN",
    "PHI", "DAL", "NYG", "WAS",
    "GB", "MIN", "DET", "CHI",
    "TB", "NO", "ATL", "CAR",
    "SF", "SEA", "LAR", "ARI"
])


# -------------------------
# UI
# -------------------------
app_ui = ui.page_navbar(
    ui.nav_panel("Data Table", ui.output_data_frame("player_table")),
    ui.nav_panel("Interactive Chart", ui.output_ui("chart_ui")),
    ui.nav_panel("Player Comparison", ui.output_data_frame("comparison_table")),
    ui.nav_panel("Fantasy League", ui.output_data_frame("fantasy_table")),
    title="🏈 ESPN NFL Player Stats Dashboard",

    sidebar=ui.sidebar(
        ui.input_select("stat_type", "Select Stat Type:", ["QB Passing", "RB Rushing", "WR Receiving"]),
        ui.input_select("team_select", "Filter by Team:", TEAMS),
        ui.input_text("player_search", "Search Player:"),
        ui.input_select("player1", "Compare Player 1:", []),
        ui.input_select("player2", "Compare Player 2:", []),
        ui.input_action_button("refresh", "🔄 Refresh Data")
    ),
    selected="Data Table"
)


# -------------------------
# Server
# -------------------------
def server(input, output, session):

    # ---- MAIN DATAFRAME (AUTO-SWITCHES BASED ON STAT TYPE) ----
    @reactive.Calc
    @reactive.event(input.refresh, input.stat_type)
    def df_raw():
        return CSV_DATA[input.stat_type()].copy()

    # ---- Populate Player Dropdowns ----
    @reactive.effect
    def _populate_players():
        df = df_raw()
        players = sorted(df["Name"].dropna().unique()) if "Name" in df else []
        ui.update_select("player1", choices=players)
        ui.update_select("player2", choices=players)

    # ---- Filters (Team + Player Search) ----
    @reactive.Calc
    def df_filtered():
        df = df_raw().copy()

        # Filter by team
        if input.team_select() != "All" and "Team" in df:
            df = df[df["Team"] == input.team_select()]

        # Filter by player name search
        if input.player_search() and "Name" in df:
            df = df[df["Name"].str.contains(input.player_search(), case=False)]

        return df

    # ---- Data Table Output ----
    @output
    @render.data_frame
    def player_table():
        return df_filtered()

    # ---- Interactive Chart ----
    @output
    @render.ui
    def chart_ui():
        df = df_filtered()
        if df.empty:
            return ui.p("No data to display.")

        # Pick chart stats
        if input.stat_type() == "QB Passing":
            x_stat, y_stat = "YDS", "TD"
            title = "QB Passing: Yards vs Touchdowns"
        elif input.stat_type() == "RB Rushing":
            x_stat, y_stat = "YDS", "TD"
            title = "RB Rushing: Yards vs Touchdowns"
        else:
            x_stat, y_stat = "YDS", "REC"
            title = "WR Receiving: Yards vs Receptions"

        chart = (
            alt.Chart(df)
            .mark_circle(size=100, opacity=0.7)
            .encode(
                x=alt.X(x_stat, title=x_stat),
                y=alt.Y(y_stat, title=y_stat),
                color=alt.Color("Team", legend=alt.Legend(title="Team")),
                tooltip=["Name", "Team", x_stat, y_stat]
            )
            .properties(width=700, height=500, title=title)
            .interactive()
        )

        return ui.HTML(chart.to_html())

    # ---- Player Comparison Table ----
    @output
    @render.data_frame
    def comparison_table():
        df = df_filtered()
        p1 = input.player1()
        p2 = input.player2()

        if not p1 or not p2:
            return pd.DataFrame()

        return pd.concat([df[df["Name"] == p1], df[df["Name"] == p2]])

    # ---- Fantasy CSV Table (SLEEPER) ----
    @reactive.Calc
    def df_fantasy():
        return FANTASY_DATA.copy()

    @output
    @render.data_frame
    def fantasy_table():
        return df_fantasy()


# -------------------------
# Create App
# -------------------------
app = App(app_ui, server)
