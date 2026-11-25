"""Invented prices, only for previewing the layout (site-demo, with a banner)."""
from datetime import date, timedelta
from .common import now


def history():
    out = []
    for i in range(30):
        dep = date.today() + timedelta(days=60 + i)
        out.append({"origin": "WAW" if i % 2 else "KRK", "depart": dep.isoformat(), "return": (dep + timedelta(days=14)).isoformat(),
                    "price": 4900 + (i * 137) % 900, "out": ["WAW" if i % 2 else "KRK", "LIS", "GIG"], "back": ["GIG", "LIS", "WAW" if i % 2 else "KRK"],
                    "airlines": ["Sample Air"], "typical": None, "direct": False, "drop": i == 7, "found": (now() - timedelta(days=29 - i)).isoformat()})
    return out
