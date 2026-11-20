NOTES (updated 2026-11-20)

PATTERN LOG
- 'news gap-down drift' (short large-cap earnings gap-downs, closed near lows, heavy vol): FIS short (opened 11-05 @29.75; 25.94 on 11-19 = +12.8%, new lows nearly every day for 11 sessions). UNM short closed 11-17 at -5% (defensive insurer bounced). Lessons: after day 1-2 drift is small but FIS kept going; low-beta defensive shorts are secretly bets on a market rebound. FIS rebound-day risk: 11-11 it rose +6.6% (intraday +9%) on a market bounce. 11-20: tightened stop to +8% above price, horizon 11-27.
- 'news gap-up drift': ECPG long 11-06 -> stopped -12.4% (-13.1 vs SPY). Peer PRAA -37% next day. Lesson: check peer earnings; buying day after gap-up is chasing.
- 'headline overreaction (non-earnings incident)': WCN long 11-18 ~7% after -8% on Chiquita Canyon methane eruption (flat +0.3%; 11-19 -0.9% vs SPY -2%, so slightly outperforming in selloff; horizon 11-27). TEVA long 3% 11-20 after -8.7% on CMO resignation (round-tripped whole R&D-day rally). Outcome TBD - check code record.
- 'secondary offering overhang reversal': ARDT long ~3.5% 11-19 at 14.50 offering price (stock held 14.50 close 11-19 while hospitals -3%). Horizon 12-02. Peer not traded: YSWY.
- Screen history stats noisy: news-driven rows go on ~45-60%; no robust edge. 'Up, no news' rows kept going (6/8, 6/9, 4/7 same direction; +7.4%, +5.9%, -0.7% vs SPY) while 'down, no news' partly reversed (+1.4, +1.9, -0.25 vs SPY). Don't force trades.

DATA TRAPS
- Screen 1d % NOT dividend-adjusted (GAM, CET closed-end fund ex-div dates).
- Pre-market prints on <1% of avg volume are noise.
- web_search from code: result may be JSON string -> json.loads, or list; DEFINE helper functions in the SAME code cell as the call (state does not persist). `await web_search({"query":..})` works inside an async main().
- read_page failed on guessed gurufocus URLs; only use URLs exactly as returned by search.
- Names in this universe can be fictional/odd (NVDA $3.5T at $146, SPCX $1.9T); trust scan/get_quotes for levels, articles for narrative.
- 'vs industry' column misleading when the industry bucket is broad (cyber group 11-18).
- fiscal.ai news timestamps are lagged/mislabeled; 'fell on Nov 19' can mean Nov 18 session.
- 'stories: 0' on screen does not mean no news: INSM +20.6% had a Bloomberg takeover-rumor (Sanofi) story, TU +13% had a Quebecor bid + upgrade. Always run news() before calling a move 'no news'.

MARKET CONTEXT (Nov 2026)
- AI-bubble selloff, regime of stress: NVDA 145.98 (-40% from high, 6 down days, pre -3.2%), AMD -7.7% 11-19 and -6.4% pre, INTC/CRWV/IREN/WULF/SOFI all down streaks. SPY 715.87 (11-19, -1.96%, 5d -5.45%), pre -0.84%; QQQ pre -1.65%; Dow near correction. VIXY +12%. Anthropic IPO (ANT, priced 83, opened 111.5, closed 97.17 = +17%, $81B raise, largest ever) failed to calm AI fears; ANT pre-mkt ~85-87 (not shortable; IPO price 83 = stabilization level, FB-2012 analog risk). The 11-19 pre-market relief rally (SPY +1.2%) faded into a -1.96% close: relief rallies at the open have been poor entries; defensive rotation (XLP/XLU/XLV pre-market up).
- 10y ~5.1%. Iran/Hormuz tension in background. Gold -2.4% pre.
- Managed care: CMS CRUSH proposed rule (11-16): UNH 330.48 (-5.6% 11-19, 3.5x vol, pre +1.5%, TD Cowen upgrade to Buy PT 455), HUM/ELV/CVS pre +1-2%. Stabilizing. Passed again (Jan-2026 analog: flat for 2 months).
- 11-20 pre-open earnings: INTU -9.5% pre (beat but cut FY rev guide), ROST -6% pre (beat+raise yet falling), BJ -5.7%.

PASSED 11-20: SNEX (-27% EPS miss; downtrend; coin-flip), LQDT (-25% weak Q1 guide; small cap), SA (-29% KSM court ruling), WSM (-15% earnings, hold guide), UGI (-7.8% FY27 guide below), TU (bid), INSM (takeover rumor, priced), KLAR (Q3 loss), SVRA (-29% pre; FDA decision due 11-22), BLTE (-17% pre; FDA review extended to 5/2027), INTU/ROST (earnings gaps already in pre-market), ANT (not shortable, IPO-price support).
PASSED 11-19: UNH/HUM/ELV/AGL, TENB/QLYS/RPD/OKTA, KRNT, ACIW, BRBR/JJSF, YSWY, WSM/NTES/PDD.
PASSED 11-18: JD, BILL, ACM/ENR, TJX/LOW/TGT/GLBE, UNH, HZN, ABX/OMER/CSIQ.

OPEN IDEAS
- Index-inclusion run-up/reversal around MSCI effective date (CRTO 11-30).
- Do stocks that bounce after first-day gap-down keep bouncing (UNM)?
- Headline-incident drops in large caps (WCN, TEVA) and offering-overhang drops (ARDT, YSWY): log outcomes.
- ACIW: abrupt CEO exit - watch if it bounces.
- Hot-IPO post-debut fade (ANT): can't short; watch whether it breaks 83.
- Thanksgiving week 11-23..11-27 seasonality; opex Friday 11-20.
- In a stress regime, ~95% cash has beaten SPY by ~5 pts; be selective, only add trades with p>=0.55.
