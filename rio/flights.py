"""Round trips Poland-Rio (GIG) in PLN. Nothing is published unless every segment was checked."""
import calendar, os
from datetime import date, timedelta
from statistics import median
from .common import RIO_TZ, config, get, load, now, save

API = "https://serpapi.com/search.json"


def airports(option):
    """Every airport touched by one direction, from segments and layovers."""
    seq = []
    for s in option.get("flights", []):
        seq += [s["departure_airport"]["id"], s["arrival_airport"]["id"]]
    return seq + [x["id"] for x in option.get("layovers", [])]


def direction_ok(option, start, end, banned):
    segs = option.get("flights") or []
    if not segs or segs[0]["departure_airport"]["id"] != start or segs[-1]["arrival_airport"]["id"] != end:
        return False
    return not set(airports(option)) & set(banned)


def route(option):
    segs = option["flights"]
    return [segs[0]["departure_airport"]["id"]] + [s["arrival_airport"]["id"] for s in segs]


def options(resp):
    return sorted([o for k in ("best_flights", "other_flights") for o in resp.get(k, []) if o.get("price")], key=lambda o: o["price"])


def add_months(d, n):
    y, m = divmod(d.year * 12 + d.month - 1 + n, 12)
    return date(y, m + 1, min(d.day, calendar.monthrange(y, m + 1)[1]))


class Budget:
    """Counts requests before sending them, so failures also count."""
    def __init__(self, cfg):
        self.s, self.cfg = load("flight_budget.json", {}), cfg
        self.today = now().astimezone(RIO_TZ).date().isoformat()

    def take(self):
        m, d = self.today[:7], self.today
        if self.s.get(m, 0) >= self.cfg["monthly_request_limit"] or self.s.get(d, 0) >= self.cfg["requests_per_day"]:
            return False
        self.s = {m: self.s.get(m, 0) + 1, d: self.s.get(d, 0) + 1, "cursor": self.s.get("cursor", 0)}
        save("flight_budget.json", self.s)
        return True


def quote(origin, dep, ret, cfg, budget, key, fetch=None):
    fetch = fetch or (lambda p: get(API, params=p, timeout=120).json())
    banned, dest = cfg["excluded_airports"], cfg["destination"]
    base = {"engine": "google_flights", "departure_id": origin, "arrival_id": dest, "outbound_date": dep, "return_date": ret, "type": "1",
            "currency": "PLN", "gl": "pl", "hl": "en", "exclude_conns": ",".join(banned), "api_key": key}
    if not budget.take():
        return None
    first = fetch(base)
    if first.get("search_parameters", {}).get("currency") != "PLN":
        raise RuntimeError("SerpApi did not confirm PLN")
    for out in [o for o in options(first) if direction_ok(o, origin, dest, banned) and o.get("departure_token")][:2]:
        if not budget.take():
            return None
        second = fetch({**base, "departure_token": out["departure_token"]})
        for back in options(second):
            if direction_ok(back, dest, origin, banned):
                ins = first.get("price_insights", {})
                return {"origin": origin, "depart": dep, "return": ret, "price": back["price"], "out": route(out), "back": route(back),
                        "airlines": sorted({s["airline"] for o in (out, back) for s in o["flights"]}), "typical": ins.get("typical_price_range"),
                        "direct": len(out["flights"]) == len(back["flights"]) == 1, "found": now().isoformat()}
    return None


def is_drop(history, q, pct):
    """Compare only with the same origin and stay, over 60 days; needs 10 samples, else Google's typical range."""
    stay = lambda h: (date.fromisoformat(h["return"]) - date.fromisoformat(h["depart"])).days
    past = [h["price"] for h in history if h["origin"] == q["origin"] and stay(h) == stay(q)
            and h["found"] < q["found"] and h["found"] >= (now() - timedelta(days=60)).isoformat()]
    if len(past) >= 10:
        return q["price"] <= median(past) * (1 - pct) or q["price"] < min(past)
    return bool(q.get("typical")) and q["price"] < q["typical"][0]


def combos(cfg, today):
    return [(o, (d := add_months(today, m)).isoformat(), (d + timedelta(days=s)).isoformat())
            for m in cfg["months_ahead"] for s in cfg["stays"] for o in cfg["origins"]]


def collect():
    key, cfg = os.getenv("SERPAPI_KEY"), config()["flights"]
    if not key:
        return [], ["Flights: SERPAPI_KEY not set"]
    budget, hist, errors, new = Budget(cfg), load("flights.json", []), [], []
    todo = combos(cfg, now().astimezone(RIO_TZ).date())
    cur = budget.s.get("cursor", 0)
    for _ in range(cfg["requests_per_day"] // 2):
        o, d, r = todo[cur % len(todo)]
        cur += 1
        try:
            q = quote(o, d, r, cfg, budget, key)
        except Exception as e:
            errors.append(f"Flights {o}: {type(e).__name__}")   # never str(e): the URL holds the key
            break
        if q:
            q["drop"] = is_drop(hist, q, cfg["drop_alert"])
            hist.append(q)
            new.append(q)
    budget.s["cursor"] = cur % len(todo)
    save("flight_budget.json", budget.s)
    save("flights.json", [h for h in hist if h["found"] >= (now() - timedelta(days=180)).isoformat()])
    return new, errors
