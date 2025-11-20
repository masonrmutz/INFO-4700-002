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
    keep_cols = [
        c for c in [
            "OwnerLabel", "player", "slot",
            "wins", "losses", "points_for",
            "points_against", "streak", "seed"
        ] if c in out.columns
    ]
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

# Helper: compute fantasy points for a raw stats DataFrame (for combined table)
def add_fantasy_points(df: pd.DataFrame, stat_type: str) -> pd.DataFrame:
    df = df.copy()

    # Clean numeric-like columns
    numeric_cols = ["YDS", "TD", "REC", "RushYds", "RushTD", "RecYds", "RecTD"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.replace(",", "", regex=False)
            )
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    def num_col(name, default=0.0):
        if name in df.columns:
            return pd.to_numeric(df[name], errors="coerce").fillna(0.0)
        return pd.Series(default, index=df.index, dtype=float)

    df["FantasyPoints"] = 0.0

    # --- QB SCORING ---
    if stat_type == "QB Passing":
        pass_yds = num_col("YDS")
        pass_td = num_col("TD")

        rush_yds = num_col("RushYds") if "RushYds" in df.columns else num_col("RUSH_YDS")
        rush_td = num_col("RushTD") if "RushTD" in df.columns else num_col("RUSH_TD")

        df["FantasyPoints"] = (
            pass_yds / 25.0
            + pass_td * 4.0
            + rush_yds / 10.0
            + rush_td * 6.0
        ).round(2)

    # --- RB SCORING ---
    elif stat_type == "RB Rushing":
        rush_rec_yds = num_col("YDS") + num_col("RecYds")
        rush_rec_td = num_col("TD") + num_col("RecTD")

        df["FantasyPoints"] = (
            rush_rec_yds / 10.0
            + rush_rec_td * 6.0
        ).round(2)

    # --- WR SCORING ---
    elif stat_type == "WR Receiving":
        rec_yds = num_col("YDS")
        rec_td = num_col("TD")
        recs = num_col("REC")

        df["FantasyPoints"] = (
            rec_yds / 10.0
            + rec_td * 6.0
            + recs * 1.0
        ).round(2)

    return df

# -------------------------
# BUILD FANTASY DATA
# -------------------------
FANTASY_STANDINGS = FANTASY_RAW.copy()
FANTASY_STANDINGS["OwnerLabel"] = FANTASY_STANDINGS.apply(get_owner_label, axis=1)
standings_cols = [
    c for c in [
        "OwnerLabel", "wins", "losses", "ties",
        "points_for", "points_against", "streak", "seed"
    ] if c in FANTASY_STANDINGS.columns
]
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
    "BUF", "MIA", "NYJ", "NE", "BAL", "CIN", "PIT", "CLE", "TEN", "IND", "JAX", "HOU",
    "KC", "LAC", "LV", "DEN", "PHI", "DAL", "NYG", "WAS", "GB", "MIN", "DET", "CHI",
    "TB", "NO", "ATL", "CAR", "SF", "SEA", "LAR", "ARI"
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
    ui.nav_panel("Combined Fantasy Points", ui.output_data_frame("combined_fantasy_table")),  # NEW PAGE
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

        # --- Filters ---
        if input.team_select() != "All" and "Team" in df:
            df = df[df["Team"] == input.team_select()]
        if input.player_search() and "Name" in df:
            df = df[df["Name"].str.contains(input.player_search(), case=False)]

        # --- Clean numeric columns (commas, strings) ---
        numeric_cols = ["YDS", "TD", "REC", "RushYds", "RushTD", "RecYds", "RecTD"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = (
                    df[col]
                    .astype(str)
                    .str.replace(",", "", regex=False)
                )
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

        # Helper to safely pull numeric series or 0 if column missing
        def num_col(name, default=0.0):
            if name in df.columns:
                return pd.to_numeric(df[name], errors="coerce").fillna(0.0)
            return pd.Series(default, index=df.index, dtype=float)

        # --- Initialize FantasyPoints ---
        df["FantasyPoints"] = 0.0

        # --- QB SCORING ---
        if input.stat_type() == "QB Passing":
            # YDS = passing yards, TD = passing TD
            pass_yds = num_col("YDS")
            pass_td = num_col("TD")

            # Optional rushing stats if present
            rush_yds = num_col("RushYds") if "RushYds" in df.columns else num_col("RUSH_YDS")
            rush_td = num_col("RushTD") if "RushTD" in df.columns else num_col("RUSH_TD")

            df["FantasyPoints"] = (
                pass_yds / 25.0
                + pass_td * 4.0
                + rush_yds / 10.0
                + rush_td * 6.0
            ).round(2)

        # --- RB SCORING ---
        elif input.stat_type() == "RB Rushing":
            # 1 pt / 10 rushing or receiving yards
            # 6 pts / rushing or receiving TD
            rush_rec_yds = num_col("YDS") + num_col("RecYds")
            rush_rec_td = num_col("TD") + num_col("RecTD")

            df["FantasyPoints"] = (
                rush_rec_yds / 10.0
                + rush_rec_td * 6.0
            ).round(2)

        # --- WR SCORING ---
        else:  # "WR Receiving"
            # 1 pt / 10 receiving yards
            # 6 pts / receiving TD
            # 1 pt / reception (PPR)
            rec_yds = num_col("YDS")      # receiving yards
            rec_td = num_col("TD")        # receiving TD
            recs = num_col("REC")         # receptions

            df["FantasyPoints"] = (
                rec_yds / 10.0
                + rec_td * 6.0
                + recs * 1.0
            ).round(2)

        # --- POINTS PER GAME (PPG) ---
        games_col = None
        for candidate in ["G", "GP", "Games"]:
            if candidate in df.columns:
                games_col = candidate
                break

        if games_col:
            games_played = pd.to_numeric(df[games_col], errors="coerce")
            games_played = games_played.replace(0, pd.NA)
            df["GamesPlayed"] = games_played
            df["FantasyPPG"] = (df["FantasyPoints"] / games_played).round(2)
        else:
            df["GamesPlayed"] = pd.NA
            df["FantasyPPG"] = pd.NA

        return df

    @output
    @render.data_frame
    def player_table():
        # If you *don't* want to show FantasyPoints/PPG here, drop them from columns
        df = df_filtered().copy()
        return df

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
            x_stat, y_stat = "YDS", "TD"
            title = "QB Passing: Yards vs Touchdowns"
        elif input.stat_type() == "RB Rushing":
            x_stat, y_stat = "YDS", "TD"
            title = "RB Rushing: Yards vs Touchdowns"
        else:
            x_stat, y_stat = "YDS", "REC"
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
                    ax.annotate(
                        row["Name"],
                        (row[x_stat], row[y_stat]),
                        textcoords="offset points",
                        xytext=(5, 5),
                        fontsize=8
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
        p1 = input.player1()
        p2 = input.player2()
        if not p1 or not p2:
            return pd.DataFrame()
        return pd.concat([df[df["Name"] == p1], df[df["Name"] == p2]])

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

    # ---- Combined Fantasy Points across QB/RB/WR ----
    @reactive.Calc
    def df_combined_fantasy():
        frames = []

        for stat_type, base_df in CSV_DATA.items():
            df = add_fantasy_points(base_df, stat_type)

            # Require at least Name, Team, FantasyPoints
            if not {"Name", "Team", "FantasyPoints"}.issubset(df.columns):
                continue

            small = df[["Name", "Team", "FantasyPoints"]].copy()
            frames.append(small)

        if not frames:
            return pd.DataFrame()

        all_df = pd.concat(frames, ignore_index=True)

        # Group so each player shows up once with combined fantasy points
        combined = (
            all_df.groupby(["Name", "Team"], as_index=False)["FantasyPoints"]
                  .sum()
        )
        combined["FantasyPoints"] = combined["FantasyPoints"].round(2)

        # Optional: sort by total fantasy points, highest first
        combined = combined.sort_values(by="FantasyPoints", ascending=False)

        return combined

    @output
    @render.data_frame
    def combined_fantasy_table():
        return df_combined_fantasy()

# -------------------------
# CREATE APP
# -------------------------
app = App(app_ui, server)

