# Data Sources for Replicating Cohen & Frazzini (2008) Customer-Supplier Momentum

## A. Customer-Supplier Link Data

**SEC disclosure basis.** Under ASC 280 (formerly SFAS 131), a public company must disclose a "major customer" that accounts for >=10% of consolidated revenue — but only the **supplier discloses the customer's existence**, and often only as "Customer A" or a vague description, not always the legal name. There is no reciprocal requirement for the customer to name its suppliers. Same structural limitation the original academic literature had to work around.

**EDGAR full-text search (efts.sec.gov).** Free, individually accessible, covers filings back to 2001 (SEC states full-text search indexes filings submitted since 2001). Query phrases like "one customer accounted for," "major customer," or "10% of net sales" across 10-Ks/10-Qs. Technically feasible as a DIY pipeline, but it's a real engineering project, not a data feed: (1) hits are prose, not structured — must regex/NLP-extract the customer name from surrounding sentences; (2) XBRL tagging of segment/customer-concentration disclosures is inconsistent — customer identity rarely captured with a dimensional tag, so not reliably machine-readable even in XBRL; (3) must then entity-match extracted names (subsidiary/informal/omitted) to a CIK/ticker, which is error-prone and needs manual QA on a sample.

**Compustat Segments – Customer file (via WRDS).** Essentially the dataset the customer-supplier momentum literature relied on. Blocker: WRDS is licensed to academic/institutional subscribers; individual accounts are for enrolled students/faculty at subscriber universities, not independent retail quants. Realistically inaccessible to an individual without a university affiliation.

**Commercial enterprise vendors** (FactSet Revere Supply Chain Relationships, Bloomberg SPLC): both quantify customer/supplier/partner/competitor links (Bloomberg claims ~200k relationships) built from filings, transcripts, and press releases. Both require an existing FactSet or Bloomberg Terminal subscription (Bloomberg terminal ~USD 24k–30k/year per seat — approximate, verify) rather than being sold standalone/API-first to individuals; FactSet Revere pricing is quote-only. S&P Capital IQ and Refinitiv similarly bundle this into enterprise subscriptions. Not realistically accessible to a solo quant.

**Cheaper API-first vendors:** searched specifically (Financial Modeling Prep, others) and **found no cheap, individually-accessible, API-first supply-chain/customer-supplier relationship dataset**. FMP's public endpoint catalog has no such product as of this research. A genuine gap.

**Best cheap starting point:** DIY extraction from EDGAR full-text search — free and the only individually-accessible option, but budget real engineering time for text extraction + entity resolution, and expect a smaller, noisier link set than Compustat Segments Customer. Treat it as "build your own dataset," not "buy a dataset."

## B. Price/Return Data

For a monthly-rebalanced long/short strategy, what matters: (1) survivorship-bias-free universe (delisted names retained with correct delisting return), (2) split/dividend-adjusted total-return series, (3) point-in-time index/universe membership. None of the individual-tier vendors below fully replicate CRSP's delisting-return treatment — a real fidelity gap vs the original paper.

- **Polygon.io (rebranded "Massive," per search, ~Oct 2025)** — developer-first API; lower tiers (~$29/mo range per third-party reviews, unverified — check massive.com/pricing) offer years of daily aggregates; higher tiers add tick history back to ~2003. Verify adjustment methodology and delisted-ticker handling in docs.
- **Tiingo** — API-first, free tier + paid "Power" tier (~$30/mo, verify), advertises 30+ years of split/dividend-adjusted EOD history; commonly cited by independent quants as solid value.
- **EODHD (EOD Historical Data)** — broad coverage, tiers roughly $20–$60/mo (verify) plus commercial tiers; explicitly sells a **delisted-companies dataset**, the single most relevant feature for survivorship-bias avoidance among cheap vendors — but full fundamentals/dividends/splits for delisted names reliable only after ~2018; pre-2018 delisted names get EOD price only.
- **Alpha Vantage** — tiers roughly $50–$250/mo (verify) by requests/minute; split/dividend-adjusted daily series, but no dedicated delisted-securities product verified.
- **Nasdaq Data Link (formerly Quandl)** — historically hosted EOD US equity databases; current pricing/availability for a specific "End of Day US Stock Prices" product could not be verified — check data.nasdaq.com directly.
- **yfinance** — free, but unofficial (scrapes undocumented Yahoo endpoints), breaks without notice, and **Yahoo drops data once a ticker delists** — unsuitable for a survivorship-bias-free backtest.

**Best cheap starting point:** EODHD, because it is the only individual-accessible vendor here that explicitly sells delisted-company price history, the make-or-break feature for point-in-time backtesting. Pair it with your own point-in-time universe construction (reconstructing S&P/Russell membership from historical files) since none of these sell point-in-time index membership cheaply.

## Sources
- SEC EDGAR Full Text Search: https://www.sec.gov/edgar/search/
- SEC EDGAR Full Text Search FAQ: https://www.sec.gov/edgar/search/efts-faq.html
- FactSet Supply Chain Relationships: https://www.factset.com/marketplace/catalog/product/factset-supply-chain-relationships
- FactSet Supply Chain API: https://developer.factset.com/api-catalog/factset-supply-chain-api
- Bloomberg Supply Chain: https://www.bloomberg.com/professional/solutions/corporations/supply-chain/
- WRDS Account Types: https://wrds-www.wharton.upenn.edu/pages/about/wrds-account-types/
- Cohen & Frazzini (AQR): https://www.aqr.com/Insights/Research/Journal-Article/Economic-Links-and-Predictable-Returns
- Cohen & Frazzini working paper PDF: http://www.econ.yale.edu/~shiller/behfin/2006-04/cohen-frazzini.pdf
- Tiingo Pricing: https://www.tiingo.com/pricing
- EODHD Pricing: https://eodhd.com/pricing
- EODHD Delisted Companies Data: https://eodhd.com/financial-apis/delisted-stock-companies-data
- Massive (formerly Polygon.io) Pricing: https://massive.com/pricing
- Alpha Vantage Premium: https://www.alphavantage.co/premium/
- Financial Modeling Prep Pricing: https://site.financialmodelingprep.com/pricing-plans
- yfinance GitHub: https://github.com/ranaroussi/yfinance

## Uncertainties / Gaps
- Several vendor prices came from search summaries / third-party reviews, not pages fetched directly (some pricing pages 403'd or were JS-rendered) — **verify every number on the vendor's live pricing page before budgeting**; pricing may have shifted since knowledge cutoff.
- Could not verify current Nasdaq Data Link (Quandl) EOD US equities availability/pricing — unresolved.
- Could not find any cheap, API-first, individually-accessible customer-supplier link dataset. Worth a further narrow search (Databento, alt-data marketplaces, academic replication packages) before concluding none exists.
- None of the reviewed price vendors were verified to fully replicate CRSP-style delisting-return treatment — a known source of backtest divergence; needs its own validation.
- Polygon.io's rebrand to "Massive" (~Oct 2025) is after training cutoff — confirm company/product identity before relying on it.
