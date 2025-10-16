import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from shiny import App, ui, reactive, render

# =========================================================
# Scraper: ESPN QB Passing (requests + BeautifulSoup)
# =========================================================
def scrape_qb_stats():
    URL = "https://www.espn.com/nfl/stats/player/_/view/offense/table/passing"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    }

    resp = requests.get(URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    # LEFT table (rank + name + team)
    player_summary = {}
    for player_info_row in soup.select(".Table--fixed-left tbody tr.Table__TR"):
        row_index = player_info_row.get("data-idx")
        if not row_index:
            continue
        player_cells = player_info_row.select("td.Table__TD")
        rk = player_cells[0].get_text(strip=True) if player_cells else ""
        player_name_tag = player_info_row.select_one("a.AnchorLink")
        name = player_name_tag.get_text(strip=True) if player_name_tag else ""
        team_node = player_info_row.select_one(".athleteCell__teamAbbrev")
        team = team_node.get_text(strip=True) if team_node else ""
        player_summary[row_index] = {"RK": rk, "Name": name, "Team": team}

    # RIGHT table (stats)
    stat_headers = [th.get_text(strip=True) for th in soup.select(".Table__Scroller thead th")]
    header_positions = {h: i for i, h in enumerate(stat_headers)}

    desired_columns = ["POS","GP","CMP","ATT","CMP%","YDS","AVG","YDS/G","LNG","TD",
                       "INT","SACK","SYL","QBR","RTG"]

    player_stats = {}
    for stat_row in soup.select(".Table__Scroller tbody tr.Table__TR"):
        row_index = stat_row.get("data-idx")
        if not row_index:
            continue
        player_stats_cells = [td.get_text(strip=True) for td in stat_row.select("td.Table__TD")]
        player_stat_line = {
            h: (player_stats_cells[header_positions[h]] if h in header_positions and header_positions[h] < len(player_stats_cells) else "")
            for h in desired_columns
        }
        player_stats[row_index] = player_stat_line

    # Merge left + right
    merged_player_records = []
    for row_index in sorted(set(player_summary) | set(player_stats), key=lambda x: int(x)):
        merged_player_record = {**player_summary.get(row_index, {}), **player_stats.get(row_index, {})}
        merged_player_records.append(merged_player_record)

    order = ["RK","Name","Team","POS","GP","CMP","ATT","CMP%","YDS","AVG","YDS/G","LNG",
             "TD","INT","SACK","SYL","QBR","RTG"]
    df = pd.DataFrame(merged_player_records)
    df = df[[c for c in order if c in df.columns]]
    
    numeric_cols = ["GP","CMP","ATT","CMP%","YDS","AVG","YDS/G","LNG","TD","INT","SACK","SYL","QBR","RTG"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    
    return df

# =========================================================
# Scraper: ESPN RB Rushing (selenium)
# =========================================================
URL_RUSH = "https://www.espn.com/nfl/stats/player/_/stat/rushing"

def build_driver(headless=True):
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1400,1000")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

def click_show_more_until_done(driver, table_container, wait, pause=0.8, max_clicks=100):
    left_rows_css = ".Table--fixed-left tbody tr.Table__TR[data-idx]"

    def row_count():
        return len(table_container.find_elements(By.CSS_SELECTOR, left_rows_css))

    clicks = 0
    prev = row_count()

    while clicks < max_clicks:
        links = driver.find_elements(By.CSS_SELECTOR, "a.AnchorLink.loadMore__link")
        link = next((x for x in links if x.is_displayed() and x.is_enabled()), None)
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
            break
        prev = new
        clicks += 1

def scrape_espn_rushing_with_selenium(headless=True):
    driver = build_driver(headless=headless)
    wait = WebDriverWait(driver, 20)

    try:
        driver.get(URL_RUSH)
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.ResponsiveTable")))
        rushing_block = driver.find_elements(By.CSS_SELECTOR, "div.ResponsiveTable")[0]

        click_show_more_until_done(driver, rushing_block, wait)

        # LEFT
        player_summary = {}
        for row in rushing_block.find_elements(By.CSS_SELECTOR, ".Table--fixed-left tbody tr.Table__TR"):
            idx = row.get_attribute("data-idx")
            if not idx:
                continue
            tds = row.find_elements(By.CSS_SELECTOR, "td.Table__TD")
            rk = tds[0].text.strip() if tds else ""
            try:
                name = row.find_element(By.CSS_SELECTOR, "a.AnchorLink").text.strip()
            except:
                name = ""
            try:
                team = row.find_element(By.CSS_SELECTOR, ".athleteCell__teamAbbrev").text.strip()
            except:
                team = ""
            player_summary[idx] = {"RK": rk, "Name": name, "Team": team}

        # RIGHT
        stat_headers = [th.text.strip() for th in rushing_block.find_elements(By.CSS_SELECTOR, ".Table__Scroller thead th")]
        header_positions = {h: i for i, h in enumerate(stat_headers)}

        desired_columns = ["POS","GP","ATT","YDS","AVG","LNG","BIG","TD","YDS/G","FUM","LST","FD"]

        player_stats = {}
        for row in rushing_block.find_elements(By.CSS_SELECTOR, ".Table__Scroller tbody tr.Table__TR"):
            idx = row.get_attribute("data-idx")
            if not idx:
                continue
            cells = row.find_elements(By.CSS_SELECTOR, "td.Table__TD")
            texts = [c.text.strip() for c in cells]
            line = {}
            for h in desired_columns:
                pos = header_positions.get(h, None)
                line[h] = texts[pos] if (pos is not None and pos < len(texts)) else ""
            player_stats[idx] = line

        rows = []
        for idx in sorted(set(player_summary) | set(player_stats), key=lambda x: int(x)):
            rows.append({**player_summary.get(idx, {}), **player_stats.get(idx, {})})

        order = ["RK","Name","Team"] + desired_columns
        df_rushing = pd.DataFrame(rows)
        df_rushing = df_rushing[[c for c in order if c in df_rushing.columns]]

        # numeric conversion
        numeric_cols = ["GP","ATT","YDS","AVG","LNG","BIG","TD","YDS/G","FUM","LST","FD"]
        for col in numeric_cols:
            if col in df_rushing.columns:
                df_rushing[col] = pd.to_numeric(df_rushing[col], errors="coerce")

        return df_rushing

    finally:
        driver.quit()

# =========================================================
# Shiny UI
# =========================================================
teams = ["All", "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN",
         "DET", "GB", "HOU", "IND", "JAX", "KC", "LAC", "LAR", "LV", "MIA", "MIN",
         "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS"]

app_ui = ui.page_fluid(
    ui.h2("NFL Player Stats (ESPN Scraper)"),
    ui.input_select("stat_type", "Select Stat Type:", ["QB Passing", "RB Rushing"]),
    ui.input_select("team_select", "Select Team:", teams),
    ui.input_select("sort_by", "Sort By:", []),  # we will populate + set default in server
    ui.input_action_button("refresh", "Refresh Data"),
    ui.output_table("player_table")
)

# --- SERVER (replace your server() with this) ---
def server(input, output, session):

    # Populate Sort By choices + a default whenever stat_type changes
    @reactive.effect
    def _populate_sort_choices():
        if input.stat_type() == "QB Passing":
            choices = ["YDS", "TD", "INT", "QBR", "RTG"]
            default = "YDS"
        else:
            choices = ["YDS", "TD", "AVG", "YDS/G", "FUM"]
            default = "YDS"
        ui.update_select("sort_by", choices=choices, selected=default)

    # Fetch/refresh data when the button is clicked (and also on stat_type change)
    @reactive.Calc
    @reactive.event(input.refresh, input.stat_type)
    def df_raw():
        if input.stat_type() == "QB Passing":
            return scrape_qb_stats()
        else:
            # ⚠️ Selenium is brittle on Connect; consider converting this to requests+bs4
            return scrape_espn_rushing_with_selenium()

    # Filter + sort reactively whenever inputs change
    @reactive.Calc
    def df_filtered():
        df = df_raw().copy()

        # Filter
        selected_team = input.team_select()
        if "Team" in df.columns and selected_team != "All":
            df = df[df["Team"] == selected_team]

        # Sort (guard for None / invalid)
        sort_column = input.sort_by()
        if sort_column and sort_column in df.columns:
            # Ensure numeric sort when appropriate
            if df[sort_column].dtype == "O":
                df[sort_column] = pd.to_numeric(df[sort_column], errors="ignore")
            df = df.sort_values(by=sort_column, ascending=False, kind="mergesort")  # stable

        return df.reset_index(drop=True)

    @output
    @render.table
    def player_table():
        return df_filtered()
app = App(app_ui, server)

