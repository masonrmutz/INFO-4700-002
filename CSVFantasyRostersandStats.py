import pandas as pd
import matplotlib.pyplot as plt
import ast
import mplcursors  # For hover tooltips
from shiny import App, ui, render, reactive

# -------------------------
# RAW GITHUB CSV URLs
# -------------------------
QB_URL = "https://raw.githubusercontent.com/masonrmutz/INFO-4700-002/main/QBSTATScsv"
RUSH_URL = "https://raw.githubusercontent.com/masonrmutz/INFO-4700-002/main/RUSHSTATScsv"
RECV_URL = "https://raw.githubusercontent.com/masonrmutz/INFO-4700-002/main/CATCHSTATScsv"
FANTASY_URL = "https://raw.githubusercontent.com/masonrmutz/INFO-4700-002/main/SLEEPERAPIcsv"

# -------------------------
# LOAD MAIN STAT CSVs
# -------------------------
CSV_DATA = {
    "QB Passing": pd.read_csv(QB_URL),
    "RB Rushing": pd.read_csv(RUSH_URL),
    "WR Receiving": pd.read_csv(RECV_URL),
}

# -------------------------
# LOAD FANTASY CSV
# -------------------------
FANTASY_RAW = pd.read_csv(FANTASY_URL)

# -------------------------
# HELPER FUNCTIONS
# -------------------------
def get_owner_label(row):
    return (
        row.get("owner") or row.get("display_name") or row.get("Owner") or
        row.get("team_name") or row.get("team")
    )

def expand_fantasy(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ["starters", "players", "bench"]:
        if col in df.columns:
            df[col] = df[col].apply(
                lambda x: ast.literal_eval(x) if isinstance(x, str) and x.startswith("[") else x
            )

    rows = []
    for _, row in df.iterrows():
        owner = get_owner_label(row)
        starters = row.get("starters", []) or []
        all_players = row.get("players", []) or []
        bench_from_col = row.get("bench", None)
        if bench_from_col is not None and isinstance(bench_from_col, list):
            bench = bench_from_col
        else:
            bench = [p for p in all_players if p not in starters]

        for p in starters:
            r = row.to_dict()
            r["OwnerLabel"] = owner
            r["player"] = p
            r["slot"] = "Starter"
            rows.append(r)

        for p in bench:
            r = row.to_dict()
            r["OwnerLabel"] = owner
            r["player"] = p
            r["slot"] = "Bench"
            rows.append(r)

    if not rows:
        return pd.DataFrame()

    out = pd.DataFrame(rows)
    keep_cols = [c for c in ["OwnerLabel", "player", "slot", "wins", "losses", "points_for", "points_against", "streak", "seed"] if c in out.columns]
    base_cols = [c for c in ["OwnerLabel", "player", "slot"] if c in out.columns]
    keep_cols = list(dict.fromkeys(base_cols + keep_cols))

    return out[keep_cols] if keep_cols else out

def fantasy_rosters_pivot(df):
    owners = df.groupby("OwnerLabel")
    rows = []
    for owner, g in owners:
        starters = g[g["slot"] == "Starter"]["player"].tolist()
        bench = g[g["slot"] == "Bench"]["player"].tolist()
        rows.append({
            "Owner": owner,
            "Starters": ", ".join(starters),
            "Bench": ", ".join(bench)
        })
    return pd.DataFrame(rows)

# -------------------------
# BUILD FANTASY DATA
# -------------------------
FANTASY_STANDINGS = FANTASY_RAW.copy()
FANTASY_STANDINGS["OwnerLabel"] = FANTASY_STANDINGS.apply(get_owner_label, axis=1)
standings_cols = [c for c in ["OwnerLabel","wins","losses","ties","points_for","points_against","streak","seed"] if c in FANTASY_STANDINGS.columns]
if standings_cols:
    FANTASY_STANDINGS = FANTASY_STANDINGS[standings_cols]
if "wins" in FANTASY_STANDINGS.columns:
    sort_cols = ["wins"]
    ascending = [False]
    if "points_for" in FANTASY_STANDINGS.columns:
        sort_cols.append("points_for")
        ascending.append(False)
    FANTASY_STANDINGS = FANTASY_STANDINGS.sort_values(by=sort_cols, ascending=ascending)
FANTASY_ROSTERS = expand_fantasy(FANTASY_RAW)

# -------------------------
# TEAMS LIST
# -------------------------
TEAMS = ["All"] + sorted([
    "BUF","MIA","NYJ","NE","BAL","CIN","PIT","CLE","TEN","IND","JAX","HOU",
    "KC","LAC","LV","DEN","PHI","DAL","NYG","WAS","GB","MIN","DET","CHI",
    "TB","NO","ATL","CAR","SF","SEA","LAR","ARI"
])

# -------------------------
# UI
# -------------------------
app_ui = ui.page_navbar(
    ui.nav_panel("Data Table", ui.output_data_frame("player_table")),
    ui.nav_panel("Interactive Chart", ui.output_plot("stat_plot")),
    ui.nav_panel("Player Comparison", ui.output_data_frame("comparison_table")),
    ui.nav_panel("Fantasy Standings", ui.output_data_frame("fantasy_standings_table")),
    ui.nav_panel("Fantasy Rosters", ui.output_data_frame("fantasy_rosters_table")),
    title="🏈 ESPN NFL Player Stats Dashboard",
    sidebar=ui.sidebar(
        ui.input_select("stat_type", "Select Stat Type:", ["QB Passing","RB Rushing","WR Receiving"]),
        ui.input_select("team_select", "Filter by Team:", TEAMS),
        ui.input_text("player_search", "Search Player:"),
        ui.input_select("player1", "Compare Player 1:", []),
        ui.input_select("player2", "Compare Player 2:", []),
        ui.input_action_button("refresh", "🔄 Refresh Data")
    ),
    selected="Data Table"
)

# -------------------------
# SERVER
# -------------------------
def server(input, output, session):

    @reactive.Calc
    @reactive.event(input.refresh, input.stat_type)
    def df_raw():
        return CSV_DATA[input.stat_type()].copy()

    @reactive.effect
    def _populate_players():
        df = df_raw()
        players = sorted(df["Name"].dropna().unique()) if "Name" in df else []
        ui.update_select("player1", choices=players)
        ui.update_select("player2", choices=players)

    @reactive.Calc
    def df_filtered():
        df = df_raw().copy()
        if input.team_select() != "All" and "Team" in df:
            df = df[df["Team"] == input.team_select()]
        if input.player_search() and "Name" in df:
            df = df[df["Name"].str.contains(input.player_search(), case=False)]
        # Remove commas in numeric columns to prevent plotting issues
        for col in ["YDS","TD","REC"]:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(",", "").astype(float)
        return df

    @output
    @render.data_frame
    def player_table():
        return df_filtered()

    # ---- WORKING CHART WITH HOVER (Matplotlib + mplcursors) ----
    @output
    @render.plot
    def stat_plot():
        df = df_filtered()
        if df.empty:
            fig, ax = plt.subplots()
            ax.text(0.5, 0.5, "No data to display.", ha="center", va="center", fontsize=12)
            ax.axis("off")
            return fig

        if input.stat_type() == "QB Passing":
            x_stat, y_stat = "YDS","TD"
            title = "QB Passing: Yards vs Touchdowns"
        elif input.stat_type() == "RB Rushing":
            x_stat, y_stat = "YDS","TD"
            title = "RB Rushing: Yards vs Touchdowns"
        else:
            x_stat, y_stat = "YDS","REC"
            title = "WR Receiving: Yards vs Receptions"

        fig, ax = plt.subplots()
        scatter = ax.scatter(df[x_stat], df[y_stat], picker=True)  # enable hover picking
        ax.set_xlabel(x_stat)
        ax.set_ylabel(y_stat)
        ax.set_title(title)

        # Axes
        ax.set_xlim(0, 5000)
        ax.set_xticks(range(0, 5001, 500))
        ax.set_ylim(0, 50)
        ax.set_yticks(range(0, 51, 10))

        # Hover tooltip for player names
        cursor = mplcursors.cursor(scatter, hover=True)
        cursor.connect("add", lambda sel: sel.annotation.set_text(df.iloc[sel.target.index]["Name"]))

        # Label top 5 players visually
        try:
            top = df.sort_values(by=y_stat, ascending=False).head(5)
            if "Name" in top.columns:
                for _, row in top.iterrows():
                    ax.annotate(row["Name"], (row[x_stat], row[y_stat]), textcoords="offset points", xytext=(5,5), fontsize=8)
        except Exception:
            pass

        fig.tight_layout()
        return fig

    # ---- Player Comparison Table ----
    @output
    @render.data_frame
    def comparison_table():
        df = df_filtered()
        p1 = input.player1()
        p2 = input.player2()
        if not p1 or not p2:
            return pd.DataFrame()
        return pd.concat([df[df["Name"]==p1], df[df["Name"]==p2]])

    # ---- Fantasy Standings ----
    @reactive.Calc
    def df_fantasy_standings():
        df = FANTASY_STANDINGS.copy()
        if input.player_search() and "OwnerLabel" in df.columns:
            df = df[df["OwnerLabel"].str.contains(input.player_search(), case=False)]
        return df

    @output
    @render.data_frame
    def fantasy_standings_table():
        return df_fantasy_standings()

    # ---- Fantasy Rosters ----
    @reactive.Calc
    def df_fantasy_rosters():
        df = FANTASY_ROSTERS.copy()
        if input.player_search() and "player" in df.columns:
            df = df[df["player"].str.contains(input.player_search(), case=False)]
        return fantasy_rosters_pivot(df)

    @output
    @render.data_frame
    def fantasy_rosters_table():
        return df_fantasy_rosters()

# -------------------------
# CREATE APP
# -------------------------
app = App(app_ui, server)
