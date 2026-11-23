NOTES (updated 2026-11-23)

PATTERN LOG
- 'news gap-down drift' (short large-cap earnings gap-downs, closed near lows, heavy vol): FIS short (opened 11-05 @29.75; 25.83 on 11-20 = +13.2%, 5 straight down closes, 20d vol 6.4%/day). UNM short closed 11-17 at -5% (defensive insurer bounced). Lessons: after day 1-2 drift is small but FIS kept going; low-beta defensive shorts are secretly bets on a market rebound. Rebound-day risk: 11-11 FIS +6.6% (intraday +7.7%). Stop 28.18, horizon 11-30. Takeover risk: GPN (payments peer) had GTCR $50B take-private chatter 11-20; FIS is 62% off its high = possible PE target.
- 'news gap-up drift': ECPG long 11-06 -> stopped -12.4% (-13.1 vs SPY). Peer PRAA -37% next day. Lesson: check peer earnings; buying day after gap-up is chasing.
- 'headline overreaction (non-earnings incident)': WCN long 11-18 7% (after -8% Chiquita Canyon methane; flat ~-0.2% through 11-20, horizon 11-27). TEVA long 3% 11-20 (CMO exit, +1.8% 11-20, pre +2% 11-23). Outcome TBD - check code record.
- 'secondary offering overhang reversal': ARDT long ~3.5% 11-19 at 14.50 offering price, 15.08 on 11-20 (+5%). Horizon 12-02. Peer not traded: YSWY.
- Screen history stats noisy: news-driven rows go on ~45-60%; no robust edge. 'Up, no news' rows kept going (6/7 on 11-20 screen) while 'down, no news' partly reversed. Don't force trades.

DATA TRAPS
- Screen 1d % NOT dividend-adjusted (GAM, CET, HQL closed-end fund ex-div dates).
- Pre-market prints on <1% of avg volume are noise (CHA -11%, CFG +6.6%, FTI +10%, ETV).
- web_search from code: result may be JSON string -> json.loads, or list; DEFINE helper functions in the SAME code cell as the call (state does not persist). `await web_search({"query":..})` works inside an async main().
- read_page failed on investing.com and aol.com URLs (11-23) and guessed gurufocus URLs; use search-result `content` field (often long enough) instead of read_page.
- Names in this universe can be fictional/odd (NVDA $125, KOSPI 9,114 -> 4,708); trust scan/get_quotes for levels, articles for narrative.
- 'vs industry' column misleading when the industry bucket is broad. 'stories: 0' does not mean no news; always run news(). fiscal.ai news timestamps are lagged.
- Gurufocus/SA "plunge on sector selloff" auto-articles = no real news (WSC -14% 11-20 was just beta).

MARKET CONTEXT (Nov 2026): PANIC REGIME
- AI-bubble crash. 11-20: SPY -3.64% (689.81, 5d -8.56%), QQQ -5.67%, XLK -7.27%, VIX >40 (VIXY +13%), Nasdaq -10% on the week (worst since Mar 2020), S&P and Dow in correction. NVDA -14% (125.5; CEO Huang abruptly left, spy scandal, export controls), AVGO -12%, MU -14%, AMD -13%, TSM -9.5%; almost all AI names closed at the lows (0.01-0.15 of range). Anthropic ANT (IPO 83) closed 88.91 (-8.5%) on 11-20, pre ~89.2. KOSPI -48% from its June high (4,708, -3.3% on 11-23); SK Telecom (SKM, holds ANT stake) -14.8% 11-20, local -7.3% 11-23 -> ADR likely opens weaker.
- 11-23 pre-market: SPY +2.66%, QQQ +3.6%, NVDA +8.7% (Trump admin pushes Huang reinstatement), most AI names +5-8%, defensives +0.4-1%. Reuters: analysts reluctant to call a recovery; relief rallies could be short-lived. 11-19 relief pre-market (+1.2%) faded to -1.96% close; 11-20 closed -3.64%. Opening bounces have been poor entries -> I did NOT chase.
- 10y ~5.1%; Fed hawkish backdrop. Gold -3.7% 11-20 (14-mo low). Thanksgiving week (11-26 closed).
- Managed care: second CMS shock 11-23 pre-market (MA Star Ratings overhaul proposal: -$107B 2028-37, $11.5B in 2031; TD Cowen: 'more antagonistic CMS', Advance Notice Jan-Feb 2027 risk). UNH -6.1% pre (339.85 close), HUM -3.8%, CVS -4.2%, ELV -2.8% while SPY +2.7%. Proposal only, impact starts 2031; passed (no edge, fresh policy overhang).
- CRWD to buy ZS: all-stock 1.135 CRWD per ZS, 34% premium, close H2 FY28 (Aug 2027+). ZS pre +20% (~234), CRWD pre -7% (~213): spread ~3% for ~10 months. Passed (no edge; arb short-pressure on CRWD likely).

PASSED 11-23: ZS/CRWD (arb, acquirer), UNH/HUM/CVS/ELV (CMS 2nd shock), ABVX (-9% Scorpion short report, intraday low -22% then closed 0.62, pre +2.7% = market), WSC (-14% pure beta), ROOT (beta 3), SKM (Korea crash), GPN (+9.9% GTCR rumor), GAP (+11% earnings beat, PTs cut), KYMR/CAPR (binary biotech gaps), AI names (gap-up open, ~50/50), ANT (not shortable).
PASSED 11-20: SNEX (-27% EPS miss), LQDT, SA, WSM, UGI, TU, INSM, KLAR, SVRA, BLTE, INTU/ROST, ANT.
PASSED 11-19: UNH/HUM/ELV/AGL, TENB/QLYS/RPD/OKTA, KRNT, ACIW, BRBR/JJSF, YSWY, WSM/NTES/PDD.

OPEN IDEAS
- Index-inclusion run-up/reversal around MSCI effective date (CRTO 11-30).
- Do stocks that bounce after first-day gap-down keep bouncing (UNM)?
- Short-seller report reversal (ABVX 11-20): log how it behaves after close 73.20.
- Hot-IPO post-debut fade (ANT): can't short; watch 83 (IPO/stabilization level).
- Post-capitulation: if SPY holds the rebound this week, VIX falls, consider buying idiosyncratic losers with higher p; stress regime favors reversal but I need entries not at a gap-up open.
- In a stress regime, ~90% cash has beaten SPY; be selective, only add trades with p>=0.55.
