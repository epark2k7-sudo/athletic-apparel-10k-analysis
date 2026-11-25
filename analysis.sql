-- ============================================================================
-- analysis.sql
-- Run these in DB Browser for SQLite (Execute SQL tab) after running
-- sec_loader.py. Run section 1 first, since it creates the views the rest uses.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- 1. BUILD THE VIEWS
-- The financials table is "long" (one row per number). This view pivots it
-- to "wide" (one row per company per year, one column per line item), which
-- makes ratio math easy.
-- ----------------------------------------------------------------------------
DROP VIEW IF EXISTS wide;
CREATE VIEW wide AS
SELECT
    c.ticker,
    f.fiscal_year,
    MAX(CASE WHEN li.std_name = 'Revenue'            THEN f.value END) AS revenue,
    MAX(CASE WHEN li.std_name = 'CostOfRevenue'      THEN f.value END) AS cost_of_revenue,
    MAX(CASE WHEN li.std_name = 'OperatingIncome'    THEN f.value END) AS operating_income,
    MAX(CASE WHEN li.std_name = 'NetIncome'          THEN f.value END) AS net_income,
    MAX(CASE WHEN li.std_name = 'TotalAssets'        THEN f.value END) AS total_assets,
    MAX(CASE WHEN li.std_name = 'CurrentAssets'      THEN f.value END) AS current_assets,
    MAX(CASE WHEN li.std_name = 'Inventory'          THEN f.value END) AS inventory,
    MAX(CASE WHEN li.std_name = 'TotalLiabilities'   THEN f.value END) AS total_liabilities,
    MAX(CASE WHEN li.std_name = 'CurrentLiabilities' THEN f.value END) AS current_liabilities,
    MAX(CASE WHEN li.std_name = 'StockholdersEquity' THEN f.value END) AS equity,
    MAX(CASE WHEN li.std_name = 'OperatingCashFlow'  THEN f.value END) AS operating_cash_flow,
    MAX(CASE WHEN li.std_name = 'CapEx'              THEN f.value END) AS capex
FROM financials f
JOIN line_items li USING (item_id)
JOIN companies  c  USING (cik)
GROUP BY c.ticker, f.fiscal_year;


-- Ratios view. In SQLite, dividing by zero or NULL gives NULL instead of an
-- error, so missing data just shows up as blank.
DROP VIEW IF EXISTS ratios;
CREATE VIEW ratios AS
SELECT
    ticker,
    fiscal_year,
    -- Profitability
    ROUND((revenue - cost_of_revenue) / revenue, 4)  AS gross_margin,
    ROUND(operating_income / revenue, 4)             AS operating_margin,
    ROUND(net_income / revenue, 4)                   AS net_margin,
    ROUND(net_income / total_assets, 4)              AS roa,
    ROUND(net_income / equity, 4)                    AS roe,
    -- Liquidity
    ROUND(current_assets / current_liabilities, 2)   AS current_ratio,
    ROUND((current_assets - inventory) / current_liabilities, 2) AS quick_ratio,
    -- Leverage. Some companies (e.g. Deckers) don't report a total
    -- liabilities line, so fall back to Assets - Equity.
    ROUND(COALESCE(total_liabilities, total_assets - equity) / equity, 2) AS liabilities_to_equity,
    -- Cash flow
    operating_cash_flow - capex                      AS free_cash_flow,
    ROUND(operating_cash_flow / net_income, 2)       AS cash_conversion  -- >1 = earnings backed by cash
FROM wide;


-- ----------------------------------------------------------------------------
-- 2. CHECK THE DATA
-- ----------------------------------------------------------------------------

-- What did we load?
SELECT * FROM companies;

-- How many years of data per company and line item? Look for gaps.
SELECT c.ticker, li.std_name, COUNT(*) AS years, MIN(fiscal_year) AS first, MAX(fiscal_year) AS last
FROM financials f
JOIN line_items li USING (item_id)
JOIN companies  c  USING (cik)
GROUP BY c.ticker, li.std_name
ORDER BY c.ticker, li.std_name;

-- Sanity check: Assets should equal Liabilities + Equity (where both exist).
SELECT ticker, fiscal_year, total_assets, total_liabilities + equity AS liab_plus_equity
FROM wide
WHERE total_liabilities IS NOT NULL
ORDER BY ticker, fiscal_year;


-- ----------------------------------------------------------------------------
-- 3. ANALYSIS QUERIES
-- ----------------------------------------------------------------------------

-- All ratios, last 5 years
SELECT * FROM ratios
WHERE fiscal_year >= (SELECT MAX(fiscal_year) - 4 FROM ratios)
ORDER BY ticker, fiscal_year;

-- Revenue in billions + year-over-year growth (LAG = previous row's value)
SELECT
    ticker,
    fiscal_year,
    ROUND(revenue / 1e9, 1) AS revenue_billions,
    ROUND((revenue - LAG(revenue) OVER w) / LAG(revenue) OVER w, 4) AS revenue_growth
FROM wide
WINDOW w AS (PARTITION BY ticker ORDER BY fiscal_year)
ORDER BY ticker, fiscal_year;

-- Who is most profitable? Rank companies by net margin in the latest year.
SELECT
    ticker,
    fiscal_year,
    net_margin,
    RANK() OVER (ORDER BY net_margin DESC) AS margin_rank
FROM ratios
WHERE fiscal_year = (SELECT MAX(fiscal_year) FROM ratios WHERE net_margin IS NOT NULL);

-- 5-year averages per company: a quick "scorecard"
SELECT
    ticker,
    ROUND(AVG(gross_margin), 4)   AS avg_gross_margin,
    ROUND(AVG(net_margin), 4)     AS avg_net_margin,
    ROUND(AVG(roe), 4)            AS avg_roe,
    ROUND(AVG(current_ratio), 2)  AS avg_current_ratio,
    ROUND(AVG(quick_ratio), 2)    AS avg_quick_ratio,
    ROUND(AVG(liabilities_to_equity), 2) AS avg_liabilities_to_equity
FROM ratios
WHERE fiscal_year >= (SELECT MAX(fiscal_year) - 4 FROM ratios)
GROUP BY ticker
ORDER BY avg_net_margin DESC;
