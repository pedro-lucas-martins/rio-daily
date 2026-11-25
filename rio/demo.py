"""Invented prices, only for previewing the layout (site-demo, with a banner)."""
from datetime import date, timedelta
from .common import now

WATCH = [{"origin": o, "depart": (date.today() + timedelta(days=100)).isoformat(), "return": (date.today() + timedelta(days=114)).isoformat()} for o in ("WAW", "KRK")]


def history():
    return [dict(w, price=4900 + (i * 137 + k * 90) % 900, out=[w["origin"], "LIS", "GIG"], back=["GIG", "LIS", w["origin"]], airlines=["Sample Air"],
                 typical=None, direct=False, drop=False, found=(now() - timedelta(days=29 - i)).isoformat())
            for k, w in enumerate(WATCH) for i in range(30)]
