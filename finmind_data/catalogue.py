"""The vendor's own dataset index, vendored so a name is looked up rather than guessed.

Every collector in this package names a FinMind dataset as a bare string, and a
name that does not exist returns the same shape of failure as one that is merely
empty for the ticker asked for — so a typo, a renamed endpoint or an invented
one costs a round of probing to tell apart from a real absence. Two such guesses
are already recorded in ``download.py``, learned by asking the API; they are
registered in ``KNOWN_ABSENT`` below rather than left as a comment, because a
"not available" note is exactly the kind that goes stale in silence when the
vendor adds the dataset later.

FinMind publishes the enum itself at ``finmind.github.io/llms-full.txt`` — every
dataset with its tier, date range, parameters and columns. Holding a copy turns
that class of question into a local lookup, and
``test_taiwan_dataset_names_in_code_resolve`` makes it binding in both
directions: no collector can land naming a dataset the vendor does not publish,
and no registered absence can quietly become available.

**Scope is the CamelCase REST enum.** Four datasets are named in lower case
(``taiwan_stock_tick_snapshot`` and the other Sponsor-tier real-time snapshots),
and that spelling collides with the Python SDK's method names, which are a
separate namespace with no derivable mapping to a dataset — ``TaiwanStockPrice``
is reached as ``api.taiwan_stock_daily``, ``TaiwanStockPriceTick`` as
``api.taiwan_stock_tick``. A lower-case token in this tree is therefore an SDK
method, and an SDK method that does not exist fails loudly at the call as an
``AttributeError``, which is not the silent class this check is for. The four
real-time snapshots are intraday quotes and out of scope for a historical panel.

**The copy carries its pull date in its filename.** It is a vendor document, not
this package's output — FinMind edits it when the catalogue moves, so a
byte-freshness check against the live URL would fail on their release schedule
rather than on a defect here. The date is what a later reader needs in order to
know how old the answer is, and a second pull lands beside the first instead of
overwriting it, so the two are never spliced.

    python -m finmind_data.catalogue          # refresh: writes today's copy
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
URL = "https://finmind.github.io/llms-full.txt"
STEM = "finmind_catalogue_"

# `### TaiwanStockPrice (股價日成交資訊)` — the vendor's own heading for one
# dataset. The Chinese name is always parenthesised and always present.
_ENTRY = re.compile(r"^### ([A-Za-z][A-Za-z0-9_]*) \((.+)\)\s*$")
# `## Taiwan Market - Fundamental (12 datasets)` — the group the entries follow.
_SECTION = re.compile(r"^## (.+?)(?: \(\d+ datasets\))?\s*$")
_FIELD = re.compile(r"^- ([A-Za-z][A-Za-z /()]*?):\s*(.*)$")

# Dataset names this package asked for and the API refused. Registered rather
# than described so the claim is checked: each must still be missing from the
# enum, and the workaround built in its place is noted with it.
KNOWN_ABSENT = {
    "TaiwanStockEPS":
        "EPS is read off TaiwanStockFinancialStatements instead (fin_is/).",
    "TaiwanStockShareholdingClassification":
        "股權分散表; TaiwanStockHoldingSharesPer is the paid-tier equivalent.",
}


def path() -> Path:
    """The newest vendored copy.

    Newest rather than a pinned name because the point of the date stamp is that
    a refresh adds a file; the live catalogue is the one that answers "does this
    dataset exist today".
    """
    copies = sorted(ROOT.glob(f"{STEM}*.txt"))
    if not copies:
        raise FileNotFoundError(
            f"no {STEM}*.txt in {ROOT} — run `python -m finmind_data.catalogue`")
    return copies[-1]


def pull_date() -> dt.date:
    """The date the copy `path()` returns was fetched, read off its filename."""
    stamp = path().stem[len(STEM):]
    return dt.datetime.strptime(stamp, "%Y%m%d").date()


def datasets() -> dict[str, dict[str, str]]:
    """Every dataset the vendor publishes, keyed by the name a collector passes.

    The value carries the entry's own fields verbatim — ``Tier``, ``Data range``,
    ``Params``, ``Columns`` — plus ``chinese`` and the ``section`` it sits under,
    so a caller can answer "is it free" and "how far back does it go" without a
    request.
    """
    out: dict[str, dict[str, str]] = {}
    section = ""
    current: dict[str, str] | None = None
    for line in path().read_text(encoding="utf-8").splitlines():
        if m := _SECTION.match(line):
            section, current = m.group(1), None
        elif m := _ENTRY.match(line):
            current = {"chinese": m.group(2), "section": section}
            out[m.group(1)] = current
        elif current is not None and (m := _FIELD.match(line)):
            current.setdefault(m.group(1), m.group(2))
        elif line.startswith("#"):
            current = None
    return out


def main() -> None:
    r = requests.get(URL, timeout=60)
    r.raise_for_status()
    out = ROOT / f"{STEM}{dt.date.today():%Y%m%d}.txt"
    out.write_text(r.text, encoding="utf-8")
    print(f"{out.name}: {len(r.text):,} bytes, {len(datasets())} datasets")


if __name__ == "__main__":
    main()
