"""
dex_photo_ids.py -- the DDL ids and the written dates read from a photo, each with its word confidence.

For Lena Marsh / DDL-3005 (D-mails DDL-3005:20261011T025909Z-62fa and ...T043000Z-6d5d, ferried by the
Operator 2026-10-10). The private graph links a photo to what it names, and works out an earliest
possible date from those ids. It needs, per photo:

    ids_found   [{"id": "DDL-3012", "conf": 93.0}, ...]     her patterns, whole tokens only
    dates_seen  [{"date": "2026-03-02", "conf": 91.0}, ...]  a full date written in the image

Nothing else is taken from the words. An id or a date is kept at whatever confidence it was read; the
graph decides what is clear enough (80 or above makes a link). The same id read twice keeps its best
reading. Input is the word boxes dex_photo_word_boxes.py wrote: [[text, conf, x, y, w, h], ...].
"""
import re
from datetime import date

# Her patterns, as sent. FND-, R-, P- and commit hashes are left out on purpose: the graph has no nodes for them.
SEAT = r"(?:DDL|SEAT)-\d{4}"
GRAPH = (r"(?:STD|CR|PRO|ADR|AB|MCN|OBS|REC|CONV|PROP|SEARCH|GT|RH|PE|CONF|AXIOM|GLOSS|ORCH|DMAIL|PA\d|PREDDL|MINI|FINDING|ASSET)"
         r"-(?:[A-Z0-9]+-)*\d+[A-Z]?")
ID = re.compile(rf"(?<![A-Za-z0-9])(?:{GRAPH}|{SEAT})(?![A-Za-z0-9])")

ISO = re.compile(r"(?<![0-9A-Za-z])((?:19|20)\d\d)-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])(?![0-9])")
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
MONTH_WORD = re.compile(r"^\W*(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
                        r"nov(?:ember)?|dec(?:ember)?)\.?$", re.I)
DAY_WORD = re.compile(r"^(\d{1,2})(?:st|nd|rd|th)?,?$")
YEAR_WORD = re.compile(r"^((?:19|20)\d\d)\W*$")
FIRST_YEAR, LAST_YEAR = 1990, 2035


def _best(pairs, key):
    """One row per key, the best confidence kept, sorted by key."""
    out = {}
    for k, conf in pairs:
        if k not in out or conf > out[k]:
            out[k] = conf
    return [{key: k, "conf": out[k]} for k in sorted(out)]


def ids_in(words):
    """[{"id", "conf"}] for every id of her patterns that stands as a whole token inside a word."""
    return _best(((m.group(0), float(w[1])) for w in words for m in ID.finditer(w[0])), "id")


def _real(y, m, d):
    try:
        return date(int(y), int(m), int(d)).isoformat() if FIRST_YEAR <= int(y) <= LAST_YEAR else None
    except ValueError:
        return None


def dates_in(words):
    """[{"date", "conf"}]: 2026-03-02 in one word, or Mar 2, 2026 across three words on one line (the weakest
    word's confidence). A date that is not a real day, or outside 1990-2035, is not a date."""
    found = []
    for w in words:
        for m in ISO.finditer(w[0]):
            d = _real(*m.groups())
            if d:
                found.append((d, float(w[1])))
    for a, b, c in zip(words, words[1:], words[2:]):
        mm, dd, yy = MONTH_WORD.match(a[0]), DAY_WORD.match(b[0]), YEAR_WORD.match(c[0])
        if not (mm and dd and yy):
            continue
        if max(abs(a[3] - b[3]), abs(b[3] - c[3])) > max(a[5], b[5], c[5]):      # not on one line
            continue
        d = _real(yy.group(1), MONTHS[mm.group(1)[:3].lower()], dd.group(1))
        if d:
            found.append((d, min(float(a[1]), float(b[1]), float(c[1]))))
    return _best(found, "date")
