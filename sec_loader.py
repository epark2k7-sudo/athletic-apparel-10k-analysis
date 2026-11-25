"""
sec_loader.py
-------------
Downloads annual (10-K) financial statement data from the SEC's free XBRL API
and saves it into a SQLite database called financials.db.

How to run (from a terminal, in the folder with this file):
    pip install requests
    python sec_loader.py
"""

import sqlite3
import time
from datetime import date

import requests

# ---------------------------------------------------------------------------
# 1. SETTINGS - change these!
# ---------------------------------------------------------------------------

# The SEC requires you to identify yourself. Put your real name and email here.
USER_AGENT = "Your Name your.email@example.com"

# Companies to analyze (stock tickers). Pick 5-10 from the same industry.
# Athletic apparel & footwear:
#   NKE  = Nike                 (fiscal year ends May)
#   LULU = Lululemon            (fiscal year ends late Jan / early Feb)
#   UAA  = Under Armour         (switched from a Dec to a March year-end in 2022)
#   DECK = Deckers (HOKA, UGG)  (fiscal year ends March)
#   COLM = Columbia Sportswear  (fiscal year ends December)
TICKERS = ["NKE", "LULU", "UAA", "DECK", "COLM"]

DB_PATH = "financials.db"

# ---------------------------------------------------------------------------
# 2. LINE ITEM MAPPING
# Companies don't all use the same XBRL "tag" for the same thing, and some
# switched tags over the years. For each standard line item we list possible
# tags in priority order. For each year we use the first tag that has a value.
# Format:  "OurName": ("statement", [tag1, tag2, ...])
# ---------------------------------------------------------------------------
LINE_ITEMS = {
    # Income statement (values cover a full year)
    "Revenue": ("income", [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
    ]),
    "CostOfRevenue": ("income", [
        "CostOfRevenue",
        "CostOfGoodsAndServicesSold",
        "CostOfGoodsSold",
    ]),
    "OperatingIncome": ("income", ["OperatingIncomeLoss"]),
    "NetIncome": ("income", ["NetIncomeLoss"]),

    # Balance sheet (values are a snapshot on one date)
    "TotalAssets": ("balance", ["Assets"]),
    "CurrentAssets": ("balance", ["AssetsCurrent"]),
    "Inventory": ("balance", [
        "InventoryNet",
        "InventoryFinishedGoodsNetOfReserves",
        "InventoryFinishedGoods",
        "InventoryGross",
    ]),
    "TotalLiabilities": ("balance", ["Liabilities"]),
    "CurrentLiabilities": ("balance", ["LiabilitiesCurrent"]),
    "StockholdersEquity": ("balance", [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ]),

    # Cash flow statement (values cover a full year)
    "OperatingCashFlow": ("cashflow", ["NetCashProvidedByUsedInOperatingActivities"]),
    "CapEx": ("cashflow", ["PaymentsToAcquirePropertyPlantAndEquipment"]),
}

HEADERS = {"User-Agent": USER_AGENT}


# ---------------------------------------------------------------------------
# 3. DATABASE SETUP
# ---------------------------------------------------------------------------
def create_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS companies (
            cik     TEXT PRIMARY KEY,   -- SEC's ID number for the company
            ticker  TEXT,
            name    TEXT
        );

        CREATE TABLE IF NOT EXISTS line_items (
            item_id   INTEGER PRIMARY KEY,
            std_name  TEXT UNIQUE,       -- e.g. 'Revenue'
            statement TEXT               -- income / balance / cashflow
        );

        CREATE TABLE IF NOT EXISTS financials (
            cik         TEXT,
            item_id     INTEGER,
            fiscal_year INTEGER,
            value       REAL,
            period_end  TEXT,            -- the date the period ended
            filed_date  TEXT,            -- when the 10-K was filed
            source_tag  TEXT,            -- which XBRL tag the value came from
            PRIMARY KEY (cik, item_id, fiscal_year),
            FOREIGN KEY (cik) REFERENCES companies(cik),
            FOREIGN KEY (item_id) REFERENCES line_items(item_id)
        );
    """)
    for name, (statement, _tags) in LINE_ITEMS.items():
        conn.execute(
            "INSERT OR IGNORE INTO line_items (std_name, statement) VALUES (?, ?)",
            (name, statement),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# 4. DOWNLOADING FROM THE SEC
# ---------------------------------------------------------------------------
def get_ticker_map():
    """Returns {ticker: (cik, company name)} for every SEC-registered company."""
    url = "https://www.sec.gov/files/company_tickers.json"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return {
        row["ticker"]: (str(row["cik_str"]).zfill(10), row["title"])
        for row in resp.json().values()
    }


def get_company_facts(cik):
    """Downloads every XBRL fact a company has ever reported."""
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# 5. CLEANING
# ---------------------------------------------------------------------------
def annual_values(facts, tag, statement):
    """
    Pulls one tag's annual values out of the company facts JSON.
    Returns {fiscal_year: {"value", "end", "filed"}}.

    Cleaning rules:
      * Only use numbers from 10-K (annual) filings.
      * Income/cash flow items must cover roughly one year (350-380 days),
        which removes quarterly numbers.
      * Balance sheet items are snapshots, so they have no start date.
      * The same number shows up in several 10-Ks (prior years are repeated),
        so keep the most recently filed one (it includes any restatements).
      * Fiscal year = the calendar year the period ENDED in.
    """
    try:
        entries = facts["facts"]["us-gaap"][tag]["units"]["USD"]
    except KeyError:
        return {}  # this company never used this tag

    best = {}
    for e in entries:
        if not e.get("form", "").startswith("10-K"):
            continue

        end = date.fromisoformat(e["end"])

        if statement == "balance":
            if "start" in e:
                continue
        else:
            if "start" not in e:
                continue
            days = (end - date.fromisoformat(e["start"])).days
            if not 350 <= days <= 380:
                continue

        year = end.year
        if year not in best or e["filed"] > best[year]["filed"]:
            best[year] = {"value": e["val"], "end": e["end"], "filed": e["filed"]}
    return best


def extract_line_items(facts):
    """Returns a list of rows: (std_name, fiscal_year, value, end, filed, tag)."""
    rows = []
    for std_name, (statement, tags) in LINE_ITEMS.items():
        by_tag = {tag: annual_values(facts, tag, statement) for tag in tags}
        all_years = set().union(*[v.keys() for v in by_tag.values()])
        for year in sorted(all_years):
            for tag in tags:  # first tag in priority order that has this year
                if year in by_tag[tag]:
                    d = by_tag[tag][year]
                    rows.append((std_name, year, d["value"], d["end"], d["filed"], tag))
                    break
    return rows


def save_company(conn, cik, ticker, name, rows):
    conn.execute(
        "INSERT OR REPLACE INTO companies (cik, ticker, name) VALUES (?, ?, ?)",
        (cik, ticker, name),
    )
    item_ids = dict(conn.execute("SELECT std_name, item_id FROM line_items"))
    conn.executemany(
        """INSERT OR REPLACE INTO financials
           (cik, item_id, fiscal_year, value, period_end, filed_date, source_tag)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [(cik, item_ids[n], y, v, end, filed, tag) for n, y, v, end, filed, tag in rows],
    )
    conn.commit()


# ---------------------------------------------------------------------------
# 6. MAIN PROGRAM
# ---------------------------------------------------------------------------
def main():
    if "example.com" in USER_AGENT:
        print("Please put your name and email in USER_AGENT at the top of this file.")
        return

    conn = sqlite3.connect(DB_PATH)
    create_tables(conn)

    print("Looking up company IDs...")
    ticker_map = get_ticker_map()

    for ticker in TICKERS:
        if ticker not in ticker_map:
            print(f"  {ticker}: not found, skipping")
            continue
        cik, name = ticker_map[ticker]
        print(f"  {ticker} ({name})...", end=" ")
        facts = get_company_facts(cik)
        rows = extract_line_items(facts)
        save_company(conn, cik, ticker, name, rows)
        print(f"{len(rows)} values saved")
        time.sleep(0.2)  # be polite: the SEC allows max 10 requests/second

    conn.close()
    print(f"\nDone! Open {DB_PATH} and run the queries in analysis.sql.")


if __name__ == "__main__":
    main()
