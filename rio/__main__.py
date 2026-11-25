import sys
from . import build, flights, news, newsletter, review, zones
from .common import load, load_env

HELP = "usage: python -m rio [news|daily|build|demo|pending|approve ID|send]"


def run(label, fn):
    try:
        res, errs = fn()
        print(f"{label}: {len(res)} items", *errs, sep="\n  ")
        return True
    except Exception as e:     # one failing source must not stop the others
        print(f"{label}: FAILED ({type(e).__name__})")
        return False


def main(a):
    cmd = a[0] if a else ""
    if cmd in ("news", "daily"):
        ok = [run("news", news.collect)]
        ok.append(run("zones", zones.collect))
        if cmd == "daily":
            ok.append(run("flights", flights.collect))
        if not any(ok):
            raise SystemExit("everything failed")
        build.build()
    elif cmd == "build":
        build.build()
    elif cmd == "demo":
        from .demo import history
        build.build("site-demo", history(), True)
    elif cmd == "pending":
        for p in load("pending.json", []):
            print(p["id"], "|", p["text"], "|", p["original"], p["url"])
    elif cmd == "approve" and len(a) > 1:
        review.approve(a[1])
        build.build()
    elif cmd == "send":
        print(newsletter.send(build.build()))
    else:
        raise SystemExit(HELP)


load_env()
main(sys.argv[1:])
