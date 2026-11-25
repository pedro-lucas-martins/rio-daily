"""Human approval for grave news and areas rising to red."""
from .common import load, save


def apply(news, zones):
    """Split content into publishable and pending. Pending items never reach the site or email."""
    ok = set(load("approvals.json", []))
    pending, items = [], []
    for n in news:
        if n["grave"] and n["id"] not in ok:
            pending.append({"id": n["id"], "kind": "news", "text": n["title"], "original": n["original"], "url": n["url"]})
        else:
            items.append(dict(n, alert=n["grave"]))
    shown, areas = load("zone_levels.json", {}), []
    for z in zones:
        lv = z["computed"]
        zid = "z-" + z["id"]
        if lv == "red" and shown.get(z["id"]) != "red" and zid not in ok:
            pending.append({"id": zid, "kind": "zone", "text": f"{z['name']} rises to red (score {z['score']})", "original": "", "url": ""})
            lv, held = "orange", True
        else:
            held = False
        if lv != "red":
            ok.discard(zid) if not held else None    # a new rise needs a new approval
        areas.append(dict(z, level=lv, held=held, was=shown.get(z["id"])))
    save("approvals.json", sorted(ok))
    save("pending.json", pending)
    return items, areas, pending


def approve(item):
    if item not in {p["id"] for p in load("pending.json", [])}:
        raise SystemExit(f"'{item}' is not pending")
    save("approvals.json", sorted(set(load("approvals.json", [])) | {item}))
