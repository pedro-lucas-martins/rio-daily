"""Send one daily message to the Google Group. Does nothing unless all settings exist."""
import os, re, smtplib
from email.message import EmailMessage
from datetime import datetime
from .common import RIO_TZ, ROOT, load, now, save


def send(ctx):
    user, pw, to = (os.getenv(k) for k in ("GMAIL_USER", "GMAIL_APP_PASSWORD", "NEWSLETTER_TO"))
    today = now().astimezone(RIO_TZ).date().isoformat()
    if not (user and pw and to):
        return "newsletter not configured: not sent"
    if load("sent.json", {}).get("last") == today:
        return "already sent today"
    updated = load("news.json", {}).get("updated")
    if not updated or (now() - datetime.fromisoformat(updated)).total_seconds() > 6 * 3600:
        return "news is stale: not sent"
    if not (ctx["items"] or ctx["flights"]):
        return "nothing to send"
    html = (ROOT / "site" / "newsletter.html").read_text(encoding="utf-8")
    m = EmailMessage()
    lead = (ctx["alerts"] or ctx["items"] or [{"title": "prices from Poland"}])[0]["title"]
    m["Subject"] = re.sub(r"[\r\n]+", " ", f"Rio Daily: {lead}")[:140]
    m["From"], m["To"] = user, to
    lines = [f"- {i['title']} ({i['source']}) {i['url']}" for i in ctx["items"][:10]]
    m.set_content("\n".join(["Rio Daily", *lines, "", ctx["site"]["url"]]))
    m.add_alternative(html, subtype="html")
    # Recorded first: after a crash, a missed email is better than a duplicate.
    save("sent.json", {"last": today, "levels": {a["id"]: a["level"] for a in ctx["areas"]}})
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as s:
        s.login(user, pw)
        s.send_message(m)
    return "sent"
