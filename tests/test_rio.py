from datetime import datetime, timedelta, timezone
import pytest
from rio import common, flights, news, review, zones, newsletter
from rio.translate import acceptable

CFG = common.config()


@pytest.fixture(autouse=True)
def tmpdata(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "DATA", tmp_path)


def opt(path, price=5000, token="t", lay=None):
    f = [{"departure_airport": {"id": a}, "arrival_airport": {"id": b}, "airline": "X"} for a, b in zip(path, path[1:])]
    return {"flights": f, "layovers": [{"id": x} for x in (lay or [])], "price": price, "departure_token": token}


class Free:
    def take(self): return True


def q(outs, backs, cur="PLN"):
    def fetch(p):
        return {"best_flights": backs} if "departure_token" in p else {"best_flights": outs, "search_parameters": {"currency": cur}}
    return flights.quote("WAW", "2027-03-01", "2027-03-15", CFG["flights"], Free(), "k", fetch)


@pytest.mark.parametrize("sp", ["GRU", "CGH", "VCP"])
def test_sao_paulo_rejected_both_ways(sp):
    ok, bad = opt(["WAW", "LIS", "GIG"]), opt(["WAW", sp, "GIG"])
    assert q([bad], [opt(["GIG", "LIS", "WAW"])]) is None
    assert q([ok], [opt(["GIG", sp, "WAW"])]) is None
    assert q([opt(["WAW", "LIS", "GIG"], lay=[sp])], [opt(["GIG", "LIS", "WAW"])]) is None


def test_cheaper_sao_paulo_return_is_skipped():
    r = q([opt(["WAW", "LIS", "GIG"])], [opt(["GIG", "GRU", "WAW"], 3000), opt(["GIG", "CDG", "WAW"], 5200)])
    assert r["price"] == 5200 and r["back"] == ["GIG", "CDG", "WAW"]


def test_wrong_airport_missing_segments_and_currency():
    good = [opt(["GIG", "LIS", "WAW"])]
    assert q([opt(["WAW", "LIS", "SDU"])], good) is None
    assert q([{"price": 1, "departure_token": "t"}], good) is None
    with pytest.raises(RuntimeError):
        q([opt(["WAW", "LIS", "GIG"])], good, "USD")


def test_budget():
    b = flights.Budget({"monthly_request_limit": 3, "requests_per_day": 2})
    assert [b.take() for _ in range(3)] == [True, True, False]


@pytest.mark.parametrize("t,tone", [("Turista é assaltado na praia de Ipanema", "bad"), ("Metrô do Rio terá greve na sexta", "caution"),
                                    ("Museu do Rio abre exposição gratuita", "good"), ("Roubos caem em Copacabana", "caution"), ("Algo acontece no Rio", "caution")])
def test_tone(t, tone):
    assert news.classify(t) == tone


def test_areas_and_relevance():
    A = CFG["areas"]
    assert news.find_areas("Furto na Barra da Tijuca", A) == ["barra"]
    assert news.find_areas("Flamengo vence no Maracanã", A) == ["maracana"]
    assert not news.relevant("Temporal no RS deixa 5 mortos", [])
    assert not news.relevant("Idosa morre na praia em Ubatuba", [])
    assert news.relevant("Praias do Rio têm bandeira vermelha", [])


def test_translation_gate():
    assert acceptable("Um dois três quatro 50", "One two three four 50")
    assert not acceptable("Preso com 50 celulares", "Arrested with 60 phones")
    assert not acceptable("Um texto aqui longo", "the the the the the the")


def test_missing_source_is_not_zero():
    w = CFG["zones"]["weights"]
    assert zones.combine({"official": 80, "shootings": None, "news": 80}, w) == 80


def test_underreported_is_unknown_without_shootings():
    z = zones.score(CFG["areas"], CFG["zones"], {}, 24322, None, {}, datetime.now(timezone.utc))
    assert {a["id"]: a["computed"] for a in z}["rocinha"] == "unknown"


def test_review():
    n = [{"id": "n1", "grave": True, "title": "x", "original": "x", "url": "u"}]
    z = [{"id": "lapa", "name": "Lapa", "score": 90, "computed": "red"}]
    items, areas, pend = review.apply(n, z)
    assert items == [] and areas[0]["level"] == "orange" and len(pend) == 2
    review.approve("n1"); review.approve("z-lapa")
    items, areas, pend = review.apply(n, z)
    assert items[0]["alert"] and areas[0]["level"] == "red" and pend == []


def test_email_never_sent_without_config(monkeypatch):
    for k in ("GMAIL_USER", "GMAIL_APP_PASSWORD", "NEWSLETTER_TO"):
        monkeypatch.delenv(k, raising=False)
    assert "not sent" in newsletter.send({})


def test_email_once_per_day(monkeypatch, tmp_path):
    import smtplib
    sent = []
    class S:
        def __init__(s, *a, **k): pass
        def __enter__(s): return s
        def __exit__(s, *a): pass
        def login(s, *a): pass
        def send_message(s, m): sent.append(m)
    monkeypatch.setattr(smtplib, "SMTP_SSL", S)
    monkeypatch.setattr(newsletter, "ROOT", tmp_path)
    (tmp_path / "site").mkdir(); (tmp_path / "site" / "newsletter.html").write_text("<p>x</p>")
    for k in ("GMAIL_USER", "GMAIL_APP_PASSWORD", "NEWSLETTER_TO"):
        monkeypatch.setenv(k, "abcdefghijklmnop" if "PASS" in k else "a@example.com")
    common.save("news.json", {"updated": common.now().isoformat()})
    ctx = {"items": [{"title": "T\nBcc: z", "source": "s", "url": "u"}], "alerts": [], "flights": [], "areas": [], "site": {"url": ""}}
    assert newsletter.send(ctx) == "sent" and newsletter.send(ctx) == "already sent today" and len(sent) == 1
    common.save("sent.json", {})
    common.save("news.json", {"updated": (common.now() - timedelta(hours=7)).isoformat()})
    assert "stale" in newsletter.send(ctx)


def test_env_file(tmp_path, monkeypatch):
    monkeypatch.setenv("RIO_T_A", "real")
    monkeypatch.setenv("RIO_T_B", "x"); monkeypatch.delenv("RIO_T_B")
    f = tmp_path / ".env"; f.write_text("# c\nRIO_T_A=file\nRIO_T_B='k=1'\nRIO_T_C=\n")
    common.load_env(f)
    import os
    assert os.environ["RIO_T_A"] == "real" and os.environ["RIO_T_B"] == "k=1" and "RIO_T_C" not in os.environ


def h(origin, dep, price, day, ret="2027-06-15"):
    return {"origin": origin, "depart": dep, "return": ret, "price": price, "found": f"{day}T11:00:00+00:00", "typical": None}


def test_series_never_mixes_trips():
    from rio.build import watch_view
    w = [{"origin": "WAW", "depart": "2027-06-01", "return": "2027-06-15"}]
    hist = [h("WAW", "2027-06-01", 5000, "2026-11-26"), h("WAW", "2026-12-25", 9000, "2026-11-27"), h("KRK", "2027-06-01", 1, "2026-11-27"),
            h("WAW", "2027-06-01", 5200, "2026-11-29")]
    v = watch_view(hist, w)[0]
    assert v["series"] == [("2026-11-26", 5000), ("2026-11-29", 5200)] and v["change"] == 200 and v["prev"][0] == "2026-11-26"


def test_drop_uses_same_trip_only():
    today = common.now()
    d = lambda n: (today - timedelta(days=n)).date().isoformat()
    q = dict(h("WAW", "2027-06-01", 4000, d(0)), found=today.isoformat())
    assert flights.is_drop([h("WAW", "2027-06-01", 5000, d(n)) for n in range(1, 11)], q, .15)
    assert not flights.is_drop([h("WAW", "2026-12-25", 9000, d(n)) for n in range(1, 11)], q, .15)


def test_watch_dates_fixed_then_replaced():
    from datetime import date
    c = CFG["flights"]
    a = flights.watched(c, date(2026, 11, 26))
    assert flights.watched(c, date(2027, 1, 10)) == a
    b = flights.watched(c, date(2027, 3, 10))
    assert b[0]["depart"] == "2027-07-10" and len(b) == 2


def test_collect_order_budget_and_cursor(monkeypatch):
    monkeypatch.setenv("SERPAPI_KEY", "k")
    calls = []
    def fake(o, d, r, cfg, budget, key):
        calls.append((o, d, r)); budget.take(); budget.take()
        return {"origin": o, "depart": d, "return": r, "price": 1, "found": common.now().isoformat(), "typical": None}
    monkeypatch.setattr(flights, "quote", fake)
    flights.collect()
    assert len(calls) == 4 and [c[0] for c in calls[:2]] == ["WAW", "KRK"]
    assert common.load("flight_budget.json", {})["cursor"] == 2
    flights.collect()     # budget used up: nothing searched, cursor unchanged
    assert len(calls) == 4 and common.load("flight_budget.json", {})["cursor"] == 2


def test_test_email_goes_only_to_sender(monkeypatch, tmp_path):
    import smtplib
    sent = []
    class S:
        def __init__(s, *a, **k): pass
        def __enter__(s): return s
        def __exit__(s, *a): pass
        def login(s, *a): pass
        def send_message(s, m): sent.append(m)
    monkeypatch.setattr(smtplib, "SMTP_SSL", S)
    monkeypatch.setattr(newsletter, "ROOT", tmp_path)
    (tmp_path / "site").mkdir(); (tmp_path / "site" / "newsletter.html").write_text("<p>x</p>")
    monkeypatch.setenv("GMAIL_USER", "me@example.com"); monkeypatch.setenv("GMAIL_APP_PASSWORD", "abcd efgh\xa0ijkl mnop "); monkeypatch.setenv("NEWSLETTER_TO", "group@example.com")
    common.save("news.json", {"updated": common.now().isoformat()})
    ctx = {"items": [{"title": "T", "source": "s", "url": "u"}], "alerts": [], "flights": [], "areas": [], "site": {"url": ""}}
    assert newsletter.send(ctx, True) == "sent" and sent[0]["To"] == "me@example.com" and sent[0]["Subject"].startswith("[TEST]")
    assert common.load("sent.json", {}) == {}
    assert newsletter.send(ctx) == "sent" and sent[1]["To"] == "group@example.com"


def test_bad_login_is_clear_and_not_recorded(monkeypatch, tmp_path):
    import smtplib
    class S:
        def __init__(s, *a, **k): pass
        def __enter__(s): return s
        def __exit__(s, *a): pass
        def login(s, *a): raise smtplib.SMTPServerDisconnected("closed")
    monkeypatch.setattr(smtplib, "SMTP_SSL", S)
    monkeypatch.setattr(newsletter, "ROOT", tmp_path)
    (tmp_path / "site").mkdir(); (tmp_path / "site" / "newsletter.html").write_text("<p>x</p>")
    monkeypatch.setenv("GMAIL_USER", "me@example.com"); monkeypatch.setenv("NEWSLETTER_TO", "g@example.com")
    common.save("news.json", {"updated": common.now().isoformat()})
    ctx = {"items": [{"title": "T", "source": "s", "url": "u"}], "alerts": [], "flights": [], "areas": [], "site": {"url": ""}}
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "abcdefghijklmnop")
    assert "refused" in newsletter.send(ctx) and common.load("sent.json", {}) == {}
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "my normal pass1!")
    assert "16-letter" in newsletter.send(ctx)


def test_underreported_never_green_even_with_shootings():
    z = zones.score(CFG["areas"], CFG["zones"], {}, 24322, {"copacabana": {"count": 1, "weight": 1}}, {}, datetime.now(timezone.utc))
    assert {a["id"]: a["computed"] for a in z}["rocinha"] == "unknown"


def test_landing_pages(tmp_path, monkeypatch):
    import shutil
    from rio import build
    real = common.ROOT / "data" / "bairros.geojson"
    monkeypatch.setattr(build, "DATA", tmp_path)
    shutil.copy(real, tmp_path / "bairros.geojson")
    monkeypatch.setattr(build, "ROOT", tmp_path)
    for d in ("templates", "static"):
        shutil.copytree(common.ROOT / d, tmp_path / d)
    build.build()      # no data at all must still give valid pages
    html = (tmp_path / "site" / "index.html").read_text()
    assert "No news available" in html and "No verified prices" in html and "data-join" in html and "wa.me" in html
    assert "rio-daily-news%2Bsubscribe%40googlegroups.com" in html and "fonts.googleapis" not in html
    assert f"style.css?v={build.version()}" in html
    assert "prefers-color-scheme" not in html + (tmp_path / "static" / "style.css").read_text()
    evil = {"id": "n1", "title": "<script>x</script>", "original": "o", "source": "s", "url": "https://e.example", "when": common.now().isoformat(),
            "tone": "bad", "grave": False, "crime": True, "areas": [], "translated": True, "summary": ""}
    common.save("news.json", {"items": [evil, dict(evil, id="n2", title="held", grave=True)]})
    build.build()
    html = (tmp_path / "site" / "index.html").read_text()
    assert "&lt;script&gt;x" in html and "held" not in html
