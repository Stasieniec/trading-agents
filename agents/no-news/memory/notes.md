Notes (2026-11-25): Strategy is price/volume only, no news access. Open trades: GKOS (entry 228.57) and CROX (entry 145.06), post-earnings-gap drift trades opened 10/29, CROX horizon ends 12/2. TJX (entry 137.15, 11/18), PDD (entry 82.46, 11/19), DKS (148.90, 11/24 +16% gap), SNY (50.38, 11/24 +6.6% gap). Closed: ZS (bought 11/23 on a +20% pre-market gap, stopped at -8.2% the same day, so the gap faded). INSM closed 11/25 (a deal).

Market state: violent regime. SPY 11/19 -1.96%, 11/20 -3.64%, 11/23 +4.71%, 11/24 -0.49%, 11/25 pre-market -1.9% (QQQ -2.9%). The AI/semis complex is crashing: NVDA -23.6% over 20d, MU -11% on 11/24 and -6.6% pre-market 11/25, SNDK, AMD, INTC all -6 to -11%. Rotation into healthcare and staples (XLV +3% on 11/24). My book is deliberately non-tech. Thanksgiving 11/26 (closed), 11/27 half day.

Rules of thumb:
(1) Don't chase pre-market spikes in thin small caps without news (SLS 11/17, 308% pre-market).
(2) The gap setup I trust is a gap on 3x+ volume after a decline, in a stock with a real market cap. Slippage there is 0.1-0.25%. Check that the gap is stock-specific against peers (TJX 11/18: HD/LOW down. PDD 11/19: BABA/JD/BIDU flat to down. DKS 11/24: NKE/ONON/DECK flat. SNY 11/24: AZN +1.1%, but the whole health sector was +3% that day, so the idiosyncratic part was about +7%).
(3) Shorting after a -6% to -20% gap with an unknown cause is a coin flip, so skip unless the pattern is clear (skipped ARDT, GLBE, NTES, WSM, INTU, ROST, UNH, ADI -13%, SHOE -22%, AMBA -34% pre-market 11/25, NTNX -14%, URBN -11%).
(4) Sector-wide surges (cybersecurity 11/18) are not stock-specific signals. Don't chase the leader after a 2-day +20% move.
(5) Pre-market counts shown in the digest are thin. Use 'shares as % of avg day' above about 10% as a minimum for believing a gap.
(6) The scan's 'vol x avg' can understate a spike when the 60-day average already includes an earlier spike (INSM). Check raw volume in get_history.
(7) Relative strength on a big down market day (stock up while SPY -2%) is a useful stock-specific signal: PDD 11/19, INSM 11/19, CROX/GKOS 11/16, TJX 11/20.
(8) A pre-market print at a round number (KYMR 150.00, +30%) can mean a buyout, where there's no alpha.
(9) Gap-drift trades opened 10/29 to 11/24 (CROX, GKOS, TJX, PDD, INSM, DKS, SNY) are all positive vs cost. But ZS 11/23 (+20% pre-market gap on a violent bounce day, 30% of avg volume) hit its -8% stop the same day. Size 4-5%, stop 8-9%.
(10) When a held name gaps through its target pre-market (INSM 11/24), act explicitly: trim and re-set stop/target from the new fill.
(11) Retail earnings week (11/18 TJX, 11/24 DKS/ANF/BURL/BBY gaps up, SHOE gap down): read-across inside the group. I avoid stacking more than 2 new names in one industry.
(12) Deal detector (INSM 11/24-25): a day on very heavy volume (79M shares, 36% of shares outstanding) with an open-to-close range under 0.5% and a flat pre-market the next day while SPY moves 2% is a cash deal. Close it. It had given +19% vs cost in 5 sessions after the first gap on 11/19 (20% surge on 14M shares, then 11/24 deal).
(13) Trailing stops: after a gap trade has held for a week, put the stop just under the post-gap lows (use get_history lows). Use extend, which measures stop/target from today's fill.

Open questions: Does SNY (pre-market 53.60) hold above 50.3? Does DKS hold above 150 (pre-market 153.3)? Do CROX (horizon 12/2, stop 146.91), GKOS (stop 231.25), TJX, PDD (stop 81.42) hold? CROX has been range-bound 150-164 for 4 weeks on falling volume, so the drift is probably over: close it at the 12/2 horizon unless it breaks 164 on volume.
