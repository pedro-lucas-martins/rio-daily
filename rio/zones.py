"""Hot-zone score: ISP precinct statistics + Fogo Cruzado shootings + news."""
import csv, io, os
from datetime import datetime, timedelta
from .common import config, get, load, norm, now, save
import requests

ISP = "https://www.ispdados.rj.gov.br/Arquivos/BaseDPEvolucaoMensalCisp.csv"
ORDER = ["green", "yellow", "orange", "red"]
FC = "https://api-service.fogocruzado.org.br/api/v2"


def isp_series():
    """{cisp: {(year, month): {robbery, theft}}} for the last 24 published months."""
    rows = list(csv.DictReader(io.StringIO(get(ISP, timeout=180).content.decode("latin-1")), delimiter=";"))
    idx = lambda r: int(r["ano"]) * 12 + int(r["mes"]) - 1
    last = max(idx(r) for r in rows)
    out, num = {}, lambda v: int(v or 0)
    for r in rows:
        if idx(r) > last - 24:
            out.setdefault(int(r["cisp"]), {})[idx(r)] = {
                "robbery": num(r["roubo_rua"]), "theft": num(r["furto_transeunte"]) + num(r["furto_celular"]) + num(r["furto_coletivo"])}
    return out, last


def shootings():
    """Recency-weighted shootings per neighbourhood, last 30 days. None without credentials."""
    email, pw = os.getenv("FOGOCRUZADO_EMAIL"), os.getenv("FOGOCRUZADO_PASSWORD")
    if not (email and pw):
        return None
    r = requests.post(f"{FC}/auth/login", json={"email": email, "password": pw}, timeout=60)
    r.raise_for_status()
    h = {"Authorization": "Bearer " + r.json()["data"]["accessToken"]}
    city = next(c for c in get(f"{FC}/cities", headers=h, params={"cityName": "Rio de Janeiro"}).json()["data"] if norm(c["name"]) == "rio de janeiro")
    out, page, pages, today = {}, 1, 1, now()
    while page <= pages:
        d = get(f"{FC}/occurrences", headers=h, params={"idState": city["state"]["id"], "idCities": city["id"], "typeOccurrence": "all", "page": page,
                "initialdate": (today - timedelta(days=30)).date().isoformat(), "finaldate": today.date().isoformat()}).json()
        pages = d["pageMeta"]["pageCount"]
        for o in d["data"]:
            age = (today - datetime.fromisoformat(o["date"].replace("Z", "+00:00"))).days
            name = norm((o.get("neighborhood") or {}).get("name") or "")
            s = out.setdefault(name, {"count": 0, "weight": 0})
            s["count"] += 1
            s["weight"] += 0.5 ** (max(age, 0) / 10)
        page += 1
    return out


def percentile(values, v):
    """0 for the lowest of the group, 100 for the highest; all-equal gives 0."""
    return 100 * sum(x < v for x in values) / max(len(values) - 1, 1)


def level(score, cuts):
    return "red" if score >= cuts["red"] else "orange" if score >= cuts["orange"] else "yellow" if score >= cuts["yellow"] else "green"


def combine(parts, weights):
    """Weighted mean over available components; a missing source is not treated as zero crime."""
    have = {k: v for k, v in parts.items() if v is not None}
    return sum(weights[k] * v for k, v in have.items()) / sum(weights[k] for k in have)


def score(areas, cfg, series, last, shots, log, today):
    raw = []
    for a in areas:
        tot = lambda key, lo, hi: sum(series.get(c, {}).get(i, {}).get(key, 0) for c in a["cisps"] for i in range(lo, hi))
        rob, the = tot("robbery", last - 11, last + 1), tot("theft", last - 11, last + 1)
        w = lambda lo, hi: tot("robbery", lo, hi) + cfg["theft_weight"] * tot("theft", lo, hi)
        recent, before = w(last - 2, last + 1), w(last - 14, last - 11)
        change = (recent - before) / before if before else 0
        names = {norm(b) for b in a["bairros"] + a.get("aliases", [])}
        sh = None if shots is None else {k: sum(v[k] for n, v in shots.items() if n in names) for k in ("count", "weight")}
        events = [e for e in log.values() if a["id"] in e["areas"]]
        nw = sum(0.5 ** (max((today - datetime.fromisoformat(e["when"])).days, 0) / 7) for e in events)
        raw.append({"a": a, "rob": rob, "the": the, "vol": w(last - 11, last + 1), "change": change, "sh": sh, "nw": nw, "events": len(events)})
    out = []
    for r in raw:
        vol = percentile([x["vol"] for x in raw], r["vol"])
        trend = max(0, min(100, 50 + r["change"] * 100))
        t = cfg["own_trend_share"]
        parts = {"official": (1 - t) * vol + t * trend,
                 "shootings": None if shots is None else percentile([x["sh"]["weight"] for x in raw], r["sh"]["weight"]),
                 "news": min(100, r["nw"] * 20)}   # 5 fresh reports = maximum
        s = round(combine(parts, cfg["weights"]))
        lv = level(s, cfg["levels"])
        if r["a"].get("underreported"):   # few reports here do not mean little crime
            lv = "unknown" if shots is None else max(lv, level(parts["shootings"], cfg["levels"]), key=ORDER.index)
        why = [f"{r['rob']:,} street robberies and {r['the']:,} phone or pocket thefts reported in 12 months",
               f"{abs(r['change']):.0%} {'more' if r['change'] > 0 else 'fewer'} (weighted) in the last 3 months than a year earlier"]
        if r["sh"]:
            why.append(f"{r['sh']['count']} shootings recorded in 30 days")
        why.append(f"{r['events']} crime report{'s' if r['events'] != 1 else ''} in the news in 14 days")
        out.append({"id": r["a"]["id"], "name": r["a"]["name"], "bairros": r["a"]["bairros"], "score": s, "computed": lv,
                    "trend": "up" if r["change"] > .1 else "down" if r["change"] < -.1 else "flat", "why": why, "robbery": r["rob"], "theft": r["the"]})
    return sorted(out, key=lambda z: -z["score"])


def collect():
    c, errors = config(), []
    series, last = isp_series()
    try:
        shots = shootings()
    except Exception as e:
        shots = None
        errors.append(f"Fogo Cruzado: {type(e).__name__}")
    z = score(c["areas"], c["zones"], series, last, shots, load("crime_log.json", {}), now())
    prev = {x["id"]: x["computed"] for x in load("zones.json", {}).get("areas", [])}
    for a in z:
        a["previous"] = prev.get(a["id"])
    save("zones.json", {"updated": now().isoformat(), "official_until": f"{last // 12}-{last % 12 + 1:02d}", "has_shootings": shots is not None, "areas": z, "errors": errors})
    return z, errors
