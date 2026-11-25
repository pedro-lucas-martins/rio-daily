"""Send one daily message to the Google Group. Does nothing unless all settings exist."""
import os, re, smtplib
from email.message import EmailMessage
from datetime import datetime
from .common import RIO_TZ, ROOT, load, now, save


def send(ctx, test=False):
    """A test goes only to the sending account itself, never to the group, and does not count as today's email."""
    user, pw, to = (os.getenv(k) for k in ("GMAIL_USER", "GMAIL_APP_PASSWORD", "NEWSLETTER_TO"))
    # Copied app passwords carry ordinary or non-breaking spaces.
    user, pw, to = (re.sub(r"\s+", "", v or "") for v in (user, pw, to))
    if test:
        to = user
    today = now().astimezone(RIO_TZ).date().isoformat()
    if not (user and pw and to):
        return "newsletter not configured: not sent"
    if not re.fullmatch(r"[^@]+@[^@]+\.[^@]+", user):
        return "GMAIL_USER is not a full email address: not sent"
    if not re.fullmatch(r"[a-zA-Z]{16}", pw):
        return "GMAIL_APP_PASSWORD is not a 16-letter app password: not sent"
    if not test and load("sent.json", {}).get("last") == today:
        return "already sent today"
    updated = load("news.json", {}).get("updated")
    if not updated or (now() - datetime.fromisoformat(updated)).total_seconds() > 6 * 3600:
        return "news is stale: not sent"
    if not (ctx["items"] or ctx["flights"]):
        return "nothing to send"
    html = (ROOT / "site" / "newsletter.html").read_text(encoding="utf-8")
    m = EmailMessage()
    lead = (ctx["alerts"] or ctx["items"] or [{"title": "prices from Poland"}])[0]["title"]
    m["Subject"] = re.sub(r"[\r\n]+", " ", f"{'[TEST] ' if test else ''}Rio Daily: {lead}")[:140]
    m["From"], m["To"] = user, to
    lines = [f"- {i['title']} ({i['source']}) {i['url']}" for i in ctx["items"][:10]]
    m.set_content("\n".join(["Rio Daily", *lines, "", ctx["site"]["url"]]))
    m.add_alternative(html, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as s:
        try:
            s.login(user, pw)
        except (smtplib.SMTPAuthenticationError, smtplib.SMTPServerDisconnected):
            return "Gmail refused the login: not sent"     # Gmail may just hang up on wrong details
        # Recorded after login, before sending: a missed email is better than a duplicate.
        if not test:
            save("sent.json", {"last": today, "levels": {a["id"]: a["level"] for a in ctx["areas"]}})
        s.send_message(m)
    return "sent"
