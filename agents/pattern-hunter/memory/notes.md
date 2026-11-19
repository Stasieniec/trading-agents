NOTES (updated 2026-11-19)

PATTERN LOG
- 'news gap-down drift' (short large-cap earnings gap-downs, closed near lows, heavy vol): FIS short (opened 11-05 @29.75; 26.73 on 11-18 = +10.2%, still grinding 2-3%/day at lows); UNM short closed 11-17 at -5% (defensive insurer bounced). Lessons: after day 1-2 drift is small but FIS kept going; low-beta defensive shorts are secretly bets on a market rebound. FIS rebound-day risk: 11-11 it rose +6.6% (intraday +9%) on a market bounce, so keep stop >= +9% above.
- 'news gap-up drift': ECPG long 11-06 -> stopped -12.4% (-13.1 vs SPY). Peer PRAA -37% next day. Lesson: check peer earnings; buying day after gap-up is chasing.
- 'headline overreaction (non-earnings incident)': WCN long 11-18 ~7% after -8% on Chiquita Canyon methane eruption. 11-18 flat (+0.3%), pre-mkt -0.3%. Outcome TBD - check code record. Horizon ends 11-27.
- 'secondary offering overhang reversal' (NEW 11-19): ARDT long ~3.5% at the open after insiders sold 8M shs at 14.50 (-18% vs close), stock closed 14.40; fundamentals/PTs intact; buyback + greenshoe support. Peer example not traded: YSWY (secondary launched 11-18, -12.2%, AH -2.1%, price unknown). Test: does a supply-driven (not info-driven) offering gap-down recover within ~8 days?
- Screen history stats noisy: news-driven rows go on ~45-60%; no robust edge. Don't force trades.

DATA TRAPS
- Screen 1d % NOT dividend-adjusted (GAM, CET closed-end fund ex-div dates).
- Pre-market prints on <1% of avg volume are noise.
- web_search from code: result may be JSON string -> json.loads, or list; DEFINE helper functions in the SAME code cell as the call (state does not persist between runs - lost cells twice on 11-19).
- Names in this universe can be fictional/odd (HZN, CALM etc.); trust scan/get_quotes for levels, articles for narrative.
- The 'vs industry' column is misleading when the industry bucket is broad: the whole cybersecurity group (TENB +15.8, QLYS +12.9, OKTA +12.1, RPD +12.5, S +10.4, CRWD +7.9) rallied 11-18 on 'Java4Shell' vulnerability warnings + PANW earnings (AH +9%), so TENB's 'no-news +15.8%' was a sector move, not a reversal setup.
- Many news timestamps from fiscal.ai are mislabeled/lagged; 'UNH fell on Nov 19' in articles actually = Nov 18 session.

MARKET CONTEXT (Nov 2026)
- AI/semis rout: NVDA 150.96 (-38% from high, 5 down days), INTC -62% from high, QQQ 5d -4.5%, XLK 5d -6%. SPY 730.20 on 11-18 (5d -3.9%). 11-19 pre-mkt: SPY +1.2%, QQQ +2.1% on Anthropic IPO priced $83 (above $70-78 range), debut today (ticker ANT), PANW +9-10% on earnings. Hot-IPO euphoria + relief rally = poor entry at open; reversal trades pay in stress but shorting into sharp rebounds hurts.
- 10y ~5.1%. Iran/Hormuz tension in background. GLD -3.2%, XLE -3.3% on 11-18.
- Managed care: CMS CRUSH proposed rule (11-16) -> UNH -15%/2d, HUM -16%, ELV -7.6%, CVS -5.2%, hospitals HCA -5%, THC -3.8%. Passed (see UNH note).
- 11-19 pre-open earnings: PDD (+5.8% pre), BABA (-1.7%), WSM (-8.5%), NTES (-6%), WMT (-1%), WMG.

PASSED 11-19: UNH/HUM/ELV/AGL (CRUSH, heavy volume continuation risk, p~0.5), TENB/QLYS/RPD/OKTA (sector rally + PANW read-through, squeeze risk), KRNT (-23% after call reversal, $0.5B slippage), ACIW (-10%, CEO leaving for another public co; interim CFO; no guidance change - possible overreaction but CEO exit news drifts), BRBR/JJSF (earnings gap-ups, small caps), YSWY (offering, price unknown, thin), WSM/NTES/PDD (earnings gaps already in pre-market).
PASSED 11-18: JD, BILL, ACM/ENR, TJX/LOW/TGT/GLBE, UNH, HZN, ABX/OMER/CSIQ.
PASSED 11-17: HTHT, TSN, MOH/CNC/ELV, TU, CRTO, OFRM/BGIN/MFI.

OPEN IDEAS
- Index-inclusion run-up/reversal around MSCI effective date (CRTO 11-30).
- Do stocks that bounce after first-day gap-down keep bouncing (UNM)?
- Headline-incident drops in large caps (WCN) and offering-overhang drops (ARDT, YSWY): log outcomes.
- ACIW: abrupt CEO exit (to another public company, no fundamental warning) - watch if it bounces; if a similar setup recurs consider long.
- Managed-care: revisit after 2 stabilizing days; Jan-2026 analog (UNH -20% on CMS notice, then flat 2 months).
