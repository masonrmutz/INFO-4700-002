# Done
import time
import pandas as pd

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- config ---
URL_PASSING = "https://www.espn.com/nfl/stats/player/_/stat/passing"

# --- helpers (identical pattern to your rushing script) ---
def build_driver(headless=True):
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1400,1000")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

def click_show_more_until_done(driver, table_container, wait, pause=0.8, max_clicks=100):
    """
    Click ESPN's 'Show More' link until it disappears or row count stops increasing.
    """
    left_rows_css = ".Table--fixed-left tbody tr.Table__TR[data-idx]"

    def row_count():
        return len(table_container.find_elements(By.CSS_SELECTOR, left_rows_css))

    def find_show_more():
        # Check inside table first
        local = table_container.find_elements(By.CSS_SELECTOR, "a.AnchorLink.loadMore__link")
        if local:
            return next((x for x in local if x.is_displayed() and x.is_enabled()), None)
        # Fallback: global page-level link
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

# --- PASSING scraper (your code pattern) ---
def scrape_espn_passing_with_selenium(headless=True):
    driver = build_driver(headless=headless)
    wait = WebDriverWait(driver, 20)

    try:
        driver.get(URL_PASSING)

        # Wait for ResponsiveTables
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.ResponsiveTable")))
        tables = driver.find_elements(By.CSS_SELECTOR, "div.ResponsiveTable")

        # Find the passing stats block
        passing_block = None
        for block in tables:
            link = block.find_elements(By.CSS_SELECTOR, 'thead a[href*="/stat/passing/"]')
            if link:
                passing_block = block
                break

        if passing_block is None:
            raise RuntimeError("Couldn't find the passing stats table on the page.")

        # Click "Show More" until all rows are loaded
        click_show_more_until_done(driver, passing_block, wait)

        # --- LEFT: rank + name + team ---
        player_summary = {}
        for row in passing_block.find_elements(By.CSS_SELECTOR, ".Table--fixed-left tbody tr.Table__TR"):
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

        # --- RIGHT: headers + stat rows ---
        stat_headers = [th.text.strip() for th in passing_block.find_elements(By.CSS_SELECTOR, ".Table__Scroller thead th")]
        header_positions = {h: i for i, h in enumerate(stat_headers)}

        desired_columns = ["POS","GP","CMP","ATT","CMP%","YDS","AVG","YDS/G","LNG","TD","INT","SACK","SYL","QBR","RTG"]

        player_stats = {}
        for row in passing_block.find_elements(By.CSS_SELECTOR, ".Table__Scroller tbody tr.Table__TR"):
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

        # --- MERGE + DataFrame ---
        rows = []
        for idx in sorted(set(player_summary) | set(player_stats), key=lambda x: int(x)):
            rows.append({**player_summary.get(idx, {}), **player_stats.get(idx, {})})

        order = ["RK","Name","Team"] + desired_columns
        df_passing = pd.DataFrame(rows)
        df_passing = df_passing[[c for c in order if c in df_passing.columns]]

        # Save & preview
        pd.set_option('display.max_rows', None)
        pd.set_option('display.max_columns', None)
        df_passing.to_csv("espn_passing.csv", index=False)
        print(df_passing)
        print("\nSaved to espn_passing.csv")

        return df_passing

    finally:
        driver.quit()

# --- run ---
if __name__ == "__main__":
    scrape_espn_passing_with_selenium(headless=True)

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
# WR DATA
URL_RECEIVING = "https://www.espn.com/nfl/stats/player/_/stat/receiving"

def scrape_espn_receiving_with_selenium(headless=True):
    driver = build_driver(headless=headless)
    wait = WebDriverWait(driver, 20)

    try:
        driver.get(URL_RECEIVING)

        # Wait for ResponsiveTables
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.ResponsiveTable")))
        tables = driver.find_elements(By.CSS_SELECTOR, "div.ResponsiveTable")

        # Find the receiving stats block
        receiving_block = None
        for block in tables:
            link = block.find_elements(By.CSS_SELECTOR, 'thead a[href*="/stat/receiving/"]')
            if link:
                receiving_block = block
                break

        if receiving_block is None:
            raise RuntimeError("Couldn't find the receiving stats table on the page.")

        # Click "Show More" until all rows are loaded
        click_show_more_until_done(driver, receiving_block, wait)

        # --- LEFT: rank + name + team ---
        player_summary = {}
        for row in receiving_block.find_elements(By.CSS_SELECTOR, ".Table--fixed-left tbody tr.Table__TR"):
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

        # --- RIGHT: headers + stat rows ---
        stat_headers = [th.text.strip() for th in receiving_block.find_elements(By.CSS_SELECTOR, ".Table__Scroller thead th")]
        header_positions = {h: i for i, h in enumerate(stat_headers)}

        # ESPN receiving stat columns
        desired_columns = [
            "POS","GP","REC","TGTS","YDS","AVG","YDS/G","LNG","TD","20+","40+","FUM","LST","FD","YAC","DROP","CTCH%"
        ]

        player_stats = {}
        for row in receiving_block.find_elements(By.CSS_SELECTOR, ".Table__Scroller tbody tr.Table__TR"):
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

        # --- MERGE + DataFrame ---
        rows = []
        for idx in sorted(set(player_summary) | set(player_stats), key=lambda x: int(x)):
            rows.append({**player_summary.get(idx, {}), **player_stats.get(idx, {})})

        order = ["RK","Name","Team"] + desired_columns
        df_receiving = pd.DataFrame(rows)
        df_receiving = df_receiving[[c for c in order if c in df_receiving.columns]]

        # Save & preview
        pd.set_option('display.max_rows', None)
        pd.set_option('display.max_columns', None)
        df_receiving.to_csv("espn_receiving.csv", index=False)
        print(df_receiving)
        print("\nSaved to espn_receiving.csv")

        return df_receiving

    finally:
        driver.quit()


if __name__ == "__main__":
    scrape_espn_receiving_with_selenium(headless=True)
# =========================================================
# Shiny UI
# =========================================================
teams = ["All", "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN",
         "DET", "GB", "HOU", "IND", "JAX", "KC", "LAC", "LAR", "LV", "MIA", "MIN",
         "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS"]

app_ui = ui.page_fluid(
    ui.h2("NFL Player Stats (ESPN Scraper)"),
    ui.input_select("stat_type", "Select Stat Type:", ["QB Passing", "RB Rushing", "WR Receiving"]),
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

