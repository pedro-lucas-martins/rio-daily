"""Shared helpers: paths, config, JSON state, text normalisation."""
import json, os, re, unicodedata
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import requests, yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RIO_TZ = ZoneInfo("America/Sao_Paulo")


def config():
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def now():
    return datetime.now(timezone.utc)


def load(name, default):
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def save(name, obj):
    DATA.mkdir(exist_ok=True)
    tmp = DATA / (name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, DATA / name)


def get(url, **kw):
    kw.setdefault("timeout", 60)
    kw.setdefault("headers", {"User-Agent": "Mozilla/5.0 (compatible; news-reader)"})
    r = requests.get(url, **kw)
    r.raise_for_status()
    return r


def norm(text):
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t)).strip()


def has(text_norm, words):
    """Words matched whole; a trailing * matches any ending."""
    for w in words:
        pat = norm(w.rstrip("*")) + (r"\w*" if w.endswith("*") else "")
        if re.search(rf"\b{pat}\b", text_norm):
            return True
    return False


def load_env(path=None):
    """Read .env on the local computer; real environment variables win."""
    p = path or ROOT / ".env"
    for line in p.read_text(encoding="utf-8").splitlines() if p.exists() else []:
        k, sep, v = line.strip().partition("=")
        if sep and not k.startswith("#") and v.strip():
            os.environ.setdefault(k.strip(), v.strip().strip("\"'"))
