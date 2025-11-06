# Imports

import os
import time
import pandas as pd
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

from shiny import App, ui, reactive, render
import altair as alt

# Config / URLs

URL_PASSING = "https://www.espn.com/nfl/stats/player/_/stat/passing"
URL_RUSH = "https://www.espn.com/nfl/stats/player/_/stat/rushing"
URL_RECEIVING = "https://www.espn.com/nfl/stats/player/_/stat/receiving"

TEAMS = ["All", "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN",
         "DET", "GB", "HOU", "IND", "JAX", "KC", "LAC", "LAR", "LV", "MIA", "MIN",
         "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS"]

CACHE_DIR = "cached_data"
os.makedirs(CACHE_DIR, exist_ok=True)
CACHE_FILES = {
    "QB Passing": os.path.join(CACHE_DIR, "espn_passing.csv"),
    "RB Rushing": os.path.join(CACHE_DIR, "espn_rushing.csv"),
    "WR Receiving": os.path.join(CACHE_DIR, "espn_receiving.csv"),
}

# Helper functions

def build_driver(headless=True):
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1400,1000")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

def click_show_more_until_done(driver, table_container, wait, pause=0.8, max_clicks=100):
    left_rows_css = ".Table--fixed-left tbody tr.Table__TR[data-idx]"

    def row_count():
        return len(table_container.find_elements(By.CSS_SELECTOR, left_rows_css))

    def find_show_more():
        local = table_container.find_elements(By.CSS_SELECTOR, "a.AnchorLink.loadMore__link")
        if local:
            return next((x for x in local if x.is_displayed() and x.is_enabled()), None)
        page = driver.find_elements(By.CSS_SELECTOR, "a.AnchorLink.loadMore__link")
        return next((x for x in page if x.is_displayed() and x.is_enabled()), None)

    clicks = 0
    prev = row_count()
    while clicks < max_clicks:
        link = find_show_more()
        if not link:
            break
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", link)
        try:
            wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.AnchorLink.loadMore__link")))
            link.click()
        except Exception:
            driver.execute_script("arguments[0].click();", link)
        time.sleep(pause)
        new = row_count()
        if new <= prev:
            time.sleep(0.7)
            new = row_count()
            if new <= prev:
                break
        prev = new
        clicks += 1

# ESPN Scraper Functions

def scrape_espn_stats(url, cache_file, desired_columns, id_str):
    if os.path.exists(cache_file):
        return pd.read_csv(cache_file)

    driver = build_driver(headless=True)
    wait = WebDriverWait(driver, 20)
    try:
        driver.get(url)
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.ResponsiveTable")))
        blocks = driver.find_elements(By.CSS_SELECTOR, "div.ResponsiveTable")

        target_block = None
        for block in blocks:
            link = block.find_elements(By.CSS_SELECTOR, f'thead a[href*="/stat/{id_str}/"]')
            if link:
                target_block = block
                break
        if target_block is None:
            raise RuntimeError(f"Couldn't find the {id_str} stats table.")

        click_show_more_until_done(driver, target_block, wait)

        player_summary = {}
        for row in target_block.find_elements(By.CSS_SELECTOR, ".Table--fixed-left tbody tr.Table__TR"):
            idx = row.get_attribute("data-idx")
            if not idx:
                continue
            rk = row.find_elements(By.CSS_SELECTOR, "td.Table__TD")[0].text.strip()
            name = row.find_element(By.CSS_SELECTOR, "a.AnchorLink").text.strip() if row.find_elements(By.CSS_SELECTOR, "a.AnchorLink") else ""
            team = row.find_element(By.CSS_SELECTOR, ".athleteCell__teamAbbrev").text.strip() if row.find_elements(By.CSS_SELECTOR, ".athleteCell__teamAbbrev") else ""
            player_summary[idx] = {"RK": rk, "Name": name, "Team": team}

        headers = [th.text.strip() for th in target_block.find_elements(By.CSS_SELECTOR, ".Table__Scroller thead th")]
        header_pos = {h: i for i, h in enumerate(headers)}
        stats = {}
        for row in target_block.find_elements(By.CSS_SELECTOR, ".Table__Scroller tbody tr.Table__TR"):
            idx = row.get_attribute("data-idx")
            if not idx:
                continue
            cells = row.find_elements(By.CSS_SELECTOR, "td.Table__TD")
            vals = [c.text.strip() for c in cells]
            stats[idx] = {
                h: vals[header_pos[h]] if h in header_pos and header_pos[h] < len(vals) else ""
                for h in desired_columns
            }

        rows = [
            {**player_summary.get(idx, {}), **stats.get(idx, {})}
            for idx in sorted(set(player_summary) | set(stats), key=lambda x: int(x))
        ]
        df = pd.DataFrame(rows)
        df.to_csv(cache_file, index=False)
        return df
    finally:
        driver.quit()

def scrape_espn_passing_with_selenium():
    return scrape_espn_stats(
        URL_PASSING,
        CACHE_FILES["QB Passing"],
        ["POS","GP","CMP","ATT","CMP%","YDS","AVG","YDS/G","LNG","TD","INT","SACK","SYL","QBR","RTG"],
        "passing"
    )

def scrape_espn_rushing_with_selenium():
    return scrape_espn_stats(
        URL_RUSH,
        CACHE_FILES["RB Rushing"],
        ["POS","GP","ATT","YDS","AVG","LNG","BIG","TD","YDS/G","FUM","LST","FD"],
        "rushing"
    )

def scrape_espn_receiving_with_selenium():
    return scrape_espn_stats(
        URL_RECEIVING,
        CACHE_FILES["WR Receiving"],
        ["POS","GP","REC","TGTS","YDS","AVG","YDS/G","LNG","TD","20+","40+","FUM","LST","FD","YAC","DROP","CTCH%"],
        "receiving"
    )

# Sleeper Fantasy Functions

def sleeper_rosters_df(league_id: str) -> pd.DataFrame:
    league = requests.get(f"https://api.sleeper.app/v1/league/{league_id}").json()
    users = requests.get(f"https://api.sleeper.app/v1/league/{league_id}/users").json()
    rosters = requests.get(f"https://api.sleeper.app/v1/league/{league_id}/rosters").json()
    players = requests.get("https://api.sleeper.app/v1/players/nfl").json()

    user_map = {u["user_id"]: u["display_name"] for u in users}

    combined_data = []
    for roster in rosters:
        owner_name = user_map.get(roster.get("owner_id"), "Unknown")
        player_ids = roster.get("players", [])
        starter_ids = roster.get("starters", [])

        starters = [
            players[p].get("full_name", "Unknown Player")
            for p in starter_ids
            if p in players
        ]
        bench = [
            players[p].get("full_name", "Unknown Player")
            for p in player_ids
            if p not in starter_ids and p in players
        ]

        wins = roster.get("settings", {}).get("wins", 0)
        losses = roster.get("settings", {}).get("losses", 0)
        points = roster.get("settings", {}).get("fpts", 0)
        games_played = wins + losses if (wins + losses) > 0 else 1
        avg_points_per_game = round(points / games_played, 2)

        combined_data.append({
            "owner": owner_name,
            "starters": starters,
            "bench": bench,
            "wins": wins,
            "losses": losses,
            "points": points,
            "avg_points_per_game": avg_points_per_game
        })

    return pd.DataFrame(combined_data)


def standings(league_id: str) -> pd.DataFrame:
    users = requests.get(f"https://api.sleeper.app/v1/league/{league_id}/users", timeout=20).json()
    userId = {u["user_id"]: u for u in users}
    rosters = requests.get(f"https://api.sleeper.app/v1/league/{league_id}/rosters", timeout=20).json()

    rows = []
    for r in rosters:
        s = r.get("settings", {}) or {}
        owner_id = r.get("owner_id")
        u = userId.get(owner_id, {})
        display = u.get("display_name") or ""
        team = (
            (r.get("metadata", {}) or {}).get("team_name")
            or (u.get("metadata", {}) or {}).get("team_name")
            or display
            or f"Team {r.get('roster_id')}"
        )
        pf = float(s.get("fpts", 0)) + float(s.get("fpts_decimal", 0) or 0) / (10 ** len(str(s.get("fpts_decimal", ""))))
        pa = float(s.get("fpts_against", 0)) + float(s.get("fpts_against_decimal", 0) or 0) / (10 ** len(str(s.get("fpts_against_decimal", ""))))
        wins, losses, ties = int(s.get("wins", 0)), int(s.get("losses", 0)), int(s.get("ties", 0))
        gp = wins + losses + ties
        winpct = round((wins + 0.5 * ties) / gp, 3) if gp else 0.0

        rows.append({
            "Team": team,
            "Owner": display or "—",
            "Wins": wins, "Losses": losses, "Ties": ties, "Win%": winpct,
            "PF": round(pf, 2), "PA": round(pa, 2)
        })

    return pd.DataFrame(rows).sort_values(by=["Wins", "PF"], ascending=[False, False]).reset_index(drop=True)

# Shiny App UI

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

# Server

def server(input, output, session):

    # ESPN Data
    @reactive.Calc
    @reactive.event(input.refresh, input.stat_type)
    def df_raw():
        stype = input.stat_type()
        if stype == "QB Passing":
            return scrape_espn_passing_with_selenium()
        elif stype == "RB Rushing":
            return scrape_espn_rushing_with_selenium()
        else:
            return scrape_espn_receiving_with_selenium()

    @reactive.effect
    def _populate_players():
        df = df_raw()
        ui.update_select("player1", choices=sorted(df["Name"].dropna().unique()))
        ui.update_select("player2", choices=sorted(df["Name"].dropna().unique()))

    @reactive.Calc
    def df_filtered():
        df = df_raw().copy()
        if input.team_select() != "All":
            df = df[df["Team"] == input.team_select()]
        if input.player_search():
            df = df[df["Name"].str.contains(input.player_search(), case=False)]
        return df

    # ESPN Outputs
    @output
    @render.data_frame
    def player_table():
        return df_filtered()

    @output
    @render.ui
    def chart_ui():
        df = df_filtered()
        if df.empty:
            return ui.p("No data to display.")

        if input.stat_type() == "QB Passing":
            x_stat, y_stat = "YDS", "TD"
            chart_title = "QB Passing: Yards vs Touchdowns"
        elif input.stat_type() == "RB Rushing":
            x_stat, y_stat = "YDS", "TD"
            chart_title = "RB Rushing: Yards vs Touchdowns"
        else:
            x_stat, y_stat = "YDS", "REC"
            chart_title = "WR Receiving: Yards vs Receptions"

        chart_obj = (
            alt.Chart(df)
            .mark_circle(size=100, opacity=0.7)
            .encode(
                x=alt.X(x_stat, title=x_stat, scale=alt.Scale(zero=False)),
                y=alt.Y(y_stat, title=y_stat, scale=alt.Scale(zero=False)),
                color=alt.Color("Team", legend=alt.Legend(title="Team")),
                tooltip=["Name", "Team", x_stat, y_stat]
            )
            .properties(title=chart_title, width=700, height=500)
            .interactive()
        )

        return ui.HTML(chart_obj.to_html())

    @output
    @render.data_frame
    def comparison_table():
        df = df_filtered()
        p1 = input.player1()
        p2 = input.player2()
        if not p1 or not p2:
            return pd.DataFrame()
        df1 = df[df["Name"] == p1]
        df2 = df[df["Name"] == p2]
        return pd.concat([df1, df2])

    # Fantasy League Tab
    @reactive.Calc
    def df_fantasy():
        league_id = 1180222056477925376
        return sleeper_rosters_df(str(league_id))

    @output
    @render.data_frame
    def fantasy_table():
        return df_fantasy()

# Run App
app = App(app_ui, server)

if __name__ == "__main__":
    print("Testing QB Passing scraper...")
    print(scrape_espn_passing_with_selenium().head())
