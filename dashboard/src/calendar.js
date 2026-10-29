// NYSE weekday closures and early closes, from exchange_calendars XNYS (the calendar the harness
// uses), read 2026-10-28. It ends 2027-10-28; after that only weekends are skipped.
// app/app.js carries the same two lists for the browser; change both together.
export const HOLIDAYS = new Set(["2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19",
  "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26",
  "2027-05-31", "2027-06-18", "2027-07-05", "2027-09-06"]);
export const EARLY_CLOSES = new Set(["2026-11-27", "2026-12-24"]); // 13:00 New York

export function isTradingDay(day) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(day || ""));
  if (!m) return false;
  const wd = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])).getUTCDay();
  return wd !== 0 && wd !== 6 && !HOLIDAYS.has(day);
}

// Minutes New York is ahead of UTC at instant t (negative: -240 in summer, -300 in winter).
function nyOffset(t) {
  const f = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hourCycle: "h23", year: "numeric",
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const p = Object.fromEntries(f.formatToParts(new Date(t)).map((x) => [x.type, x.value]));
  return (Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute, +p.second) - t) / 60000;
}

// The instant a New York wall-clock time on a given day happens, in ms since the epoch.
export function nyTime(day, hh, mm) {
  const [y, mo, d] = day.split("-").map(Number);
  const wall = Date.UTC(y, mo - 1, d, hh, mm);
  return wall - nyOffset(wall - 5 * 3600e3) * 60000;
}

export function sessionBounds(day) {
  return { open: nyTime(day, 9, 30), close: EARLY_CLOSES.has(day) ? nyTime(day, 13, 0) : nyTime(day, 16, 0) };
}
