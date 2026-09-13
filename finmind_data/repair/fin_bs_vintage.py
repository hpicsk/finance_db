"""Take FinMind's revision of a balance sheet only where the filing sides with it.

FinMind re-ingested `TaiwanStockBalanceSheet` after `fin_bs/` was downloaded,
and the revision is not a correction. MOPS, where each company filed its
statement, sides with the tree in some quarters and with the revision in others,
and inside some quarters it splits by company. So each company-period the
revision touched is graded against its own filing, and replaced only where the
filing sides with the revision.

`grade` holds the tree against a snapshot of the vendor's current answer, one
date-keyed file per period end, and asks MOPS (`t164sb03`) for every
company-period whose level items differ, plus `CONTROLS` per period whose level
items all agree. A vendor item is matched to a line of the filing by its label:
verbatim first, then after dropping a trailing parenthetical or 淨額 and reading
總計, 總額 and a bare 總 as one ending, and only where exactly one line matches.
The filing prints share counts in shares and every other amount in thousands,
and a value agrees with it within half of that unit. Each answer is cached, one
file per company-period, and the grade is written to
`fin_bs_vintage_grade.parquet`.

`apply` writes the revision into every company-period whose filing sides with
it. The filing sides with the revision when every item it prints agrees with the
revision and not every one agrees with the tree. Each row the revision carries
takes the revision's value and label, and a row only the revision carries is
added. A row the revision does not carry stays as it was: the grade compares
values both vintages carry, so it never asked the filing about that row, and the
filing prints some of them. Every row of those company-periods on which the two
vintages differ is kept in `fin_bs_vintage.parquet`, with both values. Both
steps refuse to start while that record exists, because the grade is of the tree
before the replacement.

    python -m finmind_data.repair.fin_bs_vintage grade --snapshot DIR --cache DIR
    python -m finmind_data.repair.fin_bs_vintage apply --snapshot DIR --dry-run
    python -m finmind_data.repair.fin_bs_vintage apply --snapshot DIR
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from ..collect.mops_filings import EMPTY, Refused, call
from ..paths import RECORDS, TREES

TREE = TREES / "fin_bs"
GRADE = RECORDS / "fin_bs_vintage_grade.parquet"
RECORD = RECORDS / "fin_bs_vintage.parquet"
KEY = ["date", "stock_id", "type"]
# `t164sb03` serves no statement before the first IFRS quarter: asked for 2012 Q3
# and Q4, it answers that no such filing exists.
FIRST_PERIOD = "2013-03-31"
# Agreeing company-periods graded per period. They decide nothing; they are
# there so that a grading which fails on statements both sources agree on shows.
CONTROLS = 4
SEED = 20260912


def _clean(label) -> str:
    return str(label).replace("　", "").strip()


def _norm(label: str) -> str:
    """A label without the parts the vendor and the filing write differently."""
    s = re.sub(r"（[^（）]*）$|\([^()]*\)$", "", label)
    s = re.sub(r"淨額$", "", s)
    return re.sub(r"(總計|總額)$", "總", s)


def _amount(s) -> float:
    """A filing amount, with thousands separators and a negative in parentheses."""
    s = str(s).strip().replace(",", "")
    if s in ("", "-", "None"):
        return np.nan
    neg = s.startswith("(") and s.endswith(")")
    try:
        v = float(s.strip("()"))
    except ValueError:
        return np.nan
    return -v if neg else v


def _refuse_if_applied() -> None:
    if RECORD.exists():
        raise SystemExit(f"{RECORD.name} exists: the replacement has run, and the "
                         f"grade and the replacement are both of the tree before it")


def _tree() -> pd.DataFrame:
    return pd.concat([pd.read_parquet(p) for p in sorted(TREE.glob("*.parquet"))
                      if pq.ParquetFile(p).metadata.num_rows], ignore_index=True)


def _periods(snapshot: Path) -> list[str]:
    """The snapshot's period ends from `FIRST_PERIOD` on that hold any row."""
    out = []
    for p in sorted(snapshot.glob("fin_bs_*.parquet")):
        d = p.stem[len("fin_bs_"):]
        if d >= FIRST_PERIOD and pq.ParquetFile(p).metadata.num_rows:
            out.append(d)
    if not out:
        raise SystemExit(f"{snapshot} holds no fin_bs_<period>.parquet with rows")
    return out


def _levels(ours: pd.DataFrame, now: pd.DataFrame, period: str) -> pd.DataFrame:
    """The level items both sources carry for one period, side by side."""
    m = (ours[ours["date"] == period]
         .merge(now[now["date"] == period], on=KEY, suffixes=("_o", "_n")))
    m = m[~m["type"].str.endswith("_per")]
    m["same"] = (m["value_o"] == m["value_n"]) | (m["value_o"].isna() & m["value_n"].isna())
    return m


def _plan(ours: pd.DataFrame, snapshot: Path) -> list[tuple[str, str, str, pd.DataFrame]]:
    """(period, stock_id, kind, items) for every company-period to grade."""
    rng = np.random.default_rng(SEED)
    plan = []
    for d in _periods(snapshot):
        m = _levels(ours, pd.read_parquet(snapshot / f"fin_bs_{d}.parquet"), d)
        revised = sorted(m.loc[~m["same"], "stock_id"].unique())
        agree = sorted(set(m["stock_id"]) - set(revised))
        ctrl = sorted(rng.choice(agree, size=min(CONTROLS, len(agree)), replace=False)) if agree else []
        plan += [(d, s, "revised", m[(m["stock_id"] == s) & ~m["same"]]) for s in revised]
        plan += [(d, s, "control", m[m["stock_id"] == s]) for s in ctrl]
    return plan


def _filing(period: str, sid: str, cache: Path) -> dict | None:
    """The filed balance sheet's lines, or None where MOPS will not serve the company."""
    f = cache / f"{period}_{sid}.json"
    if f.exists():
        return json.loads(f.read_text())
    y, mo = int(period[:4]), int(period[5:7])
    try:
        res = call("t164sb03", {"companyId": sid, "dataType": "2", "season": str(mo // 3),
                                "year": str(y - 1911), "subsidiaryCompanyId": ""})
    except Refused:
        return None
    finally:
        time.sleep(1.0)
    if res is None:
        raise SystemExit(f"MOPS gave no answer for {sid} {period}; re-run to resume "
                         f"from {cache}")
    lines = {"reportList": [] if res is EMPTY else res.get("reportList") or []}
    f.write_text(json.dumps(lines, ensure_ascii=False))
    return lines


def _match(label: str, labels: list[str]) -> str | None:
    """The one filing line a vendor label names, or None.

    A label the filing prints more than once names no line, verbatim or not.
    """
    if label in labels:
        return label if labels.count(label) == 1 else None
    hit = [l for l in labels if _norm(l) == _norm(label)]
    return hit[0] if len(hit) == 1 else None


def grade(snapshot: Path, cache: Path) -> pd.DataFrame:
    _refuse_if_applied()
    cache.mkdir(parents=True, exist_ok=True)
    plan = _plan(_tree(), snapshot)
    print(f"{sum(k == 'revised' for _, _, k, _ in plan)} revised and "
          f"{sum(k == 'control' for _, _, k, _ in plan)} control company-periods", flush=True)
    rows = []
    for n, (d, sid, kind, items) in enumerate(plan, 1):
        base = {"period": d, "stock_id": sid, "kind": kind}
        res = _filing(d, sid, cache)
        if res is None or not res["reportList"]:
            rows.append({**base, "status": "refused" if res is None else "no_report"})
            continue
        labels = [_clean(r[0]) for r in res["reportList"]]
        lines = {_clean(r[0]): _amount(r[1]) for r in res["reportList"]}
        for r in items.itertuples():
            label = _clean(r.origin_name_o)
            line = _match(label, labels)
            rows.append({**base, "type": r.type, "label": label, "filing_label": line,
                         "unit": "shares" if line and "（單位：股）" in line else "thousands",
                         "ours": r.value_o, "now": r.value_n,
                         "filing": lines[line] if line else np.nan,
                         "status": "ok" if line else "no_label"})
        if n % 200 == 0:
            print(f"{n} of {len(plan)}, last {d} {sid}", flush=True)
    g = pd.DataFrame(rows, columns=["period", "stock_id", "kind", "type", "label",
                                    "filing_label", "unit", "ours", "now", "filing", "status"])
    g.to_parquet(GRADE, index=False)
    return g


def verdicts(g: pd.DataFrame) -> pd.DataFrame:
    """One verdict per graded company-period.

    ``revision`` and ``tree`` name the side every printed item agrees with where
    the other side misses at least one; ``both``, ``neither`` and ``mixed`` are
    the rest, and ``ungraded`` is a company-period with no item the filing
    prints, which keeps the status it failed on in ``status``.
    """
    ok = g[g["status"] == "ok"]
    scale = np.where(ok["unit"] == "shares", 1.0, 1000.0)
    t = (ok["ours"] / scale - ok["filing"]).abs() <= 0.5
    v = (ok["now"] / scale - ok["filing"]).abs() <= 0.5
    per = (ok.assign(t=t, v=v).groupby(["period", "stock_id", "kind"])
             .agg(items=("t", "size"), tree=("t", "sum"), revision=("v", "sum"))
             .reset_index())
    per["verdict"] = "mixed"
    per.loc[(per["revision"] == per["items"]) & (per["tree"] < per["items"]), "verdict"] = "revision"
    per.loc[(per["tree"] == per["items"]) & (per["revision"] < per["items"]), "verdict"] = "tree"
    per.loc[(per["tree"] == per["items"]) & (per["revision"] == per["items"]), "verdict"] = "both"
    per.loc[(per["tree"] == 0) & (per["revision"] == 0), "verdict"] = "neither"
    cp = g.groupby(["period", "stock_id", "kind"])["status"].agg(
        lambda s: "ok" if (s == "ok").any() else s.iloc[0]).reset_index()
    out = cp.merge(per, on=["period", "stock_id", "kind"], how="left")
    out["verdict"] = out["verdict"].fillna("ungraded")
    return out


def apply(snapshot: Path, dry_run: bool) -> pd.DataFrame:
    _refuse_if_applied()
    v = verdicts(pd.read_parquet(GRADE))
    todo = v[(v["kind"] == "revised") & (v["verdict"] == "revision")]
    log = []
    for d, grp in todo.groupby("period"):
        now = pd.read_parquet(snapshot / f"fin_bs_{d}.parquet")
        now = now[now["date"] == d]
        for sid in grp["stock_id"]:
            p = TREE / f"{sid}.parquet"
            f = pd.read_parquet(p)
            old, new = f[f["date"] == d], now[now["stock_id"] == sid][f.columns]
            m = old.merge(new, on=KEY, how="outer", suffixes=("_old", "_new"),
                          indicator="change")
            m["change"] = m["change"].map({"both": "changed", "left_only": "kept",
                                           "right_only": "added"}).astype(str)
            same = ((m["change"] == "changed")
                    & ((m["value_old"] == m["value_new"])
                       | (m["value_old"].isna() & m["value_new"].isna()))
                    & (m["origin_name_old"] == m["origin_name_new"]))
            log.append(m[~same])
            if not dry_run:
                at = pd.MultiIndex.from_frame(old[KEY])
                rev = new.set_index(KEY)
                hit = at.isin(rev.index)
                for c in ("value", "origin_name"):
                    f.loc[old.index[hit], c] = rev.loc[at[hit], c].to_numpy()
                add = new[~pd.MultiIndex.from_frame(new[KEY]).isin(at)]
                f = (pd.concat([f, add], ignore_index=True)
                       .sort_values("date", kind="stable").reset_index(drop=True))
                f.to_parquet(p, index=False)
    rec = pd.concat(log, ignore_index=True)
    print(f"{len(todo)} company-periods; rows {rec['change'].value_counts().to_dict()}")
    if not dry_run:
        rec.to_parquet(RECORD, index=False)
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["grade", "apply"])
    ap.add_argument("--snapshot", type=Path, required=True,
                    help="date-keyed TaiwanStockBalanceSheet pulls, fin_bs_<period>.parquet")
    ap.add_argument("--cache", type=Path, help="MOPS answers, one file per company-period")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.step == "grade":
        if args.cache is None:
            ap.error("grade needs --cache")
        grade(args.snapshot, args.cache)
    else:
        apply(args.snapshot, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
