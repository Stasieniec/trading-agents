General notes (session 1, 2026-10-30)
- Tool gotcha: web_search inside code_execution returns a STRING-like payload; printing it char by char blew up context. Parse with json.loads if str, and print only [:300] slices. Keep research output small.
- Digest date quirk: digest built 10-29 21:46 UTC; IEX 'latest trade' prices from after hours (e.g. INTC 76.43 vs close 92.07, AMZN 227 vs 243.79) show the overnight reaction BEFORE the open. Always compare last IEX trade vs close for after-hours earners.
- Session 1: no trades. Intel (-17..-22% AH on weak Q4 guide/PC TAM -12%, gross margin 38%) and Amazon (-7% AH, AWS +39% but FCF -$42B TTM, capex $220B) gapped; judged no clear edge after the gap. Big tech sold off after earnings (Alphabet -8% AH, Apple -6.6% AH per search snippets, unverified). NOW -27% on 10-29.
- Ideas to revisit: AMZN dip-buy if AWS-driven thesis holds; INTC drift; check whether post-earnings gap-downs in mega caps continue or revert (record outcomes here).
