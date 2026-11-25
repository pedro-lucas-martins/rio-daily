"""Collect, filter, classify, translate and de-duplicate news."""
import calendar, hashlib, html, re, time
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from urllib.parse import quote_plus
import feedparser
from .common import config, get, has, load, norm, now, save
from .translate import translate

CRIME = ["assalt*", "roub*", "furt*", "arrastao", "tiro", "tiros", "tiroteio*", "balead*", "bala perdida", "assassin*", "homicid*",
         "morto*", "morta*", "mata", "matou", "sequestr*", "golpe*", "estupr*", "latrocinio*", "faca", "esfaquead*", "dopad*", "boa noite cinderela",
         "robbed", "robber*", "shooting*", "shot", "murder*", "killed", "theft*", "mugg*", "scam*", "stabb*"]
TROUBLE = ["acidente*", "incendio*", "afogament*", "afogad*", "desabament*", "deslizament*", "dengue", "surto", "improprias", "impropria"]
CAUTION = ["greve*", "temporal", "chuva*", "ressaca", "interdit*", "interdic*", "fechad*", "alerta*", "atraso*", "cancelad*", "suspens*",
           "previsao", "paralisac*", "calor", "manifestac*", "protesto*", "strike*", "storm*", "closed", "operacao policial"]
GOOD = ["festival", "exposicao", "show", "shows", "reabre", "reabert*", "inaugur*", "gratuit*", "recorde", "premi*", "eleit*", "abre", "abert*",
        "queda", "caem", "cai", "reduc*", "novo", "nova", "carnaval", "reveillon", "celebr*", "opens", "free", "award*", "record"]
TOURIST = ["turis*", "estrangeir*", "gring*", "hotel", "hoteis", "hostel", "praia*", "aeroporto", "galeao", "santos dumont", "metro", "vlt", "brt",
           "museu*", "cristo redentor", "corcovado", "pao de acucar", "bondinho", "festival", "exposicao", "show", "shows", "reveillon", "carnaval",
           "linha vermelha", "linha amarela", "temporal", "chuva*", "ressaca", "calor", "greve*", "maracana", "trilha*", "lapa",
           "tourist*", "tourism", "beach*", "airport", "visitor*", "hotels", "museum*", "flights"]
CITY = ["rio de janeiro", "no rio", "do rio", "ao rio", "pelo rio", "em rio", "rio", "rj", "carioca*", "pier maua", "museu do amanha"]
# Elsewhere in the state or country: drop unless a Rio area is also named.
ELSEWHERE = ["niteroi", "sao goncalo", "baixada fluminense", "duque de caxias", "nova iguacu", "belford roxo", "marica", "buzios", "cabo frio", "angra*",
             "paraty", "petropolis", "volta redonda", "campos dos goytacazes", "macae", "rio grande do sul", "rio grande do norte", "sao paulo", "salvador",
             "fortaleza", "recife", "bahia", "campo grande news", "rio branco", "rio preto", "ponta negra", "rio claro", "teresopolis", "rio das ostras", "rio verde", "ubatuba", "jatai", "litoral paulista", "litoral de sp", "sp", "rs", "ms", "mg", "bahia", "saquarema", "vilatur", "cepilho", "alagoas", "suica", "itaborai", "sul fluminense"]
OLD = ["relembre", "ha anos", "julgamento", "condenad*", "novela", "filme", "eleicoes", "audiencia", "julgad*", "base aerea", "governador", "maio", "maiô", "biquini", "fotos", "famosos", "votos", "cocaina", "frascos", "droga*", "sommelier*", "doacao de sangue"]
DEADLY = ["morto*", "morta*", "mata", "matou", "assassin*", "homicid*", "latrocinio*", "balead*", "killed", "murder*", "shot", "tiroteio*", "arrastao"]


def area_names(area):
    return area["bairros"] + area.get("aliases", [])


def find_areas(text, areas):
    """Match capitalised names in the original text: avoids 'lagoa', 'centro' or 'saúde' as common words."""
    risky = {"Centro": r"(no|do|ao|o) Centro( do Rio)?\b|Centro do Rio", "Saúde": r"bairro da Saúde", "Lagoa": r"(na|da) Lagoa\b(?! Santa)",
             "Portuguesa": r"bairro Portuguesa", "Flamengo": r"(Praia|Aterro|bairro) do Flamengo", "Botafogo": r"(Praia de|em|bairro de) Botafogo",
             "Glória": r"(na|da) Glória", "Vasco da Gama": r"bairro Vasco da Gama", "Barra da Tijuca": r"Barra da Tijuca", "Tijuca": r"(?<!Barra da )(?<!Unidos da )Tijuca"}
    return [a["id"] for a in areas
            if any(re.search(rf"\b(?:{risky.get(n, re.escape(n))})(?!\w)", text) for n in area_names(a))]


def relevant(text, areas):
    n = norm(text)
    if has(n, OLD):
        return False
    if has(n, ELSEWHERE) and not areas:
        return False
    if not (areas or has(n, CITY)):
        return False
    return bool(areas and has(n, CRIME + CAUTION + TROUBLE + GOOD)) or has(n, TOURIST)


def classify(text):
    """good / caution / bad. Mixed or unclear signals become caution."""
    n = norm(text)
    bad, good = has(n, CRIME + TROUBLE), has(n, GOOD)
    if bad and has(n, ["queda", "caem", "cai", "reduc*"]):
        return "caution"
    if bad:
        return "bad"
    if has(n, CAUTION):
        return "caution"
    return "good" if good else "caution"


def grave(text, areas):
    n = norm(text)
    return has(n, DEADLY) and bool(areas or has(n, ["turis*", "tourist*", "estrangeir*"]))


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def fetch(cfg, errors):
    feeds = [dict(f, google=False) for f in cfg["feeds"]]
    feeds += [{"name": "Google News", "google": True, "url":
               f"https://news.google.com/rss/search?q={quote_plus(q + ' when:%dd' % cfg['max_age_days'])}&hl=pt-BR&gl=BR&ceid=BR:pt-419"}
              for q in cfg["google_queries"]]
    ok = 0
    for f in feeds:
        try:
            if f["google"]:
                time.sleep(3)     # Google refuses quick bursts
            try:
                body = get(f["url"]).content
            except Exception:
                time.sleep(20)
                body = get(f["url"]).content
            entries = feedparser.parse(body).entries
            ok += 1
        except Exception as e:
            errors.append(f"{f['name']}: {type(e).__name__}")
            continue
        for e in entries:
            if not e.get("published_parsed"):
                continue
            when = datetime.fromtimestamp(calendar.timegm(e.published_parsed), timezone.utc)
            title, source, snippet = clean(e.title), f["name"], ""
            if f["google"]:
                source = clean((e.get("source") or {}).get("title", "")) or "Google News"
                title = re.sub(rf"\s+-\s+{re.escape(source)}$", "", title)
            else:
                snippet = " ".join(re.split(r"(?<=[.!?])\s+", clean(e.get("summary")))[:2])[:320]
            if not str(e.link).startswith(("https://", "http://")):
                continue
            yield {"title": title, "source": source, "snippet": snippet, "url": e.link, "when": when,
                   "lang": f.get("lang", "pt"), "must": f.get("must_mention_rio", False)}
    if not ok:
        raise RuntimeError("all news feeds failed")


def same_story(a, b):
    A, B = ({w for w in norm(x).split() if len(w) > 3} for x in (a, b))
    return (len(A & B) / max(min(len(A), len(B)), 1) >= .55 and len(A & B) >= 3) or SequenceMatcher(None, norm(a), norm(b)).ratio() > .75


def same_death(a, b):
    """Follow-ups on one killing of a tourist: only merged when the reports agree on tourist + death + a detail."""
    A, B = norm(a), norm(b)
    both = lambda w: has(A, w) and has(B, w)
    return both(["turis*", "influenc*"]) and both(["mort*", "morre*", "assassin*", "matou"]) and (both(["american*", "norte americano", "eua"]) or len(
        {w for w in A.split() if len(w) > 4} & {w for w in B.split() if len(w) > 4}) >= 3)


def collect():
    full = config()
    cfg, areas, errors = full["news"], full["areas"], []
    cutoff = now() - timedelta(days=cfg["max_age_days"])
    cache = load("translations.json", {})
    picked = []
    for it in sorted(fetch(cfg, errors), key=lambda x: x["when"], reverse=True):
        if not cutoff <= it["when"] <= now() + timedelta(hours=1) or any(b in it["source"].lower() for b in cfg["blocked_sources"]):
            continue
        if len(it["title"]) > 180:   # social posts and scraped captions
            continue
        text = f"{it['title']}. {it['snippet']}"
        it["areas"] = find_areas(it["title"], areas)
        if it["must"] and not (it["areas"] or has(norm(it["title"]), CITY)):
            continue
        if not relevant(it["title"], it["areas"]):
            continue
        dup = next((p for p in picked if same_story(p["title"], it["title"]) or same_death(p["title"], it["title"])), None)
        if dup:
            dup["also"] = dup.get("also", 0) + 1
            continue
        it["tone"], it["grave"] = classify(text), grave(text, it["areas"])
        it["crime"] = has(norm(text), CRIME)
        picked.append(it)
    out, dropped, counts = [], 0, {}
    for it in picked:
        if counts.get(it["tone"], 0) >= cfg["max_per_tone"]:
            continue
        title, snip = it["title"], it["snippet"]
        if title.isupper():
            title = title.capitalize()
        key = it["title"]
        if it["lang"] != "en":
            title, snip = cache.get(key) or translate(title), (cache.get(snip) or translate(snip)) if snip else ""
            if not title:
                dropped += 1
                continue
            cache[key] = title
            if snip:
                cache[it["snippet"]] = snip
        counts[it["tone"]] = counts.get(it["tone"], 0) + 1
        out.append({"id": "n" + hashlib.sha1(norm(it["title"]).encode()).hexdigest()[:9], "title": title, "summary": snip or "",
                    "original": it["title"], "source": it["source"], "url": it["url"], "when": it["when"].isoformat(), "tone": it["tone"],
                    "grave": it["grave"], "crime": it["crime"], "areas": it["areas"], "translated": it["lang"] != "en", "also": it.get("also", 0)})
    keep = {i["original"] for i in out} | {i["snippet"] for i in picked}
    save("translations.json", {k: v for k, v in cache.items() if k in keep})
    # 14-day crime log used by the zone score (kept small, no article text)
    log = load("crime_log.json", {})
    for it in picked:
        if it["crime"] and it["areas"] and it["tone"] == "bad":
            log[hashlib.sha1(norm(it["title"]).encode()).hexdigest()[:10]] = {"when": it["when"].isoformat(), "areas": it["areas"], "title": norm(it["title"])}
    limit = (now() - timedelta(days=14)).isoformat()
    log, seen = {k: v for k, v in sorted(log.items(), key=lambda x: x[1]["when"]) if v["when"] >= limit}, []
    for k in list(log):   # one event reported on several days counts once
        if any(same_story(s, log[k]["title"]) or same_death(s, log[k]["title"]) for s in seen):
            del log[k]
        else:
            seen.append(log[k]["title"])
    save("crime_log.json", log)
    save("news.json", {"updated": now().isoformat(), "items": out, "untranslatable": dropped, "errors": errors})
    return out, errors
