# Athletic Apparel 10-K Analysis

**Ethan Park · November 2026**

A financial statement analysis of five athletic apparel and footwear companies
(Nike, Lululemon, Deckers, Under Armour, and Columbia Sportswear) built from
their 10-K filings. Python pulls the data from the SEC, SQL stores it and
calculates the ratios, Excel rebuilds the ratios independently to cross-check
the SQL results, and the original 10-K filings verify both.

The full findings are in **Ethan_Park_10-K_Analysis.pdf**.

---

## Files

| File | What it is |
|---|---|
| `sec_loader.py` | Python script that downloads annual 10-K data from SEC EDGAR and saves it to the database |
| `analysis.sql` | SQL that builds the `wide` and `ratios` views, runs data checks, and produces the analysis queries |
| `financials.db` | SQLite database with the downloaded data and views (ready to open) |
| `apparel_analysis.xlsx` | Excel workbook: ratio formulas, pivot tables, charts, company lookup, and the 10-K tie-out |

## How the pipeline works

1. **Python (`sec_loader.py`)** downloads every company's XBRL financial data
   from the SEC API, keeps only annual 10-K figures, and saves about 980 values
   to `financials.db`. The `LINE_ITEMS` dictionary maps each company's XBRL tags
   to standard line items, with backup tags in priority order for companies
   that changed tags over time.
2. **SQL (`analysis.sql`)** pivots the data into one row per company per year
   (`wide` view) and calculates the ratios (`ratios` view), then runs data
   checks and the 5-year scorecard.
3. **Excel (`apparel_analysis.xlsx`)** recalculates the ratios with its own
   formulas to cross-check SQL, and presents the results.
4. **Verification:** 14 line items were tied back to the FY2026 10-K filings
   for Deckers and Under Armour. All matched.

## Ratios calculated

| Category | Ratio | Formula |
|---|---|---|
| Profitability | Gross margin | (Revenue − Cost of revenue) / Revenue |
| | Net margin | Net income / Revenue |
| | ROE | Net income / Equity |
| Liquidity | Current ratio | Current assets / Current liabilities |
| | Quick ratio | (Current assets − Inventory) / Current liabilities |
| Leverage | Liabilities-to-equity | Total liabilities / Equity (Assets − Equity when total liabilities isn't reported) |
| Cash flow | Free cash flow | Operating cash flow − Capital expenditures |
| Growth | Revenue growth | Year-over-year change, using SQL's `LAG()` window function |

## Excel workbook sheets

| Sheet | Contents |
|---|---|
| wide | Raw data from SQL plus ratio formulas (IF/OR logic for missing data) and color scales |
| Liquidity | Current vs. quick ratio comparison and chart |
| Company Lookup | Dropdown tool using two-condition XLOOKUP and SUMIFS |
| Scorecard | Pivot table of 5-year average ratios, which matches the SQL results |
| Dashboard | Company selector using XLOOKUP |
| Revenue Trends | Pivot tables and revenue charts |
| Tied Out | Database figures tied to the FY2026 10-K filings |

## How to run it

1. Install Python 3 and the `requests` library: `pip3 install requests`
2. In `sec_loader.py`, set `USER_AGENT` to your name and email (the SEC
   requires it) and `DB_PATH` to where you want the database saved.
3. Run `python3 sec_loader.py`
4. Open `financials.db` in DB Browser for SQLite, paste `analysis.sql` into the
   Execute SQL tab, run it, and click Write Changes.

To just explore the results, open `financials.db` or `apparel_analysis.xlsx`
directly; no need to rerun the script.

## Data notes

- **Fiscal years** are labeled by the calendar year they ended in. The companies'
  fiscal years end in different months (Nike: May; Deckers and Under Armour:
  March; Lululemon: late January/early February; Columbia: December).
- **Restatements:** when a figure appeared in more than one filing, the most
  recently filed value was used.
- **Under Armour** changed its fiscal year-end in 2022; its 3-month transition
  period was excluded.
- **Nike's inventory:** Nike stopped using the `InventoryNet` tag after FY2011.
  A COUNT/GROUP BY check in SQL caught the gap, and backup tags recovered all years.
- **Columbia:** net income is unavailable for FY2022 in the SEC data pulled, so
  its net margin and ROE average FY2023–2025.

## How AI was used

I used Claude (Anthropic) as a coding assistant and tutor. AI wrote the first
versions of `sec_loader.py` and `analysis.sql` and guided later updates; I set
up and ran the pipeline, made my own changes (including adding inventory and
the quick ratio), wrote the Excel formulas, verified the data against the
10-K filings, and wrote the analysis. Details are in the "How I Used AI"
section of the memo.
