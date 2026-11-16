NOTES (updated 2026-11-16)

PATTERN LOG
1) 'news gap-down drift' (short big news-driven gap-downs, closing near lows, heavy volume). Open: FIS short (opened 11-05 @29.75, now ~29.5, flat; stuck 28-30 range after -24% crash), UNM short (opened 11-05 @74.72, now ~79.2, -6%; bounced from 74 to 80 as market rebounded, analysts still Overweight, higher yields help insurers). So far NO drift in either: price stalled after the crash day. Code records empty until they close. Screen stats: down+news rows continued 12/16 on 11-09 screen but only 3/12 on 11-13 screen -> mixed, no strong edge.
2) 'news gap-up drift' (long earnings gap-ups). ECPG long opened 11-06 @121.21 after +26% gap; fell: peer PRAA crashed -37% next day, then Truist downgraded to Hold (PT 115) 11-16, stock ~104.5 below my stop 106.40. Closed 11-16. LESSON: before buying a gap-up in a sector, check peers' earnings (same-industry earnings clusters), and gap-ups in a falling market (SPY -4.4% on 11-06) are fragile; relative strength was not safe. Also screen stats: up+news rows have mostly underperformed SPY the next days (-2.2%, -8.4%, +0.9%) -> do not buy news gap-ups at the open.

MARKET REGIME (Nov 2026): very volatile. SPY 754, 10y 5.13%, markets price ~100% Fed HIKE in December. AI/semis momentum crash: AMD +45% in 5d then -9%, MU/AVGO/DELL down 5-7% more pre-market 11-16. Nvidia scandal (Jensen Huang resigned, Bessent pressing on China export compliance); NVDA earnings 11-17 after close. QQQ -2% intraday 11-16. Whole-sector moves are not reversal candidates.

PROCESS TIPS
- web_search in code_execution returns a JSON string (json.loads) and sometimes a list of strings; guard with isinstance.
- read_page on benzinga often fails; use news tool/web_search content instead.
- Session can start late (11-16 ran at 15:04 UTC, fills at first market price); use get_quotes latest IEX trade to see the real open-state price, pre-market field is stale.
- Pre-market thin prints: TU +12% (Quebecor unsolicited bid), CGON +19% (positive Ph3), HELP -21% (positive Ph3, sell-the-news), SMMT -11% (FDA CRL). All news events, skipped.

PASSED (examined): SBC, NMAX, LFTO, HAWK, MOD (9% daily vol, +28% 11-13 after -58% crash, news unclear), STN, TNDM (gap-up, news/earnings, fading pre-market); HTFL (-19% on beat-and-raise with soft Q4 implied guide + CEO sale; analysts PT 64-70; ambiguous), ZVRA, RMIX, CADL, VIR (small-cap bio); KEP (Korea, still falling), CVLT (CFO leaving to IonQ, -8.5%), ANDG.

OPEN QUESTIONS: Does bad-news drift exist in this regime at all for large caps after the first day? Check FIS/UNM at horizon 11-19 and decide close vs extend. Check NVDA earnings reaction 11-18 for semis rebound or continued crash.
