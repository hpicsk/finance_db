"""Integrity assertions for the claims `kr_status`'s documentation makes.

This repo has no CI; verification is ad-hoc. Run with the data trees populated,
from anywhere:

    python kr_status/test_assertions.py

or run every package's assertions at once with `./run_assertions.sh` from the
repo root. Each check prints PASS, FAIL, or SKIP where a prerequisite
artifact is absent, along with `n`, the size of the population it examined.
The script exits non-zero if any check fails, if any examined nothing, and if
any skipped — a skip verified nothing, so iterating without the artifact takes
`--allow-skips`. `n` is held against `populations.json`, which records what
each check last read; re-seed it with `--write-populations` after a refresh.

Every figure in README.md and coverage.md is a property of one marcap clone
and one DART harvest, not a constant: a refresh that adds events is *meant* to
fail the exact ones, and that failure is what carries the new numbers into the
prose in the same commit. Two tables are projections of other tracked
artifacts — the audit events of the opinions cache, the historical seed of the
delisting calendar — and are held to a fresh projection rather than to a count.
"""
from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from kr_status.schema import DATA_DIR, STATUS_COLUMNS, STATUS_KINDS, events_path  # noqa: E402
from kr_status.marcap_halt_infer import MARCAP_DIR, RUN_GAP_DAYS  # noqa: E402
from kr_status.dart_audit import MIN_YEAR, OPINIONS_PATH, QUALIFIED_OPINIONS, build_events  # noqa: E402
from kr_status.dart_insincere import DEFAULT_DURATION_MONTHS, INSINCERE_RE  # noqa: E402
from kr_status.fdr_collect import HISTORICAL_PROXY_WINDOW_DAYS, seed_historical_audit  # noqa: E402

# Each check's population, recorded so a tree that lost rows fails rather
# than passing on a smaller one. Per package, not per repo: the root is a
# container and holds no package's numbers.
POPULATIONS = Path(__file__).with_name("populations.json")


class Skipped(Exception):
    """A prerequisite artifact is absent, so this check verified nothing.

    Distinct from a pass because it is: it used to print as one, which is the
    same confusion the population guard below exists to remove.
    """


# README § dart_corp_actions: the one table here that is not a status source,
# and the two event families its `category` splits.
CORP_ACTION_COLUMNS = ["ticker", "parent", "corp_code", "event", "category",
                       "rcept_dt", "rcept_no"]
GENUINE_EVENTS = {"유상증자", "무상증자", "유무상증자", "감자"}
ENTITY_EVENTS = {"회사합병", "회사분할", "회사분할합병", "주식교환"}

# README § marcap_halt_infer: the duration past which a "halt" is read as a
# line that never trades rather than a suspension, and the share of halt
# events coverage.md says sit past it.
LONG_HALT_DAYS = 252
LONG_HALT_SHARE_PCT = 1.6      # coverage.md: "~1.6% of events span > 252 days"
SHARE_TOL_PCT = 0.05           # half the last printed digit

# README § marcap_halt_infer: where each signal's coverage begins. Halt starts
# at the collector's default `--start-year` (marcap_halt_infer.main), a chosen
# cut — marcap itself runs from 1995 and carries the flag there too. Admin and
# alert start on the first marcap session carrying the label, which the check
# reads off marcap again rather than trusting from here.
HALT_START_YEAR = 2004
FIRST_DEPT_LABEL = pd.Timestamp("2011-05-02")

# coverage.md, alert row and the halt cross-check, all on 2020–2024.
WINDOW_START, WINDOW_END = pd.Timestamp("2020-01-01"), pd.Timestamp("2024-12-31")
ALERT_RUNS, ALERT_TICKERS = 230, 207
CROSSCHECK_SAMPLE, CROSSCHECK_QUERYABLE = 60, 30
# (confirmed, queryable) per duration bucket: 100 %, 78 %, 14 %, 30 %.
CROSSCHECK_BUCKETS = {"31-60d": (4, 4), "11-30d": (7, 9), "4-10d": (1, 7), "1-3d": (3, 10)}
BUCKET_EDGES, BUCKET_LABELS = [0, 3, 10, 30, 60], ["1-3d", "4-10d", "11-30d", "31-60d"]


def _events(name: str) -> pd.DataFrame:
    p = events_path(name)
    if not p.exists():
        raise Skipped(f"{p.name} not built")
    return pd.read_parquet(p)


def _marcap_years() -> list[int]:
    years = sorted(int(p.stem.split("-")[1]) for p in MARCAP_DIR.glob("marcap-*.parquet"))
    if not years:
        raise Skipped(f"no marcap-YYYY.parquet under {MARCAP_DIR}")
    return years


def _first_marcap_label(label: str) -> pd.Timestamp:
    """The first marcap session whose Dept carries `label`, read off marcap itself."""
    for year in _marcap_years():
        df = pd.read_parquet(MARCAP_DIR / f"marcap-{year}.parquet", columns=["Date", "Dept"])
        hit = df.loc[df["Dept"].fillna("").str.contains(label), "Date"]
        if len(hit):
            return pd.Timestamp(hit.min())
    raise AssertionError(f"no marcap row carries {label}")


def _same_rows(a: pd.DataFrame, b: pd.DataFrame, cols: list[str]) -> bool:
    """Row-for-row equality on `cols`, compared as text so a datetime resolution
    that changed in a parquet round-trip does not read as a data change."""
    if len(a) != len(b):
        return False
    return all((a[c].astype(str).values == b[c].astype(str).values).all() for c in cols)


# ---- README § Schema --------------------------------------------------------

def test_status_tables_share_the_schema():
    frames = {p.name: pd.read_parquet(p) for p in sorted(DATA_DIR.glob("*_events.parquet"))}
    status = {k: v for k, v in frames.items() if "status" in v.columns}
    if not status:
        raise Skipped("no status table under data/")
    n = 0
    for name, df in status.items():
        assert list(df.columns) == STATUS_COLUMNS, (
            f"README § Schema: every *_events.parquet matches STATUS_COLUMNS — "
            f"{name} has {list(df.columns)}")
        assert df["status"].isin(STATUS_KINDS).all(), (
            f"README § Schema: status is one of {STATUS_KINDS} — {name} carries "
            f"{sorted(set(df['status']) - set(STATUS_KINDS))}")
        assert df["ticker"].str.fullmatch(r"[0-9A-Z]{6}").all(), (
            f"README § Schema: ticker is 6-char zero-padded — {name} breaks it")
        assert (df["end_date"].isna() | (df["end_date"] >= df["start_date"])).all(), (
            f"README § Schema: end_date is the release date, on or after start_date — "
            f"{name} has a window that ends before it starts")
        n += len(df)
    return f"{len(status)} status tables match STATUS_COLUMNS over {n:,} rows", n


def test_corp_actions_are_not_a_status_source():
    ca = _events("dart_corp_action")
    assert list(ca.columns) == CORP_ACTION_COLUMNS, (
        f"README § dart_corp_actions: output columns are {CORP_ACTION_COLUMNS} and "
        f"carry no `status` — found {list(ca.columns)}")
    want = ca["event"].map(lambda e: "genuine" if e in GENUINE_EVENTS
                           else "entity" if e in ENTITY_EVENTS
                           else "none" if e == "" else None)
    assert want.notna().all(), (
        f"README § dart_corp_actions: every event is 유상증자/무상증자/유무상증자/감자 "
        f"or 회사합병/회사분할/회사분할합병/주식교환 — also found "
        f"{sorted(set(ca.loc[want.isna(), 'event']))}")
    assert (want == ca["category"]).all(), (
        "README § dart_corp_actions: `category` is genuine for the share-count "
        "events and entity for the identity events — the split on disk differs")
    pref = ca["ticker"].str[-1] != "0"
    assert (ca.loc[pref, "parent"] == ca.loc[pref, "ticker"].str[:5] + "0").all(), (
        "README § dart_corp_actions: a preferred share resolves to the parent "
        "common (code[:5] + '0')")
    assert (ca.loc[~pref, "parent"] == ca.loc[~pref, "ticker"]).all(), (
        "README § dart_corp_actions: a common is its own parent")
    return (f"{len(ca):,} rows split {want.value_counts().to_dict()}; "
            f"{int(pref.sum())} preferred rows resolve to their parent common"), len(ca)


# ---- README § marcap_halt_infer, coverage.md rows halt / admin / alert -------

def test_marcap_runs_break_on_the_gap():
    ev = _events("marcap_halt").sort_values(["ticker", "status", "start_date"])
    nxt = ev.groupby(["ticker", "status"])["start_date"].shift(-1)
    gap = (nxt - ev["end_date"]).dt.days.dropna()
    assert (gap > RUN_GAP_DAYS).all(), (
        f"README § marcap_halt_infer: 'a gap > {RUN_GAP_DAYS} calendar days breaks a "
        f"run' — {int((gap <= RUN_GAP_DAYS).sum())} consecutive runs of one ticker "
        f"and status sit closer than that, so they should have been one run")
    return (f"every consecutive pair of the {len(ev):,} runs is more than "
            f"{RUN_GAP_DAYS} days apart (closest {int(gap.min())})"), len(gap)


def test_marcap_signals_start_where_marcap_does():
    ev = _events("marcap_halt")
    years = _marcap_years()
    first = ev.groupby("status")["start_date"].min()
    last = ev.groupby("status")["end_date"].max()
    assert first["halt"].year == HALT_START_YEAR < years[0] + 10 and years[0] < HALT_START_YEAR, (
        f"README § marcap_halt_infer: halt coverage runs from {HALT_START_YEAR}, the "
        f"collector's default start, inside a marcap clone that begins earlier — "
        f"first halt {first['halt'].date()}, first marcap year {years[0]}")
    for status, label in (("admin", "관리종목"), ("alert", "투자주의환기")):
        on = _first_marcap_label(label)
        assert first[status] == on == FIRST_DEPT_LABEL, (
            f"README § marcap_halt_infer: {status} events begin on the first marcap "
            f"session carrying {label}, {FIRST_DEPT_LABEL.date()} — events begin "
            f"{first[status].date()}, the label {on.date()}")
    stale = {s: int(last[s].year) for s in ("halt", "admin", "alert")
             if last[s].year != years[-1]}
    assert not stale, (
        f"README § Rerun cadence: marcap_halt_infer re-derives after each marcap "
        f"refresh — marcap runs to {years[-1]} but these end earlier: {stale}")
    return (f"halt from {first['halt'].date()}, admin and alert from "
            f"{first['admin'].date()}, all three to {years[-1]}"), len(ev)


def test_long_halts_are_the_documented_share():
    ev = _events("marcap_halt")
    halts = ev[ev["status"] == "halt"]
    span = (halts["end_date"] - halts["start_date"]).dt.days + 1
    long = span > LONG_HALT_DAYS
    share = 100 * long.mean()
    assert math.isclose(share, LONG_HALT_SHARE_PCT, abs_tol=SHARE_TOL_PCT), (
        f"coverage.md halt row: '~{LONG_HALT_SHARE_PCT}% of events span > "
        f"{LONG_HALT_DAYS} days' — {share:.2f} % of {len(halts):,} halts do")
    return (f"{int(long.sum()):,} of {len(halts):,} halts ({share:.2f} %) span more "
            f"than {LONG_HALT_DAYS} days"), len(halts)


def test_alert_runs_overlapping_2020_2024():
    ev = _events("marcap_halt")
    alert = ev[(ev["status"] == "alert") & (ev["start_date"] <= WINDOW_END)
               & (ev["end_date"] >= WINDOW_START)]
    got = (len(alert), alert["ticker"].nunique())
    assert got == (ALERT_RUNS, ALERT_TICKERS), (
        f"coverage.md alert row: 'KOSPI+KOSDAQ: {ALERT_RUNS} runs overlap 2020–2024, "
        f"across {ALERT_TICKERS} distinct tickers' — {got[0]} runs, {got[1]} tickers")
    # KOSPI+KOSDAQ is a claim about the market of those rows, which the event
    # table does not carry; marcap does.
    markets = set()
    for year in range(WINDOW_START.year, WINDOW_END.year + 1):
        df = pd.read_parquet(MARCAP_DIR / f"marcap-{year}.parquet",
                             columns=["Code", "Dept", "Market"])
        markets |= set(df.loc[df["Dept"].fillna("").str.contains("투자주의환기")
                              & df["Code"].isin(alert["ticker"]), "Market"])
    assert markets <= {"KOSPI", "KOSDAQ"}, (
        f"coverage.md alert row counts KOSPI+KOSDAQ — the runs also fall on {markets}")
    return (f"{got[0]} alert runs on {got[1]} tickers overlap 2020–2024, "
            f"markets {sorted(markets)}"), len(alert)


def test_halt_crosscheck_sample():
    p = DATA_DIR / "marcap_halt_dart_crosscheck.parquet"
    if not p.exists():
        raise Skipped(f"{p.name} not built (python -m kr_status.marcap_halt_dart_crosscheck)")
    cc = pd.read_parquet(p)
    frame_ok = (cc["start_date"].between(WINDOW_START, WINDOW_END).all()
                and cc["n_days"].between(1, 60).all())
    assert len(cc) == CROSSCHECK_SAMPLE and frame_ok, (
        f"coverage.md halt row: 'DART cross-check on a {CROSSCHECK_SAMPLE}-sample "
        f"2020–2024' of halts up to 60 days — {len(cc)} rows, "
        f"{cc['start_date'].min().date()}..{cc['start_date'].max().date()}, "
        f"n_days up to {cc['n_days'].max()}")
    q = cc[cc["note"] == ""].copy()
    assert len(q) == CROSSCHECK_QUERYABLE, (
        f"coverage.md '거래정지, inference vs. canonical': '{CROSSCHECK_QUERYABLE} "
        f"queryable' of {CROSSCHECK_SAMPLE} — "
        f"{len(q)} rows had a corp_code to query")
    q["bucket"] = pd.cut(q["n_days"], bins=BUCKET_EDGES, labels=BUCKET_LABELS)
    got = {b: (int(g["confirmed"].sum()), len(g))
           for b, g in q.groupby("bucket", observed=True)}
    assert got == CROSSCHECK_BUCKETS, (
        f"coverage.md '거래정지, inference vs. canonical': '100% of 31–60d halts, "
        f"78% of 11–30d, 14% of 4–10d, "
        f"30% of 1–3d had a DART-filed causing event' — (confirmed, queryable) per "
        f"bucket is {got}, documented {CROSSCHECK_BUCKETS}")
    return (f"{len(cc)} sampled halts, {len(q)} queryable, confirmed per bucket "
            f"{ {b: f'{c}/{n}' for b, (c, n) in got.items()} }"), len(cc)


# ---- README § Phase B, coverage.md audit_qualified row ----------------------

def test_audit_events_rebuild_from_the_cache():
    if not OPINIONS_PATH.exists():
        raise Skipped(f"{OPINIONS_PATH.name} not harvested")
    ev = _events("dart_audit")
    opinions = pd.read_parquet(OPINIONS_PATH)
    rebuilt = build_events(opinions)
    cols = [c for c in STATUS_COLUMNS if c != "fetched_at"]
    assert _same_rows(rebuilt, ev, cols), (
        f"README § Phase B: dart_audit_events.parquet is the projection of "
        f"dart_audit_opinions.parquet — a rebuild (python -m kr_status.dart_audit "
        f"--rebuild-events) gives {len(rebuilt)} rows against {len(ev)} committed, "
        f"or the same rows with other windows")
    return (f"{len(ev):,} audit_qualified events rebuild identically from "
            f"{len(opinions):,} cached opinions"), len(ev)


def test_audit_events_are_non_clean_opinions_2015_plus():
    if not OPINIONS_PATH.exists():
        raise Skipped(f"{OPINIONS_PATH.name} not harvested")
    opinions = pd.read_parquet(OPINIONS_PATH)
    assert list(opinions.columns) == ["ticker", "bsns_year", "opinion_code", "receipt_dt", "raw"], (
        f"README § Phase B: the opinions cache is (ticker, bsns_year, opinion_code, "
        f"receipt_dt, raw) — found {list(opinions.columns)}")
    assert int(opinions["bsns_year"].min()) == MIN_YEAR, (
        f"coverage.md '감사의견 비적정, pre-2015': DART's structured audit-opinion "
        f"endpoint is populated for "
        f"bsns_year ≥ {MIN_YEAR} only — the cache starts at {opinions['bsns_year'].min()}")
    ev = _events("dart_audit")
    label = ev["detail"].str.split(" ", n=1).str[0]
    assert label.isin(QUALIFIED_OPINIONS).all(), (
        f"README § Phase B: an audit_qualified event is a 한정 / 부적정 / 의견거절 "
        f"opinion — also found {sorted(set(label) - QUALIFIED_OPINIONS)}")
    year = ev["source"].str.split(":").str[1].astype(int)
    assert (year >= MIN_YEAR).all(), (
        f"coverage.md audit_qualified row: DART events are {MIN_YEAR}+ — "
        f"the earliest source year is {year.min()}")
    assert ev["end_date"].notna().all() and (ev["end_date"] >= ev["start_date"]).all(), (
        "README § Phase B: an audit_qualified window closes at the ticker's next "
        "non-적정 receipt, or one year on when none follows — never NaT, never "
        "before it opens; a row breaks that")
    # Several years' opinions filed on one day (a late bulk filing) close the
    # earlier ones at zero length; the last of them carries the flag forward.
    same_day = int((ev["end_date"] == ev["start_date"]).sum())
    return (f"{len(ev):,} events, all 한정/부적정/의견거절 on bsns_year "
            f"{year.min()}–{year.max()}, every window closed ({same_day} at zero "
            f"length, filed on one day)"), len(ev)


def test_historical_seed_matches_the_calendar():
    ev = _events("historical_audit")
    with tempfile.TemporaryDirectory() as d:
        fresh = seed_historical_audit(out_path=Path(d) / "historical_audit_events.parquet")
    cols = [c for c in STATUS_COLUMNS if c != "fetched_at"]
    assert _same_rows(fresh, ev, cols), (
        f"README § Rerun cadence: fdr_collect --seed-historical is re-run when the "
        f"delisting calendar is refreshed — a fresh seed has {len(fresh)} rows "
        f"against {len(ev)} committed")
    span = (ev["end_date"] - ev["start_date"]).dt.days
    assert (span == HISTORICAL_PROXY_WINDOW_DAYS).all(), (
        f"README § fdr_collect: window = [delisting_date − "
        f"{HISTORICAL_PROXY_WINDOW_DAYS}d, delisting_date] — spans found "
        f"{sorted(set(span))}")
    return (f"{len(ev)} proxy events re-seed identically from the calendar, each "
            f"{HISTORICAL_PROXY_WINDOW_DAYS} days wide"), len(ev)


# ---- coverage.md insincere row ----------------------------------------------

def test_insincere_windows_are_one_year():
    ev = _events("dart_insincere")
    want = ev["start_date"] + pd.DateOffset(months=DEFAULT_DURATION_MONTHS)
    assert (ev["end_date"] == want).all(), (
        f"coverage.md insincere row: 'end_date = start_date + {DEFAULT_DURATION_MONTHS} "
        f"months (KRX standard)' — {int((ev['end_date'] != want).sum())} rows differ")
    assert ev["detail"].str.contains(INSINCERE_RE, regex=True).all(), (
        "README § Phase B: every insincere row is a 불성실공시법인지정 filing, not a "
        "지정예고 / 지정여부 notice")
    return (f"{len(ev):,} designations, each open for {DEFAULT_DURATION_MONTHS} "
            f"months"), len(ev)


# ---- README § Shared utility ------------------------------------------------

def test_corp_code_cache_records_its_misses():
    cache, misses = DATA_DIR / "corp_code_cache.parquet", DATA_DIR / "corp_code_misses.csv"
    if not cache.exists():
        raise Skipped(f"{cache.name} not built")
    cc = pd.read_parquet(cache)
    m = pd.read_csv(misses, dtype=str)
    assert cc["ticker"].is_unique, "README § Shared utility: one corp_code per ticker"
    assert list(m.columns) == ["ticker", "name"], (
        f"README § Shared utility: corp_code_misses.csv is (ticker, name) — "
        f"found {list(m.columns)}")
    unresolved = set(cc.loc[cc["corp_code"].isna(), "ticker"])
    assert set(m["ticker"]) == unresolved, (
        f"README § Shared utility: 'misses are logged to data/corp_code_misses.csv' — "
        f"the CSV lists {len(m)} tickers, the cache leaves {len(unresolved)} unresolved, "
        f"and they differ")
    return (f"{len(cc):,} tickers cached, {len(unresolved)} unresolved and every one "
            f"of them in corp_code_misses.csv"), len(cc)


CHECKS = [
    test_status_tables_share_the_schema,
    test_corp_actions_are_not_a_status_source,
    test_marcap_runs_break_on_the_gap,
    test_marcap_signals_start_where_marcap_does,
    test_long_halts_are_the_documented_share,
    test_alert_runs_overlapping_2020_2024,
    test_halt_crosscheck_sample,
    test_audit_events_rebuild_from_the_cache,
    test_audit_events_are_non_clean_opinions_2015_plus,
    test_historical_seed_matches_the_calendar,
    test_insincere_windows_are_one_year,
    test_corp_code_cache_records_its_misses,
]


if __name__ == "__main__":
    # This block is the same in every package's test_assertions.py, and
    # run_assertions.sh fails when the copies differ: edit it in one, then copy
    # it to the rest. Nothing below is package-specific — it needs CHECKS,
    # Skipped and POPULATIONS from above, and nothing else.
    #
    # A check that skipped verified nothing, which is the state this runner
    # exists to tell apart from a pass — and a suite of nothing but skips used to
    # exit 0, which is the same confusion one layer up from the one `Skipped`
    # fixed. Tolerable while iterating locally, never on the path that reproduces
    # the tree, so the strict reading is the default and the loose one is asked
    # for by name.
    allow_skips = "--allow-skips" in sys.argv[1:]
    # The population a check examined fingerprints the tree it read, and non-zero
    # is only the floor of what that fingerprint catches: a count that halves
    # still passes. A population that *grew* is a re-pull and says nothing; one
    # that *shrank* means the check now reads less of the tree than it did, which
    # is the same silent weakening `n` was added to expose, one revision later.
    # The bound is per check because a population clipped to a window moves only
    # when the window does, while one open past it grows every time the vendor
    # is re-pulled — a single rule would either fail every refresh or catch
    # nothing.
    # Re-seeding is the documented path after a refresh, and it was unreachable:
    # a legitimately moved population fails its own guard, which counts as a
    # failure, which makes the re-seed refuse — so the path existed only while it
    # was not needed. Under `--write-populations` the recorded numbers are being
    # replaced on purpose, so the comparison against them is reported and not
    # enforced. Every other assertion still has to pass, which is what stops a
    # broken tree from being written down as the expectation.
    reseed = "--write-populations" in sys.argv[1:]
    baseline = json.loads(POPULATIONS.read_text()) if POPULATIONS.exists() else {}
    observed = {}
    drift = []
    failures = skipped = 0
    for fn in CHECKS:
        try:
            # Every check returns the size of the population it examined. One that
            # examined none of it cannot have found anything wrong, and prints the
            # same PASS as one that examined all of it — so the empty case fails
            # here, once, rather than in each check that remembers to guard it.
            # int() because a numpy count is not JSON-serialisable, and the
            # baseline below is written as JSON.
            msg, n = fn()
            n = int(n)
            assert n, ("examined an empty population, so nothing it asserts was "
                       "tested — the inputs it reads are missing, filtered away, "
                       "or no longer shaped the way it expects")
            observed[fn.__name__] = n
            want = baseline.get(fn.__name__)
            if want:
                moved = (n != want["n"] if want["bound"] == "exact"
                         else n < want["n"])
                if moved and reseed:
                    drift.append(f"{fn.__name__} {want['n']:,} -> {n:,}")
                    moved = False
                assert not moved, (
                    f"examined {n:,} where {POPULATIONS.name} records "
                    f"{want['n']:,} ({want['bound']}). A shrink means the check "
                    f"now reads less of the tree than it did, or the tree lost "
                    f"rows; a move under `exact` means a population clipped to "
                    f"a window changed, which a re-pull does only by moving the "
                    f"window. Re-seed with --write-populations once the change "
                    f"is understood")
            print(f"PASS  {fn.__name__} [n={n:,}]: {msg}")
        except Skipped as e:
            skipped += 1
            print(f"SKIP  {fn.__name__}: {e}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {fn.__name__}: {e}")
        except Exception as e:  # missing data tree, etc. — report, don't hide
            failures += 1
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(CHECKS) - failures - skipped}/{len(CHECKS)} checks passed"
          + (f", {skipped} skipped" if skipped else ""))
    if skipped and not allow_skips:
        print(f"FAIL  {skipped} check(s) read an artifact that is not built, so "
              f"they verified nothing. Build it, or pass --allow-skips to "
              f"iterate without it.")
    unseeded = [f.__name__ for f in CHECKS if f.__name__ not in baseline]
    if unseeded:
        print(f"NOTE  {len(unseeded)} check(s) absent from {POPULATIONS.name}, so "
              f"their population is unbounded above zero: {', '.join(unseeded)}")
    if reseed:
        # Re-seeding takes its numbers only from a run that passed — a baseline
        # written from a broken tree records the breakage as the expectation.
        for d in drift:
            print(f"MOVED {d}")
        if failures or skipped:
            print("REFUSED to re-seed from a run that did not pass every check")
            failures += 1
        else:
            merged = {k: {"n": v,
                          "bound": baseline.get(k, {}).get("bound", "monotone")}
                      for k, v in observed.items()}
            POPULATIONS.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n")
            print(f"wrote {POPULATIONS.name} for {len(merged)} checks")
    sys.exit(1 if failures or (skipped and not allow_skips) else 0)
