# Research notes

Research done 28 Oct 2026. Every claim links to its source. The sources are a mix of academic papers,
student theses, news and data sites, so the weights below are a **starting point to be tested** in the
backtest (section 8), not settled facts.

---

## R1. What makes a stock worth buying

### What the evidence says

**Frontier and African markets in general**
- Value and momentum premiums were sizable across 21 frontier markets (2006–2016), in large and small
  stocks alike ([Quantpedia summary of the frontier-markets study](https://quantpedia.com/equity-factor-strategies-in-frontier-markets/)).
- A study of 375 blue-chip firms across 8 African markets over 23 years found the Fama-French five- and
  six-factor models explained returns best. Their factors include size, value, momentum, profitability,
  investment and liquidity ([Hearn et al., Int. Review of Financial Analysis, open access](https://eprints.soton.ac.uk/496110/)).
- Caution: across 23 frontier countries, only 38% of 167 published anomalies held up at the 5% level, and
  only 19% when weighted by company size ([same Southampton paper's frontier review](https://repository.essex.ac.uk/39612/1/1-s2.0-S1057521924006847-main.pdf)).
  So most "rules" found in papers don't survive. That's why we backtest our own.

**The NSE itself** (mostly university theses; small samples)
- Momentum: found on the NSE over a 12-year sample ([Karungu, Memba & Muturi 2018](https://core.ac.uk/download/234632405.pdf)),
  and specifically over **3–6 month** horizons ([Otinga 2017, Strathmore](https://su-plus.strathmore.edu/handle/11071/5597)).
- Value: mixed. One study found a significant value effect ([KCA University](https://repository.kcau.ac.ke/bitstreams/96f7dd35-9f05-4ef2-bdb6-a353bfea8c08/download));
  another found value portfolios of large caps lost money in 2010–2019 while momentum was positive but mixed
  ([Chakaya 2021, Strathmore](https://su-plus.strathmore.edu/items/e7031f65-a89f-46f2-bab7-86f4e3b9370d)).
- Dividend yield: one 2009–2018 study found high yield went with *lower* later returns
  ([AfricArXiv](https://africarxiv.ubuntunet.net/handle/1/497)). A high yield is often a falling price, so yield
  needs a check that earnings actually cover the dividend.
- Liquidity: matters, but isn't the main driver of returns ([Strathmore thesis, 2012–2016](https://su-plus.strathmore.edu/items/3c6c5c3d-1d75-4bf7-9089-c16efe60fc2b/full)).
  Its bigger role for us is practical: many counters trade a few hundred shares a day, so you can't get in or out.

### What this means for our scoring

| Factor | How we measure it | Starting weight | Why |
|---|---|---|---|
| **Liquidity** | average daily traded value (KES) over 60 days | **gate**, not points | below the threshold → "watch only", not ranked |
| Momentum | price return over the last 6 months, skipping the most recent month | 25 | strongest NSE evidence (3–6 month horizon) |
| Value | P/E and price-to-book, compared **within the sector** | 20 | strong in frontier studies, mixed on the NSE |
| Dividend | yield, only counted if EPS covers the dividend (payout ≤ 100%) | 20 | income matters to NSE investors; the cover check avoids yield traps |
| Quality | EPS growth and stability over recent years | 15 | profitability is a factor in the African study |
| Risk | lower 6-month volatility scores higher | 10 | protects against the wildest counters |
| News | events from Kenyan news (results, dividends, policy), capped | 7 | real information, but noisy |
| **Online opinion** | what people and analysts say on X, Reddit, YouTube | **3 (lowest)** | can nudge a score but can't decide a ranking |

Every factor score is 0–100, ranked against the other stocks. The final score is the weighted average.
The backtest (section 8) will check whether these weights beat simpler ones, such as momentum alone.

---

## R2. Market context and what drives each stock

### Kenya, October 2026 (affects every stock)
- Central Bank Rate held at **8.75%** on 7 Oct 2026 ([CBK](https://www.centralbank.go.ke/2026/10/07/mpc-retains-the-cbr-at-8-75-percent-3/)).
- Inflation **6.8%** in September, up from 6.6%, near the top of the 2.5–7.5% target band. CBK raised its
  2026 growth forecast to 5.0%. Main risks cited: energy prices and Middle East trade disruption
  ([Serrari](https://serrarigroup.com/kenya-central-bank-holds-rate-at-8-75-as-inflation-rises/),
  [People Daily](https://peopledaily.digital/business/cbk-holds-interest-rate-at-8-75-as-kenya-growth-forecast-rises-to-5)).
- NSE 20 up about 45% over twelve months, while trading volume fell last quarter
  ([Business Today, citing CMA](https://businesstoday.co.ke/nse-hits-record-ksh4-12t-despite-trading-slump)).
  After a big rally, value scores matter more.
- Bank dividends were strong for FY2025: Equity KES 5.75 final, KCB KES 3.00 final plus special, Co-op paid an
  interim; StanChart's annual dividend fell to KES 31 from 45 ([SIB 2026 Outlook](https://sib.co.ke/reports/wp-content/uploads/2026/02/SIB-2026-Outlook-Report-vf.pdf),
  [Mansa Markets tracker](https://www.mansamarkets.com/blog/dividends-declared-2026-kenya-nse-companies)).

**Macro things to watch in the news:** CBK rate decisions, inflation releases, the shilling, Treasury bill
and bond yields, fuel prices (EPRA's monthly review), the Finance Bill and excise duty changes, government
budget and debt news, IMF programme news, rainfall, and foreign investor flows.

### Drivers by sector
Sectors follow the NSE classification in the [2025 NSE dataset (Wanjawa, Mendeley, CC BY 4.0)](https://data.mendeley.com/datasets/2b63rx67xt/2).

| Sector | Main drivers | News to watch |
|---|---|---|
| Banking | interest rates and bond yields, bad-loan levels, credit growth, capital, dividends | CBK decisions, results, dividend announcements, bank tax changes |
| Telecom (SCOM) | M-Pesa growth, data revenue, Ethiopia losses, regulation, the shilling | CA and CBK rules, Ethiopia updates, tariffs, results |
| Insurance | claims, investment income (bond yields), premium growth | results, regulation (IRA), large claims |
| Agricultural (tea, coffee, avocado) | auction prices, weather, the shilling (exports in USD), costs | Mombasa tea auction prices, rainfall, export demand |
| Energy and Petroleum | power tariffs (EPRA), fuel margins and volumes, rainfall (hydro), government ownership | EPRA reviews, fuel prices, outages, privatisation news |
| Manufacturing | excise duty, input costs (fuel, grain), consumer demand, the shilling | Finance Bill, excise changes, commodity prices |
| Construction | infrastructure spending, housing, cement demand | budget, government projects, competition |
| Commercial and Services | consumer spending, tourism (TPSE, KQ), advertising (NMG, SGL, SCAN) | tourism numbers, fuel (KQ), ad market |
| Investment | value of the holdings, property market, discount to net asset value | asset sales, results |
| Investment Services (NSE) | market trading turnover | monthly turnover, new listings |
| REITs | rental income, occupancy, distributions | results, distributions, acquisitions |

### The watchlist: each counter's type and status

**Status key:** `rank` = scored normally · `watch` = shown but not ranked · `out` = excluded.
Price data on afx.kwayisi.org (28 Oct 2026) shows which counters actually traded.

| Ticker | Company | Sector | Type | Status | Notes |
|---|---|---|---|---|---|
| ABSA | Absa Bank Kenya | Banking | share | rank | |
| BKG | BK Group | Banking | share | rank | Rwandan bank, cross-listed: Rwanda's economy and franc matter |
| COOP | Co-operative Bank | Banking | share | rank | |
| DTK | Diamond Trust Bank | Banking | share | rank | regional (Tanzania, Uganda) |
| EQTY | Equity Group | Banking | share | rank | big regional exposure (DRC, Uganda, Rwanda) |
| FMLY | Family Bank | Banking | share | rank | newly listed in 2026 ([SIB](https://sib.co.ke/reports/wp-content/uploads/2026/02/SIB-2026-Outlook-Report-vf.pdf)); short price history |
| HFCB | HFCB Group (formerly HF Group) | Banking | share | rank | renamed 22 May 2026 ([Kenyan Wall Street](https://kenyanwallstreet.com/hf-group-rebrands-hfcb-group)) |
| HFCK | (old code for HFCB) | — | — | out | duplicate of HFCB; drop |
| IMH | I&M Holdings | Banking | share | rank | |
| KCB | KCB Group | Banking | share | rank | |
| NCBA | NCBA Group | Banking | share | rank | |
| SBIC | Stanbic Holdings | Banking | share | rank | |
| SCBK | Standard Chartered Kenya | Banking | share | rank | high payout; dividend cut in 2026 |
| SCOM | Safaricom | Telecom | share | rank | biggest stock on the NSE by far |
| BRIT | Britam | Insurance | share | rank | |
| CIC | CIC Insurance | Insurance | share | rank | |
| JUB | Jubilee Holdings | Insurance | share | rank | |
| KNRE | Kenya Re | Insurance | share | rank | state-controlled |
| LBTY | Liberty Kenya | Insurance | share | rank | |
| SLAM | Sanlam Allianz | Insurance | share | rank | |
| EGAD | Eaagads | Agricultural | share | rank | coffee; thin trading likely |
| KAPC | Kapchorua Tea | Agricultural | share | rank | tea prices; thin trading likely |
| KUKZ | Kakuzi | Agricultural | share | rank | avocados, macadamia |
| LIMT | Limuru Tea | Agricultural | share | rank | thin trading likely |
| SASN | Sasini | Agricultural | share | rank | tea and coffee |
| WTK | Williamson Tea | Agricultural | share | rank | tea prices |
| KEGN | KenGen | Energy | share | rank | hydro (rainfall), geothermal; state-controlled |
| KPLC | Kenya Power | Energy | share | rank | tariffs, government policy |
| KPLC-P4 | Kenya Power 4% preference | Energy | preference share | out | fixed-dividend instrument, not comparable |
| KPLC-P7 | Kenya Power 7% preference | Energy | preference share | out | same |
| KPC | Kenya Pipeline | Energy | share | rank | IPO at KES 9.00, listed 10 Mar 2026 ([HapaKenya](https://hapakenya.com/2026/03/11/kpc-debuts-on-the-nse-at-ksh-9-30-after-ksh-112b-ipo/)); short history |
| TOTL | TotalEnergies Marketing | Energy | share | rank | fuel margins set by EPRA |
| UMME | Umeme | Energy | share | rank | Ugandan power distributor; check current business status |
| AMAC | Africa Mega Agricorp | Manufacturing | share | rank | thin trading likely |
| BAT | BAT Kenya | Manufacturing | share | rank | excise duty, high payout |
| BOC | BOC Kenya | Manufacturing | share | rank | industrial gases; thin trading |
| CARB | Carbacid | Manufacturing | share | rank | carbon dioxide producer |
| EABL | East African Breweries | Manufacturing | share | rank | excise duty, barley costs |
| FTGH | Flame Tree Group | Manufacturing | share | rank | |
| SKL | Shri Krishana Overseas | Manufacturing | share | rank | recent small listing; business to research |
| UNGA | Unga Group | Manufacturing | share | rank | maize and wheat prices |
| CGEN | Car and General | Automobiles | share | rank | motorcycles and machinery |
| CRWN | Crown Paints | Construction | share | rank | |
| PORT | EA Portland Cement | Construction | share | rank | |
| ARM | ARM Cement | Construction | share | out | suspended since 2018, in receivership ([Business Daily](https://www.businessdailyafrica.com/bd/markets/capital-markets/long-drawn-receiverships-spook-investors-in-suspended-nse-stocks-5581834)) |
| BAMB | Bamburi Cement | Construction | share | out | suspended after the Amsons takeover in 2025 ([Cytonn](https://www.cytonn.com/uploads/downloads/kenyas-fy2025-2026-budget-review-cytonn-weekly-26-2025vf.pdf)) |
| CABL | East African Cables | Construction | share | out | suspended June 2025 ([Kenyan Wall Street](https://kenyanwallstreet.com/transcentury-east-african-cables-shares-suspended-ncba-share-price-hits-decade-high)) |
| DCON | Deacons East Africa | Services | share | out | suspended, in administration |
| EVRD | Eveready East Africa | Services | share | watch | penny stock |
| HBE | Homeboyz Entertainment | Services | share | watch | no recent trades shown |
| KQ | Kenya Airways | Services | share | rank | fuel prices, tourism, government support |
| LKL | Longhorn Publishers | Services | share | rank | textbook demand, curriculum |
| NBV | Nairobi Business Ventures | Services | share | watch | penny stock |
| NMG | Nation Media Group | Services | share | rank | advertising revenue |
| SGL | Standard Group | Services | share | rank | advertising revenue |
| SMER | Sameer Africa | Services | share | rank | |
| SCAN | WPP ScanGroup | Services | share | rank | advertising |
| TPSE | TPS Serena | Services | share | rank | tourism |
| UCHM | Uchumi | Services | share | watch | penny stock, restructuring |
| XPRS | Express Kenya | Services | share | rank | logistics |
| CTUM | Centum Investment | Investment | share | rank | trades at a discount to its assets |
| HAFR | Home Afrika | Investment | share | watch | penny stock |
| KURV | Kurwitu Ventures | Investment | share | watch | no recent trades shown |
| OCH | Olympia Capital | Investment | share | rank | |
| TCL | TransCentury | Investment | share | out | suspended June 2025 |
| NSE | Nairobi Securities Exchange | Investment Services | share | rank | earns from trading turnover |
| MSC | Mumias Sugar | Manufacturing | share | out | suspended since 2019 ([Kenyan Wall Street](https://kenyanwallstreet.com/why-mumias-sugar-was-suspended-from-trading-at-the-nse)) |
| ALP | ALP Industrial REIT | REIT | REIT (USD) | watch | listed 11 Mar 2026, **priced in US dollars** ([African Markets](https://www.african-markets.com/en/stock-markets/nse/alp-industrial-reit-debuts-on-nairobi-securities-exchange-after-115-oversubscribed-offer)) |
| LAPR | LAPTrust Imara I-REIT | REIT | REIT | watch | no recent trades shown |
| TRFC | TRIFIC Green USD I-REIT | REIT | REIT (USD) | watch | not verified yet; the name suggests US-dollar pricing |
| GLD | Absa NewGold ETF | ETF | gold ETF | out | tracks gold, not a company |
| SMWF | Satrix MSCI World Feeder | ETF | global ETF | out | tracks world stocks |

**Totals:** 52 `rank`, 9 `watch`, 11 `out`. The liquidity gate will move more `rank` counters to `watch`
each run, based on actual trading.

---

## R3. Data sources

### Prices
| Source | What | Allowed? | Plan |
|---|---|---|---|
| [Mendeley NSE datasets (Wanjawa)](https://data.mendeley.com/datasets/2b63rx67xt/2) | daily prices for all stocks, one file per year, 2007–2025, plus a sector list | **CC BY 4.0**: free to use with credit | load once for history |
| [afx.kwayisi.org/nse](https://afx.kwayisi.org/nse/) | latest prices and volume for every counter; per-stock pages with EPS, dividend per share, yield, market cap | robots.txt allows it with **`Crawl-delay: 60`** | one request per run for prices; stock pages fetched slowly (one a minute) once a week |
| [NSE website](https://www.nse.co.ke/) | official daily price list, announcements | robots.txt allows it | check the daily price list format; use it to verify |
| [NSE crawler on GitHub](https://github.com/kwoshvick/NSE-Stock-Price-Crawler) | prices 2006 to April 2022 | — | not needed; Mendeley covers the same years and goes further |
| NSE daily price list PDFs (`nse.co.ke/wp-content/uploads/27-OCT-26.pdf`) | every trading day, including 2026 | allowed | **scanned images, no text**: would need OCR |
| [MyStocks](https://live.mystocks.co.ke/) | daily price lists | price lists need a login; [terms](https://live.mystocks.co.ke/terms.php) forbid redistribution | not used |
| [StockAnalysis](https://stockanalysis.com/) | NSE price history | [terms](https://stockanalysis.com/terms-of-use/) ban scripts and scrapers | not used |
| [EODHD](https://eodhd.com/pricing) | end-of-day API; free plan: 20 calls a day, 20 a minute, 500 bonus, 1 year of history | official API, free key | **used for 2026.** Covers 69 Nairobi counters under its own codes (Safaricom = `SAFARI`). 14 days arrived 10x or 100x too high and are repaired on load. |

**2026 gap: filled** from EODHD on 28 Oct 2026 (61 calls). afx's main page marks NCBA as suspended
(28 Oct 2026), which still needs checking against an NSE notice.

The Mendeley data was itself scraped from MyStocks, which is licensed by the NSE, so we spot-check it
against afx and NSE figures. The credit line goes in the README.

### News
| Source | RSS feed | Rules | How we use it |
|---|---|---|---|
| Business Daily | yes (`/service/rss/bd/1939132/feed.rss`) | `ai-train=no`, `use=reference`, blocks ClaudeBot | **headline, link and short summary only**; full text never sent to AI |
| Nation | none found | same as Business Daily | headlines only, if at all |
| The Standard (business) | yes (`/rss/business.php`) | robots.txt allows all | headlines plus article text |
| Capital FM Business | yes (`capitalfm.africa/business/feed/`) | allowed (feeds and articles) | headlines plus article text |
| The Star | feed URL not working yet | robots.txt allows all | find a working feed or section page |
| Kenyan Wall Street | feed blocked (403) | site pages allowed, `/api/` blocked | read section pages politely |
| NSE announcements | — | allowed | results, dividends, suspensions |

Rule for the scraper: identify ourselves honestly in the User-Agent, wait between requests, and respect
each site's robots.txt and content signals.

---

## R4. Who to listen to online (lowest-weight factor)

Online opinion feeds only the 3-point "online opinion" factor. It is never shown as a reason to buy.

**Better-quality sources (research from licensed firms):**
- Licensed brokers' and investment banks' research: Standard Investment Bank (SIB), Cytonn weekly reports.
  Their reports are long-form and explain their reasoning, which is more useful than a "buy" tweet.
- [@NSE_PLC](https://x.com/nse_plc), the exchange's official account: announcements, not opinions.
- [NSEinsider](https://nseinsider.co.ke/) and the [Weekly Kenya Capital Market Brief](https://okutoyiwilson.substack.com/p/weekly-kenya-capital-market-brief-f2f): daily and weekly market summaries.

**Retail chatter (use with care):**
- [@NSE_Investors (Market Cap Trainers)](https://x.com/NSE_Investors): investor education mixed with promotion.
- r/Kenya threads on NSE stocks ([example mirror](https://reddit.sentinel-team.org/subreddits/Kenya/snapshots/2026-02-13T10%3A20%3A31.804977Z)).
  I found no dedicated Kenyan investing subreddit.
- YouTube: no channel with a track record turned up yet.

**Red flags to filter out:** accounts pushing WhatsApp or Telegram groups, referral links, "guaranteed"
returns, or unlicensed trading signals. Comments on price sites often promote paid groups.

**Still to do:** X search through Agent-Reach to find which Kenyan analysts are actually active and
discussing specific tickers. It isn't possible from this machine yet (see below).

---

## Open items
1. **X access.** `twitter-cli` can't read X cookies from Chrome on this PC (Windows cookie encryption), and
   no cookies are saved in Agent-Reach. It needs `TWITTER_AUTH_TOKEN` and `TWITTER_CT0` set, exported by Ryan
   from his own logged-in x.com session.
2. Verify TRFC (what it is, which currency) and UMME's current business status.
3. Check the format of the NSE's official daily price list.
4. Price-to-book needs book value per share, which afx doesn't show. Until a source is found, value uses P/E only.
