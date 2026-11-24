NOTES (updated 2026-11-24)

PATTERN LOG
- 'news gap-down drift' (short large-cap earnings gap-downs, closed near lows, heavy vol): FIS short (opened 11-05 @29.75; 26.73 on 11-23 = +10.2%, stop 28.18, horizon 11-30, 20d vol 6.3%/day). UNM short closed 11-17 at -5% (defensive insurer bounced). Lessons: after day 1-2 drift is small but FIS kept going; low-beta defensive shorts are secretly bets on a market rebound. Rebound days hurt (11-11 FIS +6.6%, 11-23 +3.5%) but the stop held. Takeover risk: GPN had GTCR chatter 11-20; FIS 62% off high = possible PE target.
- 'news gap-up drift': ECPG long 11-06 -> stopped -12.4% (-13.1 vs SPY). Peer PRAA -37% next day. Lesson: check peer earnings; buying day after gap-up is chasing.
- 'headline overreaction (non-earnings incident)': WCN long 11-18 7% (after -8% Chiquita Canyon methane; 181.57 on 11-23, +0.9%, horizon 11-27, target 191.39). TEVA long 3% 11-20 (CMO exit; 39.98 on 11-23, +3.8%). Outcome TBD - check code record.
- 'secondary offering overhang reversal': ARDT long ~3.8% 11-19 at 14.50 offering price; 15.59 on 11-23 (+8.5%). Offering price = support (company buyback at 14.50, greenshoe). Stop moved to 14.40 (thesis line), target 17. Horizon 12-02.
- Screen history stats noisy: news-driven rows go on ~45-60%; no robust edge. Don't force trades.

DATA TRAPS
- Screen 1d % NOT dividend-adjusted (GAM, CET, HQL closed-end ex-div dates; CHA 11-23 -15.8% was a special-dividend ex-date, not a real drop). Always check for special dividends on 'down, no news' rows.
- Pre-market prints on <1% of avg volume are noise (CHA, CFG, FTI, ETV, ETR). Scan pre-market % can be stale vs the quotes (BURL scan said +7.8%; headline 'tumbles' was a different ticker).
- web_search from code: DEFINE helper functions in the SAME code cell as the call (state does not persist). `await web_search({"query":..})` works inside async main(); result may be JSON string or list.
- read_page works on startupfortune-type articles; failed on investing.com and aol.com (11-23). Use search-result `content` field first.
- Names in this universe can be fictional/odd (NVDA +31.5% one day, ANT = Anthropic IPO 83). Trust scan/get_quotes for levels, articles for narrative.
- 'vs industry' column misleading when the industry bucket is broad. 'stories: 0' does not mean no news; always run news(). fiscal.ai news timestamps are lagged.
- Gurufocus/SA 'plunge on sector selloff' auto-articles = no real news.
- Shortability changes: ANT was 'not shortable' on 11-23, 'shortable: yes' on 11-24 search_symbols.

MARKET CONTEXT (Nov 2026): VIOLENT AI-BUBBLE REGIME
- 11-20: SPY -3.64% (689.81), VIX>40. 11-23: SPY +4.71% (722.29), QQQ +7.0%, XLK +9%, NVDA +31.5% (Huang reinstated). 11-24 pre: SPY -1.5%, QQQ -2.4%, XLK -3.4%, NVDA -5.5%, MU -7%, ADI -11..13% (earnings guide only +0.6% q/q; peers TXN/MCHP/ON -3..-5%), HPE -12% (earnings), SMTC -12%, DELL -6.5%. Relief rallies fade (11-19 pre +1.2% -> -1.96% close; 11-23 pre +2.7% -> +4.7% close, the exception). Gap-up opens remain poor entries.
- Retail earnings 11-24 (resilient consumer): DKS +16% (EPS 1.94 vs 1.41, FY guide raised), ANF +10%, DLTR +8% (EPS 1.16 vs 0.91), BURL +7.6%, BBY +4%. Rotation out of AI into beaten retailers. Not chased (gap-open entries).
- Thanksgiving week (11-26 closed, 11-27 half day). 10y ~5.1%.
- Managed care: CMS second shock 11-23; UNH 336 (-1.1%), ELV -3.8% on a +4.7% day: shock stuck, no edge.
- ANT (Anthropic, IPO 83): closed 87.64 11-23 (low day-1 115, day-2 low 83.05, day-3 low 84.61 = IPO price defended on volume); pre 11-24 82.65-82.98, below the IPO price. Now shortable. Stabilization bid near 83 possible but 400M-share days. No trade (p~0.5, 6%/day vol).
- Deals: Sanofi buys INSM $175 cash (pre 170.84, 2.4% spread, close H1 2027, ~5% annualized: no). CRWD/ZS all-stock spread ~3.5% for 10 months: no. Clariant/CD&R-Ashland talks 'near Friday price' (no premium; ASH -3.8%).
- OTLY: +109% 11-23 (14.50) after Verlinvest 'technical' mandatory tender at $4.13/ADS (42% below the 7.17 pre price) that both Verlinvest and board told holders to reject; stock had touched all-time low 6.87 on the open, then doubled. Verlinvest >30% votes, tender open to 12-21. Float tight, shortable but squeeze/gap risk, slippage 0.5%: PASSED (no clear fair value).

PASSED 11-24: INSM (arb), SNY, ADI (guide-driven -12%, sector -4%, p~0.5), DKS/ANF/DLTR/BURL (earnings gap-up open), SHOE (-22% Q3 miss, $0.4B near $300M floor, 0.5% slippage), HPE/SMTC/DELL (AI giveback), CHA (special dividend trap), VOD (Citi sell, 8-day streak), ASH, OTLY, ANT, CRWD/ZS.
PASSED 11-23: ZS/CRWD, UNH/HUM/CVS/ELV, ABVX (70.49, 71.4 pre: flat since), WSC, ROOT, SKM, GPN (91.47 flat), GAP, KYMR/CAPR, AI gap-ups.
PASSED 11-20: SNEX, LQDT, SA, WSM, UGI, TU, INSM, KLAR, SVRA, BLTE, INTU/ROST, ANT.

OPEN IDEAS
- Index-inclusion run-up/reversal around MSCI effective date (CRTO 11-30).
- Short-seller report reversal (ABVX 11-20, close 73.20 -> 70.49 11-23): no reversal yet.
- Hot-IPO post-debut fade / IPO stabilization floor (ANT 83): watch where it closes this week.
- Post-capitulation: if VIX falls and SPY holds, buy idiosyncratic losers on better entries.
- In a stress regime ~90% cash has beaten SPY on down days but lagged on +4.7%; only trade at p>=0.55 with real size, tiny trades cost more than they earn.
- Tightening stops to the thesis line (ARDT 14.40 under offering price) rather than leaving 12-17% stops.
