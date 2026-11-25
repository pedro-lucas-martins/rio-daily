"""Build the static site and the newsletter from collected data."""
import json, shutil
from datetime import datetime
from urllib.parse import quote
from jinja2 import Environment, FileSystemLoader, select_autoescape
from .common import DATA, RIO_TZ, ROOT, config, load, norm, now, save
from . import review

LEVELS = {"red": "High", "orange": "Elevated", "yellow": "Moderate", "green": "Lower", "unknown": "Not enough data"}
TONES = {"bad": "Bad", "caution": "Heads-up", "good": "Good"}


def flight_view(hist, today):
    live = {}
    for h in hist:     # latest price for each trip
        if h["depart"] > today:
            live[(h["origin"], h["depart"], h["return"])] = h
    fresh = [h for h in live.values() if (now() - datetime.fromisoformat(h["found"])).days <= 15]
    by_day = {}
    for h in hist:
        d = h["found"][:10]
        by_day[d] = min(by_day.get(d, 10**9), h["price"])
    return sorted(fresh, key=lambda h: h["price"]), sorted(by_day.items())


def spark(series, w=640, h=160):
    if len(series) < 2:
        return ""
    lo, hi = min(p for _, p in series), max(p for _, p in series)
    f = lambda i, p: (40 + i * (w - 50) / (len(series) - 1), 15 + (hi - p) * (h - 40) / ((hi - lo) or 1))
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in (f(i, p) for i, (_, p) in enumerate(series)))


def context(hist=None, demo=False):
    cfg, n, z = config(), load("news.json", {"items": []}), load("zones.json", {"areas": []})
    items, areas, pending = review.apply(n["items"], z["areas"])
    today = now().astimezone(RIO_TZ)
    flights, series = flight_view(load("flights.json", []) if hist is None else hist, today.date().isoformat())
    sent = load("sent.json", {}).get("levels", {})
    for a in areas:
        a["was"] = sent.get(a["id"])
        a["label"] = LEVELS[a["level"]]
    for i in items:
        i["date"] = datetime.fromisoformat(i["when"]).astimezone(RIO_TZ).strftime("%d %b, %H:%M")
    c = cfg["site"]
    msg = "Rio Daily: news in English, hot zones and flights from Poland"
    group = c["group_email"]
    return {"site": c, "items": items, "areas": areas, "pending": len(pending), "flights": flights, "series": series, "points": spark(series),
            "alerts": [i for i in items if i["alert"]], "levels": LEVELS, "tones": TONES, "zones": z, "demo": demo, "cfg": cfg,
            "date": today.strftime("%A, %d %B %Y"), "updated": today.strftime("%d %b %Y, %H:%M"), "stale": n.get("errors", []) + z.get("errors", []),
            "share": "https://wa.me/?text=" + quote(msg + (" " + c["url"] if c["url"] else "")),
            "join": f"mailto:{group.replace('@', '+subscribe@')}?subject=Subscribe" if group else "",
            "leave": f"mailto:{group.replace('@', '+unsubscribe@')}?subject=Unsubscribe" if group else ""}


def build(out="site", hist=None, demo=False):
    ctx, dst = context(hist, demo), ROOT / out
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
