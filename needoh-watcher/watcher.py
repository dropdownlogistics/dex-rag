"""Needoh stock watcher — polls 19 retailer URLs, texts Emily on new finds."""
import json
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from twilio.rest import Client

HERE = Path(__file__).parent
load_dotenv(HERE / ".env")

TWILIO_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_FROM = os.environ["TWILIO_FROM_NUMBER"]
EMILY_TO = os.environ["EMILY_PHONE_NUMBER"]

STATE_FILE = HERE / "seen.json"
LOG_FILE = HERE / "watcher.log"

URLS = [
    ("mykidztoys.com", "https://mykidztoys.com/search?q=needoh&options%5Bprefix%5D=last"),
    ("fatbraintoys.com", "https://www.fatbraintoys.com/search.cfm?q=Needoh"),
    ("bonjourfete.com", "https://www.bonjourfete.com/search?q=needoh&_pos=1&_psq=needoh&_ss=e&_v=1.0"),
    ("scheels.com", "https://www.scheels.com/b/needoh?searchTerm=needoh"),
    ("toysandsweets.com", "https://toysandsweets.com/collections/needoh"),
    ("christianbook.com", "https://www.christianbook.com/apps/search?Ntt=Needoh&Ne=0&N=0&Ntk=keywords&action=Search&ps_exit=RETURN%7Clegacy&ps_domain=www&event=BRSRCG%7CPSEN"),
    ("playtherapysupply.com", "https://www.playtherapysupply.com/search?q=Needoh"),
    ("staples.com", "https://www.staples.com/needoh/directory_needoh"),
    ("educationmakesthedifference.com", "https://educationmakesthedifference.com/collections/fidgets-for-all-ages/toys"),
    ("pharmfavorites.com", "https://pharmfavorites.com/search?q=needoh&options%5Bprefix%5D=last"),
    ("bingsdsm.com", "https://www.bingsdsm.com/s/search?q=Needoh"),
    ("twirlsandtwigs.com", "https://twirlsandtwigs.com/search?q=Needoh"),
    ("booksamillion.com", "https://www.booksamillion.com/search?query=needoh&id=9749258330610"),
    ("safariltd.com", "https://www.safariltd.com/search?type=page%2Carticle%2Cproduct&q=needoh"),
    ("redballoon.com", "https://www.redballoon.com/s/search?q=Needoh"),
    ("barnesandnoble.com", "https://www.barnesandnoble.com/s/Needoh"),
    ("theprizebooth.com", "https://www.theprizebooth.com/search?q=needoh&options%5Bprefix%5D=last"),
    ("shopsmallscreendesigns.com", "https://www.shopsmallscreendesigns.com/pages/rapid-search-results?q=needoh"),
    ("buttercuplynne.com", "https://www.buttercuplynne.com/collections/sensory-toys"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

STARTUP_MSG = (
    "\U0001F7E2 Needoh Watcher is live! Watching 19 sites every 15 min. "
    "I'll text you the second something drops. \U0001F419"
)

# Generic non-product link texts to ignore even if they contain "needoh"
SKIP_EXACT = {
    "needoh", "shop needoh", "search: needoh", "needoh products",
    "needoh toys", "all needoh", "view all", "see more",
}


def log(msg: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as e:
        print(f"log write failed: {e}")


def load_state() -> tuple[dict, bool]:
    """Return (state, first_run). first_run is True when no usable state file exists."""
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            data.setdefault("startup_sent", False)
            data.setdefault("seen", {})
            return data, False
        except json.JSONDecodeError:
            log("state file corrupt, starting fresh")
    return {"startup_sent": False, "seen": {}}, True


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def fetch(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def extract_products(html: str, base_url: str) -> list[tuple[str, str]]:
    """Return deduped [(product_name, link)] for anchors whose text contains 'needoh'."""
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        text = " ".join(a.get_text(" ", strip=True).split())
        if not text or "needoh" not in text.lower():
            continue
        if len(text) < 6 or len(text) > 200:
            continue
        if text.lower().strip() in SKIP_EXACT:
            continue
        href = a["href"]
        if href.startswith("//"):
            href = "https:" + href
        elif href.startswith("/") or not href.startswith("http"):
            href = urljoin(base_url, href)
        found.setdefault(text, href)
    return list(found.items())


def send_sms(client: Client, body: str) -> None:
    msg = client.messages.create(body=body, from_=TWILIO_FROM, to=EMILY_TO)
    log(f"SMS sent sid={msg.sid}")


def main() -> int:
    state, first_run = load_state()
    client = Client(TWILIO_SID, TWILIO_TOKEN)

    if first_run:
        log("first run — cataloging current findings silently, no product alerts this run")

    if not state["startup_sent"]:
        try:
            send_sms(client, STARTUP_MSG)
            state["startup_sent"] = True
            save_state(state)
        except Exception as e:
            log(f"startup SMS failed — {e}")

    seen = state["seen"]
    new_alerts = 0
    cataloged = 0

    for site, url in URLS:
        try:
            html = fetch(url)
        except requests.RequestException as e:
            log(f"{site}: fetch failed — {e}")
            continue
        try:
            products = extract_products(html, url)
        except Exception as e:
            log(f"{site}: parse failed — {e}")
            continue
        log(f"{site}: {len(products)} candidate(s)")
        for name, link in products:
            key = f"{site}::{name.lower()}"
            if key in seen:
                continue
            if first_run:
                seen[key] = datetime.now().isoformat(timespec="seconds")
                cataloged += 1
                continue
            if "sugar skull cat" in name.lower():
                body = f"\U0001F6A8 SUGAR SKULL CAT ALERT \U0001F6A8 — {site} — GO GO GO! {link}"
            else:
                body = f"\U0001F7E2 Needoh alert! {name} spotted at {site} — {link}"
            try:
                send_sms(client, body)
                seen[key] = datetime.now().isoformat(timespec="seconds")
                new_alerts += 1
            except Exception as e:
                log(f"{site}: SMS send failed for '{name}' — {e}")

    save_state(state)
    if first_run:
        log(f"first-run catalog complete: {cataloged} item(s) marked as seen, 0 alerts sent")
    else:
        log(f"run complete: {new_alerts} new alert(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
