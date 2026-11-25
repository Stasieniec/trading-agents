NOTES (updated 2026-11-25)

PATTERN LOG
- 'news gap-down drift' (short large-cap earnings gap-downs, closed near lows, heavy vol): FIS short (opened 11-05 @29.75; 27.13 on 11-24 = +8.8%, stop 28.18, horizon 11-30, pre 11-25 26.86). UNM short closed 11-17 at -5% (defensive insurer bounced). Lessons: after day 1-2 drift is small but FIS kept going; low-beta defensive shorts are secretly bets on a market rebound. Rebound days hurt (11-11 FIS +6.6%, 11-23 +3.5%) but the stop held. Takeover risk: GPN had GTCR chatter 11-20; FIS 60% off high = possible PE target.
- 'news gap-up drift': ECPG long 11-06 -> stopped -12.4% (-13.1 vs SPY). Peer PRAA -37% next day. Lesson: check peer earnings; buying day after gap-up is chasing.
- 'headline overreaction (non-earnings incident)': WCN long 11-18 7% (after -8% Chiquita Canyon methane; 183.89 on 11-24, +2.2%, extended 11-25 to 12-04, target 191.4). TEVA long 3% 11-20 (CMO exit; 40.10 on 11-24, +4.2%). Outcome TBD - check code record.
- 'secondary offering overhang reversal': ARDT long ~3.8% 11-19 at 14.50 offering price; 15.72 on 11-24 (+9.4%). Offering price = support. Stop 14.42, target 17, horizon 12-03.
- Screen history stats noisy: news-driven rows go on ~45-60%; no robust edge. BUT code table 11-24 screen: no-news UP rows reversed (only 3/10 went on, -1.76% vs SPY); no-news DOWN rows continued 8/10. Plausible regime effect (stress day: gap-ups fade, losers keep sliding). Two screens earlier showed the opposite (11-20: up-no-news +4.8%), so don't over-trust.

DATA TRAPS
- Screen 1d % NOT dividend-adjusted (GAM, CET, HQL closed-end ex-div dates; CHA 11-23 -15.8% was a special-dividend ex-date). Always check special dividends on 'down, no news' rows.
- Pre-market prints on <1% of avg volume are noise. Scan pre-market % can be stale vs quotes.
- web_search from code: DEFINE helper functions in the SAME code cell as the call (state does not persist). `await web_search({"query":..})` inside async main(); result may be JSON string or list. Gurufocus 'down X% without company news' auto-articles = no real info but they list sector peers (useful for sympathy check).
- read_page works on startupfortune-type articles; failed on investing.com and aol.com. Use search-result `content` first.
- Names in this universe can be fictional/odd (NVDA +31.5% one day, ANT = Anthropic IPO 83). Trust scan/get_quotes for levels.
- 'vs industry' column misleading when the bucket is broad. 'stories: 0' does not mean no news; always run news(). fiscal.ai timestamps lagged.
- Shortability changes day to day (ANT).

MARKET CONTEXT (Nov 2026): VIOLENT AI-BUBBLE REGIME
- 11-20 SPY -3.64% (689.81), VIX>40. 11-23 SPY +4.71% (722.29) NVDA +31.5%. 11-24 SPY -0.49% (718.78), QQQ -1.99%, XLK -3.26%, XLV +2.95%, XLP +1.66% (defensive rotation). 11-25 pre: SPY -1.9%, QQQ -2.9%, NVDA -5%, MU -6%, Kospi -6%, potential new tariffs, PCE/GDP at 8:30. 'Relief rallies fade' holds; gap-up opens remain poor entries.
- Thanksgiving: 11-26 closed, 11-27 half day. 10y ~5.1%. Soybean oil at 9-month lows (BG -8.6%, ADM -3.8%, DAR -6.9% on 11-24: biofuel margin fears, sector-driven, not a reversal).
- 11-24 after-close earnings reactions (gap-downs 11-25): AMBA -34% pre (Q4 guide $70-75M vs $112M consensus, MS downgrade); NTNX -12% pre (beat and unchanged guide, CEO Ramaswami stepping down, BofA to Neutral PT 62); URBN -12% pre (record Q3, comps +4.4% but disappointed). DY -18% on 11-24 (EPS miss/weak Q4 guide despite record backlog and $200M buyback; 566 -> 179 since June, relentless AI-infra unwind).
- ANT (Anthropic, IPO 83): closed 81.91 on 11-24 (first close below IPO price), pre 11-25 78.14. Stabilization bid broken. Not traded (p~0.5, 6%/day vol).
- Deals: Sanofi buys INSM $175 cash (Mizuho downgraded to neutral PT 175, spread ~2.4%: no). CRWD/ZS all-stock spread: no. OTLY tender: passed.

PASSED 11-25: AMBA short (chasing -34% gap, 0.5% slippage, ~8%/day vol), NTNX (CEO exit; research says info-driven drops keep drifting, p~0.45 long), URBN (-12% record quarter, gap entry), BG (-8.6% no company news but biofuel sector driven, 52w low, downtrend), DY (relentless downtrend despite beat), CELC (+18.5% no news, closed at high, but PTs 150-190 and biotech sector +3%: edge ~1.5% x small size not worth slippage), IMTX, KSS/ANF/DKS (gap-up chase), EMBC (+40% small cap), ANT.
PASSED 11-24: INSM (arb), SNY, ADI, DKS/ANF/DLTR/BURL, SHOE, HPE/SMTC/DELL, CHA, VOD, ASH, OTLY, ANT, CRWD/ZS.
PASSED 11-23: ZS/CRWD, UNH/HUM/CVS/ELV, ABVX, WSC, ROOT, SKM, GPN, GAP, KYMR/CAPR.
PASSED 11-20: SNEX, LQDT, SA, WSM, UGI, TU, INSM, KLAR, SVRA, BLTE, INTU/ROST, ANT.

OPEN IDEAS
- Index-inclusion run-up/reversal around MSCI effective date (CRTO 11-30).
- Short-seller report reversal (ABVX 11-20): no reversal yet.
- Hot-IPO post-debut fade / IPO stabilization floor (ANT 83 broken 11-24).
- Post-capitulation: if VIX falls and SPY holds, buy idiosyncratic losers on better entries.
- In stress ~90% cash has beaten SPY on down days but lagged on +4.7%; only trade at p>=0.55 with real size, tiny trades cost more than they earn.
- Tighten stops to the thesis line (ARDT 14.40 under offering price).
- Executive-exit overreaction: TEVA +4% so far; NTNX (CEO exit, beat/raise) is a test case - watch how it trades 11-25..12-03 to learn whether CEO exits with good results revert.
