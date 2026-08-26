"""Read a share swap's exchange ratio off the acquirer's filing.

``delisting_consideration.csv`` prices a swap as ``per_share`` successor shares
per target share, and for most of the swap-labelled exits that number is not
available at all. The labels record a ratio for a dozen of them, but in
conventions that disagree row to row — ``0.3562:1``, ``1:1.68``, ``3.15:1``, a
bare ``1.39`` — and picking a direction by whichever reading lands nearest the
last close would measure the picking rather than the deal (README caveat 8).
The direction has to come off a filing, and this is what fetches it.

**Why the acquirer and not the target.** ``mops_filings.py`` documents the
asymmetry this exploits: MOPS gates the 說明 on the company's *current*
registration, so a target that deregistered on the way out is served its
subject lines and nothing else — 14 of the 164 return a body. The acquirer is
still 公開發行 and its filings of the same transaction are served in full, ratio
included. A 股份轉換 is announced on both sides, so the sealed half is never the
only half.

**Where that stops.** The gate is on registration and not on the delisting
table, so it closes again when the *acquirer* was itself later bought — 2448
晶元光電 bought 8199 廣鎵 in 2012 and folded into a holding company in 2021, and
the host now refuses it in the same words it refuses the targets. Those deals
are recorded in ``mops_acquirer_refusals.csv`` and skipped, because which of
them are out is a coverage answer this package owes rather than a run that
failed.

**The map is checked, not asserted.** Each deal names its acquirer's company as
it appears in the *target's* own subject lines, which are already local in
``mops_listing/``, and ``verify_map`` requires the name to be found there. A
transposed code cannot survive that: the labels record 永崴投控 for two 2018
exits as 3172, which is 炎洲流通, and the holdco is 3712.

**Three of the deals are not swaps.** The route is defined by whose filing is
served, not by how the deal paid, so it also reaches the second step of a
two-step going-private — a tender, then a 合併 or 股份轉換 that squeezes out
whoever did not tender. Those buyers are large listed companies and their
filings state the squeeze-out price directly, which is the number
``delisting_consideration.csv`` needs and the offer table does not carry. Two of
the three restate the tender price and one does not, so the price has to be read
rather than carried across.

**Which announcements cost a request.** A large acquirer files on the order of
150 announcements a year, and the ratio sits in a handful, so details are
fetched only for subjects that name the target or the ratio. The filter is
recorded per deal in the cache, because a subject line that was not fetched is
not evidence of absence.

    python -m finmind_data.swap_ratios              # every deal not yet cached
    python -m finmind_data.swap_ratios --only 3534
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

from .mops_filings import (LISTING_DIR, LOOKBACK_ROC_YEARS, details_for,
                           listings_for, log)

ROOT = Path(__file__).resolve().parent
ACQ_LISTING_DIR = ROOT / "mops_acquirer_listing"
ACQ_DETAIL_DIR = ROOT / "mops_acquirer_detail"
ACQ_REFUSALS = ROOT / "mops_acquirer_refusals.csv"
FRAME = ROOT / "delisting_sign.parquet"
LABELS = ROOT / "delisting_labels.csv"

# target -> (acquirer code, the acquirer's company name as the target's own
# subject lines write it). The name is the evidence for the code and is checked
# against `mops_listing/<target>.parquet`; the code is checked against the
# panel, since a swap is priced on the successor's own sessions.
#
# Two pairs share an acquirer and one pair shares a deal: 3428 and 6145 went
# into the same new holdco alongside 6298, and 3068 and 5255 into 奇力新 a few
# months apart. Both are cached per target rather than per acquirer, because the
# unit of work here is the deal and a re-run should resume at the one that
# failed.
DEALS = {
    "3534": ("2454", "聯發科技"),
    "3367": ("2356", "英業達"),
    "5854": ("5880", "合作金庫金融控股"),
    "3389": ("3036", "文曄科技"),
    "8199": ("2448", "晶元光電"),
    "3080": ("3698", "隆達電子"),
    "5280": ("3545", "旭曜科技"),
    "5491": ("3710", "連展投資控股"),
    "3068": ("2456", "奇力新電子"),
    "3428": ("3712", "永崴投資控股"),
    "6145": ("3712", "永崴投資控股"),
    "3514": ("3576", "新日光能源科技"),
    "3299": ("5317", "凱美電機"),
    "5255": ("2456", "奇力新電子"),
    "4944": ("6488", "環球晶圓"),
    # 3561 shares 3514's acquirer and its filing: one 3576 announcement sets both
    # ratios, and the sentence for 昇陽 was read while transcribing 昱晶's. It is
    # cached under its own id anyway, because the citation check resolves a row's
    # quote against the cache named for that row's target and a shared body read
    # under a sibling's name is a source no rule can find.
    "3561": ("3576", "新日光能源科技"),
    # The three two-step residuals, added once `terminal_value` became the
    # settlement interface: each was tendered first and ended by a second step
    # the buyer filed, so the tender price is what the holders who tendered
    # received and the ratio here is what the rest were squeezed out at
    # (README caveat 8). They differ from the entries above only in having a
    # tender in front of them; the lookup is the same one.
    "6422": ("2327", "國巨"),
    "4725": ("1101", "台灣水泥"),
    "5820": ("2881", "富邦金融控股"),
}

# A subject worth a detail request: it names the target, or it names the ratio
# or the transaction that carries one. Two decisions on width, in opposite
# directions. A bare 合併 is *not* a key, because it is the word in 合併財務報表
# and 合併營收 — on the largest acquirer here it takes the filter from 9 of 428
# subjects to 53, and the extra 44 are quarterly results. The target's first two
# characters *are* a key, because an acquirer writes the short name (雷凌 for
# 雷凌科技) as often as the registered one, and a false positive costs one
# request while a miss costs the deal.
_DEAL_WORDS = ("換股比例", "轉換比例", "股份轉換", "增發新股", "轉換基準日",
               "合併基準日", "合併契約", "合併案")


def _wanted(subject: str, target_name: str) -> bool:
    keys = (target_name, target_name[:2]) + _DEAL_WORDS
    return any(k in subject for k in keys)


def target_names() -> dict[str, str]:
    """Each target's company name as MOPS writes it, from its own listing."""
    out = {}
    for sid in DEALS:
        l = pd.read_parquet(LISTING_DIR / f"{sid}.parquet")
        names = [n for n in l["company_name"].dropna().unique() if n]
        assert names, f"{sid} has no company_name in its own listing"
        out[sid] = names[0]
    return out


def verify_map() -> None:
    """The acquirer named for each deal must appear in the target's subjects.

    The whole point of going to the acquirer is that the target cannot be
    asked, so the code routing the request is the one thing here with no
    downstream check on it. This is that check, and it reads the evidence the
    package already holds rather than a note about where the code came from.
    """
    missing = []
    for sid, (acq, acq_name) in DEALS.items():
        l = pd.read_parquet(LISTING_DIR / f"{sid}.parquet")
        subjects = " ".join(l["subject"].fillna(""))
        if acq_name not in subjects:
            missing.append(f"{sid}->{acq} ({acq_name})")
    assert not missing, (
        f"the acquirer named for {missing} is not mentioned in the target's own "
        f"subject lines, so the code routing its filings rests on nothing this "
        f"package holds")


def collect(sid: str, acq: str, acq_name: str, delist_date: pd.Timestamp,
            tgt_name: str) -> tuple[int, int]:
    """Cache the acquirer's headers and the bodies of the deal-relevant ones."""
    lst_path = ACQ_LISTING_DIR / f"{sid}.parquet"
    det_path = ACQ_DETAIL_DIR / f"{sid}.parquet"
    if det_path.exists():
        return -1, -1

    if lst_path.exists():
        lst = pd.read_parquet(lst_path)
    else:
        roc = delist_date.year - 1911
        years = list(range(roc - LOOKBACK_ROC_YEARS, roc + 1))
        lst = listings_for(acq, years)
        if lst is None:
            raise RuntimeError(f"{sid}: listings for acquirer {acq} failed")
        lst.to_parquet(lst_path, index=False)

    want = lst[lst["subject"].fillna("").map(lambda s: _wanted(s, tgt_name))]
    det, refusal = details_for(want)
    if det is None:
        raise RuntimeError(f"{sid}: details for acquirer {acq} failed")
    if refusal:
        # The route has a boundary and this is it: an acquirer that later
        # deregistered is gated exactly as the target is, so a deal whose buyer
        # was itself bought is unreachable here. Recorded and skipped rather
        # than raised, because one sealed buyer must not cost the deals behind
        # it in the loop, and because which deals are out is a coverage answer
        # this package owes rather than a run that failed.
        _record_refusal(sid, acq, refusal)
    det.to_parquet(det_path, index=False)
    return len(lst), len(det)


def _record_refusal(sid: str, acq: str, refusal: str) -> None:
    """One row per target whose acquirer the host will not serve.

    Its own file rather than `mops_detail_refusals.csv`: there `stock_id` is
    the delisted name being refused, and here the refusal is about a company
    that never delisted, keyed by the target it was asked for.
    """
    row = pd.DataFrame([{"target_id": sid, "acquirer_id": acq,
                         "refusal": refusal.strip()}])
    if ACQ_REFUSALS.exists():
        row = (pd.concat([pd.read_csv(ACQ_REFUSALS, dtype=str), row],
                         ignore_index=True)
                 .drop_duplicates(["target_id"], keep="last"))
    row.sort_values("target_id").to_csv(ACQ_REFUSALS, index=False)


# Every phrasing seen in the bodies these deals return, as one alternation. It
# is here to *surface* candidates for reading, never to decide a ratio: the
# direction is read from the sentence, and a regex that guessed it would be the
# fitting this module exists to avoid.
RATIO_HINT = re.compile("換股比例|換發|轉換比例|每.{0,12}股.{0,20}換")


# Lines of context printed either side of a ratio line. The MOPS 併購 template
# puts the ratio under a numbered heading and the number on the lines below it,
# so the sentence that carries the direction usually straddles the match.
_CONTEXT_LINES = 3


def show(sid: str, full: bool = False) -> None:
    """Print the ratio clauses for one target, for reading by hand.

    A body runs to fifty lines of boilerplate and the direction sits in one
    sentence of it, so what is printed is the matched line with a few either
    side. ``full`` prints the whole body, for the deals where the excerpt turns
    out to straddle the sentence.
    """
    det = pd.read_parquet(ACQ_DETAIL_DIR / f"{sid}.parquet")
    acq, acq_name = DEALS[sid]
    print("=" * 96)
    print(f"{sid}  acquirer {acq} {acq_name}  ({len(det)} bodies)")
    for r in det.itertuples():
        body = r.body or ""
        if not RATIO_HINT.search(body):
            continue
        print("-" * 96)
        print(f"{r.spoke_date} | {(r.subject or '').replace(chr(13), '')}")
        if full:
            print(body)
            continue
        lines = body.splitlines()
        keep = sorted({j for i, l in enumerate(lines) if RATIO_HINT.search(l)
                       for j in range(max(0, i - _CONTEXT_LINES),
                                      min(len(lines), i + _CONTEXT_LINES + 1))})
        prev = None
        for j in keep:
            if prev is not None and j != prev + 1:
                print("   ...")
            print(f"   {lines[j]}")
            prev = j


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated target ids")
    ap.add_argument("--show", action="store_true",
                    help="print cached ratio clauses instead of fetching")
    ap.add_argument("--full", action="store_true",
                    help="with --show, print whole bodies rather than excerpts")
    args = ap.parse_args()

    verify_map()
    todo = list(DEALS)
    if args.only:
        todo = args.only.split(",")
        unknown = [t for t in todo if t not in DEALS]
        assert not unknown, f"{unknown} are not swap deals in DEALS"

    if args.show:
        for sid in todo:
            show(sid, full=args.full)
        return 0

    ACQ_LISTING_DIR.mkdir(exist_ok=True)
    ACQ_DETAIL_DIR.mkdir(exist_ok=True)
    f = pd.read_parquet(FRAME).set_index("stock_id")
    names = target_names()
    done = skipped = 0
    for sid in todo:
        acq, acq_name = DEALS[sid]
        n_l, n_d = collect(sid, acq, acq_name,
                           pd.Timestamp(f.loc[sid, "delist_date"]), names[sid])
        if n_l < 0:
            skipped += 1
            continue
        done += 1
        log(f"  {sid} <- {acq} {acq_name}: {n_l} headers, {n_d} bodies"
            f"{' REFUSED' if n_d == 0 else ''}")
    log(f"acquirer filings: wrote {done}, skipped {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
