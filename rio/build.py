"""Build the static site and the newsletter from collected data."""
import json, shutil
from datetime import date, datetime
from urllib.parse import quote
from jinja2 import Environment, FileSystemLoader, select_autoescape
from .common import DATA, RIO_TZ, ROOT, config, load, norm, now, save
from . import review

LEVELS = {"red": "High", "orange": "Elevated", "yellow": "Moderate", "green": "Lower", "unknown": "Not enough data"}
TONES = {"bad": "Bad", "caution": "Heads-up", "good": "Good"}


def flight_view(hist, today):
    """Latest price per trip, cheapest first; only future trips checked in the last 15 days."""
    live = {}
    for h in sorted(hist, key=lambda h: h["found"]):
        if h["depart"] > today:
            live[(h["origin"], h["depart"], h["return"])] = h
    return sorted((h for h in live.values() if (now() - datetime.fromisoformat(h["found"])).days <= 15), key=lambda h: h["price"])


def watch_view(hist, watch):
    """One price series per watched trip: never mixes dates or origins."""
    out = []
    for w in watch:
        days = {}
        for h in sorted(hist, key=lambda h: h["found"]):
            if all(h[k] == w[k] for k in ("origin", "depart", "return")):
                days[h["found"][:10]] = h["price"]
        if days:
            s = sorted(days.items())
            out.append(dict(w, series=s, price=s[-1][1], day=s[-1][0], points=spark(s), low=min(days.values()), high=max(days.values()),
                            prev=s[-2] if len(s) > 1 else None, change=s[-1][1] - s[-2][1] if len(s) > 1 else None))
    return out


def spark(series, w=640, h=160):
    if len(series) < 2:
        return ""
    x = [date.fromisoformat(d).toordinal() for d, _ in series]   # real spacing: missing days leave a gap
    lo, hi = min(p for _, p in series), max(p for _, p in series)
    return " ".join(f"{10 + (a - x[0]) * (w - 20) / (x[-1] - x[0]):.1f},{15 + (hi - p) * (h - 30) / ((hi - lo) or 1):.1f}" for a, (_, p) in zip(x, series))


def context(hist=None, demo=False, watch=None):
    cfg, n, z = config(), load("news.json", {"items": []}), load("zones.json", {"areas": []})
    items, areas, pending = review.apply(n["items"], z["areas"])
    today = now().astimezone(RIO_TZ)
    hist = load("flights.json", []) if hist is None else hist
    flights = flight_view(hist, today.date().isoformat())
    watch = watch_view(hist, load("watch.json", []) if watch is None else watch)
    sent = load("sent.json", {}).get("levels", {})
    for a in areas:
        a["was"] = sent.get(a["id"])
        a["label"] = LEVELS[a["level"]]
    for i in items:
        i["date"] = datetime.fromisoformat(i["when"]).astimezone(RIO_TZ).strftime("%d %b, %H:%M")
    c = cfg["site"]
    msg = "Rio Daily: news in English, hot zones and flights from Poland"
    group = c["group_email"]
    return {"site": c, "items": items, "areas": areas, "pending": len(pending), "flights": flights, "watch": watch,
            "alerts": [i for i in items if i["alert"]], "levels": LEVELS, "tones": TONES, "zones": z, "demo": demo, "cfg": cfg,
            "date": today.strftime("%A, %d %B %Y"), "updated": today.strftime("%d %b %Y, %H:%M"), "stale": n.get("errors", []) + z.get("errors", []),
            "share": "https://wa.me/?text=" + quote(msg + (" " + c["url"] if c["url"] else "")),
            "join": f"mailto:{group.replace('@', '+subscribe@')}?subject=Subscribe" if group else "",
            "leave": f"mailto:{group.replace('@', '+unsubscribe@')}?subject=Unsubscribe" if group else ""}


def build(out="site", hist=None, demo=False, watch=None):
    ctx, dst = context(hist, demo, watch), ROOT / out
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir()
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html"]))
    env.filters["pln"] = lambda v: f"{v:,.0f} PLN".replace(",", " ")
    for page in ("index", "news", "zones", "flights", "about"):
        (dst / f"{page}.html").write_text(env.get_template(f"{page}.html").render(page=page, **ctx), encoding="utf-8")
    (dst / "newsletter.html").write_text(env.get_template("newsletter.html").render(page="mail", monday=now().astimezone(RIO_TZ).weekday() == 0, **ctx), encoding="utf-8")
    shutil.copytree(ROOT / "static", dst / "static")
    geo = json.loads((DATA / "bairros.geojson").read_text(encoding="utf-8"))
    where = {norm(b): a for a in ctx["areas"] for b in a["bairros"]}
    feats = []
    for f in geo["features"]:
        a = where.get(norm(f["properties"]["nome"]))
        if a:
            feats.append({"type": "Feature", "geometry": f["geometry"], "properties": {"bairro": f["properties"]["nome"], "name": a["name"], "level": a["level"], "label": a["label"], "why": a["why"], "id": a["id"]}})
    (dst / "static" / "zones.json").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False), encoding="utf-8")
    if not demo:
        save("zone_levels.json", {a["id"]: a["level"] for a in ctx["areas"]})
    return ctx
