"""The statement trees and when their figures became readable."""
from __future__ import annotations
import glob
import math
import pandas as pd

from finmind_data.window import COVERAGE_END, COVERAGE_START
from finmind_data.paths import DATA, TREES
from ._common import Skipped, _LATE_FRAME_END, _PER_STOCK_BREAK, _STAMP_SPLIT, _STATEMENT_BREAK, _tree


def test_taiwan_fundamentals_are_fiscal_dated():
    """CAVEATS.md 9: fiscal period end, no announcement date.

    A look-ahead limit rather than a survivorship one, and invisible in the
    schema unless someone states what `date` means. `dividend/` carries
    `AnnouncementDate`, which is what makes the others' silence a gap rather
    than a convention of the source.
    """
    fin = _tree(TREES / "fin_is/2330.parquet")
    ends = set(pd.to_datetime(fin["date"]).dt.strftime("%m-%d"))
    assert ends <= {"03-31", "06-30", "09-30", "12-31"}, (
        f"CAVEATS.md 9 says fin_is dates are fiscal quarter ends; 2330 also "
        f"carries {sorted(ends - {'03-31', '06-30', '09-30', '12-31'})}"
    )
    for dset in ("fin_is", "fin_bs", "fin_cf"):
        c = set(pd.read_parquet(TREES / f"{dset}/2330.parquet").columns)
        assert not {"AnnouncementDate", "create_time", "announcement_date"} & c, (
            f"CAVEATS.md 9 says {dset}/ carries no announcement date; it now "
            f"has one, so the look-ahead caveat is obsolete and signals built "
            f"on it can be aligned point-in-time"
        )

    # `create_time` carries no announcement date for anything this package
    # answers about, and where its values fall is what rules it out. Read
    # unclipped on purpose: the claim is about the stamps landing outside the
    # window, and a clipped read would find none and asserting that zero would
    # verify nothing.
    #
    # The stamps are two different things either side of the window. On the
    # 2005-2010 backfill the lag from a period to its stamp runs to twenty
    # years, which is an ingest time for rows the vendor rewrote rather than a
    # release date. On the 2026 rows it is about ten days, which is what a
    # release date looks like under Taiwan's monthly-revenue deadline — so the
    # column is not uniformly meaningless, it is uniformly absent here. Neither
    # kind reaches the window, and that is the caveat: a signal built on
    # in-window monthly revenue has no announcement date to align to.
    tot = stamped = inwin_stamped = 0
    backfill_lag = []
    months, stamps = [], []
    for p in sorted(glob.glob(str(TREES / "month_rev/*.parquet"))):
        m = pd.read_parquet(p)
        if not len(m):
            continue
        tot += len(m)
        st = m["create_time"].astype(str).str.strip()
        d = pd.to_datetime(m["date"], errors="coerce")
        hit = st != ""
        stamped += int(hit.sum())
        inw = d.between(COVERAGE_START, COVERAGE_END)
        inwin_stamped += int((hit & inw).sum())
        months.append(pd.DataFrame({"date": d[inw], "hit": hit[inw]}))
        stamps.append(pd.DataFrame({
            "date": d[hit], "stock_id": m.loc[hit, "stock_id"],
            "lag": (pd.to_datetime(st[hit], errors="coerce") - d[hit]).dt.days}))
        back = hit & (d < COVERAGE_START)
        if back.any():
            lag = (pd.to_datetime(st[back], errors="coerce") - d[back]).dt.days
            backfill_lag += list(lag.dropna())
    per = pd.concat(months, ignore_index=True).groupby("date")["hit"].mean()
    assert stamped, (
        "CAVEATS.md 9 argues from where create_time's values fall that it is "
        "not a release date for this window; no row in the tree carries one at "
        "all, so the argument has no population and the caveat is unsupported "
        "rather than confirmed"
    )
    # The frontier the caveat now turns on, read off the column rather than
    # written down: the reporting month from which the vendor stamps at
    # publication. Split at a half because the two sides are not near it — the
    # month before is stamped on well under a tenth of its rows and every month
    # after on essentially all of them — so any cut between the clusters names
    # the same month and this one is not a tuned boundary.
    above = per.index[per > _STAMP_SPLIT]
    assert len(above), (
        f"CAVEATS.md 9 says the vendor stamps monthly revenue at publication "
        f"from a reporting month inside the window; no month has {_STAMP_SPLIT:.0%} "
        f"of its rows stamped, so the point-in-time stretch the caveat offers "
        f"does not exist"
    )
    frontier = above.min()
    stragglers = sorted(per.index[(per.index > frontier) & (per <= _STAMP_SPLIT)])
    assert not stragglers, (
        f"CAVEATS.md 9 dates the point-in-time stretch from {frontier.date()} "
        f"onward, which requires every later reporting month to be stamped; "
        f"{len(stragglers)} are not ({[str(d.date()) for d in stragglers[:4]]}), "
        f"so the stretch is not contiguous and a study aligning on the stamp "
        f"would drop those months silently"
    )
    assert backfill_lag and min(backfill_lag) > 365, (
        f"CAVEATS.md 9 reads the pre-window stamps as the vendor's ingest "
        f"time because they post-date their own periods by years; the smallest "
        f"such lag is now {min(backfill_lag) if backfill_lag else None} days, "
        f"which is a release date's distance, not an ingest one"
    )

    # The figures the caveat quotes on each side of the frontier.
    s = pd.concat(stamps, ignore_index=True)
    pub = s[s["date"] >= frontier]
    early = s[(s["date"] >= COVERAGE_START) & (s["date"] < frontier)]
    pre = s[s["date"] < COVERAGE_START]
    figures = (tot, stamped, str(frontier.date()),
               (len(pub), pub["stock_id"].nunique(), int(pub["lag"].min()),
                int(pub["lag"].max()), float(pub["lag"].median())),
               (len(early), early["stock_id"].nunique(), float(early["lag"].median())),
               (len(pre), int(pre["lag"].min()), int(pre["lag"].max())))
    assert figures == (416_142, 15_934, "2026-03-01", (13_574, 1_944, 0, 79, 9.0),
                       (2_010, 122, 5_161.0), (350, 5_617, 7_808)), (
        f"CAVEATS.md 9 says 15,934 of month_rev's 416,142 rows carry a "
        f"create_time; that the vendor stamps at publication from reporting "
        f"month 2026-03, on 13,574 rows across 1,944 stocks lagging their "
        f"reporting date by 0 to 79 days with a median of 9; and that before "
        f"it the stamps fall on 2,010 in-window rows in 122 stocks at a median "
        f"lag of 5,161 days and on 350 pre-window rows at 5,617 to 7,808. The "
        f"tree gives {figures}"
    )

    div = _tree(TREES / "dividend/1101.parquet")
    assert "AnnouncementDate" in div.columns, (
        "CAVEATS.md 9 names dividend/ as the one dataset carrying "
        "AnnouncementDate; it no longer does"
    )
    return (f"fin_* dated on quarter ends with no announcement column; "
            f"month_rev create_time on {stamped:,} of {tot:,} rows, "
            f"{inwin_stamped:,} in-window and stamped at publication from "
            f"{frontier.date()} on, pre-window lag from {min(backfill_lag):,}d; "
            f"dividend has it"), tot


def test_taiwan_statement_trees_drop_old_delistings():
    """CAVEATS.md 10: prices keep the delisted names, statements do not.

    The universe overlay and the rebuild together make the *price* panel
    survivorship-complete, and a reader who stops there will assume the whole
    package is. It is not: the endpoints serving company filings answer for a
    company that still reports, so a name that failed a decade ago has prices
    and no income statement, and the missing names are exactly the failures a
    fundamentals study must not drop.

    Every number below is checked the way the caveat states it. The gap is
    absence at the source rather than clipping, so the file is read unclipped
    too and asserted empty. The break is one-sided, so the assertion is on the
    later side being whole rather than on a rate, and each tree's break date is
    derived as its latest delisting without a row. And the contrast that
    localises it to the filing endpoints — the exchange's own daily series
    keeping the same names — is read from `per_pbr/` and `instflow/`, which no
    part of the statement path touches.
    """
    import pyarrow.parquet as pq

    from finmind_data.repair.date_keyed_fill import RECORD

    u = pd.read_parquet(DATA / "universe.parquet")
    d = pd.read_parquet(DATA / "delisted_universe.parquet")
    uid = set(u["stock_id"].astype(str))
    d = d.copy()
    d["date"] = pd.to_datetime(d["date"])
    d["sid"] = d["stock_id"].astype(str)
    inwin = d[(d["date"] >= COVERAGE_START) & (d["date"] <= COVERAGE_END)
              & d["sid"].isin(uid)]
    delist = dict(zip(inwin["sid"], inwin["date"]))
    assert len(delist) == 179, (
        f"CAVEATS.md 10 reports the statement coverage against 179 commons "
        f"delisted inside the window; the table now dates {len(delist)}"
    )

    have, empty_file, stale_only, last_row = [], 0, [], {}
    for sid in sorted(delist):
        whole = pd.read_parquet(TREES / f"fin_is/{sid}.parquet")
        clipped = _tree(TREES / f"fin_is/{sid}.parquet")
        if len(clipped):
            have.append(sid)
            last_row[sid] = pd.to_datetime(whole["date"]).max()
        elif len(whole):
            stale_only.append(sid)
        else:
            empty_file += 1
    assert len(have) == 84, (
        f"CAVEATS.md 10 says fin_is/ carries rows for 84 of the 179; it "
        f"now carries them for {len(have)}"
    )
    assert not stale_only, (
        f"CAVEATS.md 10 says the missing files are empty rather than "
        f"out-of-window, which is what makes this absence at the source and "
        f"not a window artifact; {len(stale_only)} now hold rows the window "
        f"excludes, so the caveat's argument no longer holds: {stale_only[:5]}"
    )
    assert empty_file == 95, (
        f"CAVEATS.md 10 pins 95 empty fin_is files; there are {empty_file}"
    )

    def traded_quarters(sid):
        o = _tree(TREES / f"ohlcv/{sid}.parquet")
        return o.loc[o["Trading_Volume"] > 0, "date"].dt.to_period("Q").nunique() if len(o) else 0

    missing = [s for s in delist if s not in last_row]
    long_lived = sum(traded_quarters(s) >= 8 for s in missing)
    assert long_lived == 85, (
        f"CAVEATS.md 10 says 85 of the 95 missing names traded in eight or "
        f"more in-window quarters; {long_lived} of {len(missing)} did"
    )

    brk = max(delist[s] for s in missing)
    # The rows the date-keyed fill added are recorded, and every fin_is/ file
    # it touched was empty, so what the per-stock query returned is the rest.
    filled = set(pd.read_parquet(RECORD / "fin_is.parquet")["stock_id"])
    per_stock = max(delist[s] for s in delist if s not in set(have) - filled)
    assert (brk, per_stock) == (_STATEMENT_BREAK, _PER_STOCK_BREAK), (
        f"CAVEATS.md 10 puts the break on {_STATEMENT_BREAK.date()}, the "
        f"latest delisting whose income statement the trees lack, and on "
        f"{_PER_STOCK_BREAK.date()} for the per-stock query alone; they are "
        f"now {brk.date()} and {per_stock.date()}"
    )
    after = [s for s in delist if delist[s] > _STATEMENT_BREAK]
    before = [s for s in delist if delist[s] <= _STATEMENT_BREAK]
    kept_after = [s for s in after if s in last_row]
    kept_before = [s for s in before if s in last_row]
    assert len(after) == 70 and len(kept_after) == 70, (
        f"CAVEATS.md 10 rests on the break being one-sided — all "
        f"{len(after)} names delisted after {_STATEMENT_BREAK.date()} carry a "
        f"statement — and {len(after) - len(kept_after)} no longer do, so the "
        f"date is not where the retention ends any more"
    )
    assert (len(before), len(kept_before)) == (109, 14), (
        f"CAVEATS.md 10 says 14 of the 109 delisted on or before "
        f"{_STATEMENT_BREAK.date()} keep a statement; now "
        f"{len(kept_before)} of {len(before)}"
    )

    # The cut is a year and does no work: the names that kept filing after
    # leaving the board run 1,511 days past their delisting at the shortest,
    # and the one that stopped runs 48 days past it.
    still_filing = [s for s in kept_before
                    if (last_row[s] - delist[s]).days > 365]
    stopped = {s: (last_row[s] - delist[s]).days
               for s in kept_before if s not in still_filing}
    assert len(still_filing) == 13 and stopped == {"2475": 48}, (
        f"CAVEATS.md 10 explains the 14 as the vendor keeping the company "
        f"rather than the listing — 13 of them still filing long after they "
        f"left the board, and 2475 filing until 48 days after it left — and "
        f"{len(still_filing)} now are, with {stopped} stopping, so the "
        f"explanation has lost the evidence it was read off"
    )

    # Every other tree the caveat compares, each with its own break: the
    # latest delisting it holds no in-window row for.
    cover = {}
    for sub in ("fin_cf", "fin_bs", "shares", "month_rev", "per_pbr", "instflow"):
        held = {s for s in delist
                if pq.ParquetFile(TREES / f"{sub}/{s}.parquet").metadata.num_rows
                and len(_tree(TREES / f"{sub}/{s}.parquet", columns=["date"]))}
        missing = [delist[s] for s in delist if s not in held]
        cover[sub] = (len(held), str(max(missing).date()) if missing else None)
    assert {k: cover[k] for k in ("fin_cf", "fin_bs", "shares", "month_rev")} == {
            "fin_cf": (91, "2019-08-05"), "fin_bs": (97, "2019-03-29"),
            "shares": (123, "2020-05-28"), "month_rev": (155, "2019-10-14")}, (
        f"CAVEATS.md 10 says fin_cf/ carries rows for 91 of the 179, fin_bs/ "
        f"for 97, shares/ for 123 and month_rev/ for 155, breaking on "
        f"2019-08-05, 2019-03-29, 2020-05-28 and 2019-10-14; the trees give "
        f"(names, break) {cover}"
    )

    def every_month(sid):
        p = TREES / f"month_rev/{sid}.parquet"
        if not pq.ParquetFile(p).metadata.num_rows:
            return False
        got = set(_tree(p, columns=["date"])["date"])
        want = pd.date_range(min(got), delist[sid].to_period("M").to_timestamp(),
                             freq="MS") if got else []
        return bool(got) and set(want) <= got

    whole_rev = (sum(map(every_month, before)), sum(map(every_month, after)))
    assert whole_rev == (10, 38), (
        f"CAVEATS.md 10 says 10 of the 109 pre-break names carry every "
        f"revenue month from their first in the window to the one before their "
        f"delisting, against 38 of the 70 after it; the tree gives {whole_rev}"
    )

    daily = (cover["per_pbr"][0], cover["instflow"][0])
    assert daily == (179, 171), (
        f"CAVEATS.md 10 localises the loss to the filing endpoints by "
        f"contrast with the exchange's daily series, per_pbr/ covering all "
        f"179 and instflow/ 171; they now cover {daily}, and without the "
        f"contrast the loss could be a property of the delisted names themselves"
    )
    return (f"fin_is/ covers {len(have)}/{len(delist)} in-window delistings, "
            f"{empty_file} files empty at the source; all {len(kept_after)} "
            f"delisted after {_STATEMENT_BREAK.date()} kept against "
            f"{len(kept_before)}/{len(before)} before it ({len(still_filing)} "
            f"still filing), per-stock alone breaking on {per_stock.date()}; "
            f"other trees {cover}; revenue whole {whole_rev}"), len(delist)


# ---- Taiwan: when a fundamental could first have been read ------------------
def test_taiwan_filing_deadline_table_covers_the_data():
    """CAVEATS.md 9: every period end in the tree resolves to a deadline.

    `available_date` raises rather than returning NaT for a period end no rule
    covers, which is only a safeguard if something exercises it against the
    whole tree — a NaT would otherwise surface as rows quietly dropped from a
    join. This also pins the 2012 regime boundary, which is the reason the
    deadlines are a versioned table instead of two constants.
    """
    import pyarrow.parquet as pq

    from finmind_data.derive.available_date import available_date, with_available_date

    resolved = 0
    for sub, kind, n_ends in (("fin_is", "financial_statement", 62),
                              ("fin_bs", "financial_statement", 59),
                              ("fin_cf", "financial_statement", 62),
                              ("month_rev", "monthly_revenue", 188)):
        ends = set()
        for f in sorted(glob.glob(str(TREES / f"{sub}/*.parquet"))):
            if not pq.ParquetFile(f).metadata.num_rows:
                continue
            ends |= set(_tree(f, columns=["date"])["date"])
        # The count, not merely presence: this test's whole subject is that the
        # deadline table spans the tree, and a tree that had shrunk to one
        # period end would be spanned by any table at all.
        assert len(ends) == n_ends, (
            f"{sub}/ holds {len(ends)} distinct period ends against the {n_ends} "
            f"the deadline table was checked to span. A download that widened or "
            f"narrowed the tree owes filing_deadlines.csv a re-check"
        )
        got = available_date(sorted(ends), kind=kind)          # raises if unruled
        resolved += len(got)
        assert (got.to_numpy() > pd.Series(sorted(ends)).to_numpy()).all(), (
            f"{sub}: some rows are available on or before the period they "
            f"describe, which is look-ahead rather than a bound on it"
        )

    # 證交法 §36 as amended 2010-06-02, in force 2012-01-01: the annual report
    # goes from four months to three. The half-year goes from a 75-day
    # consolidated back-stop to 45 days a year later — §183 defers §36 I(2) to
    # 一百零二會計年度 — so the two rules break in different years and a constant
    # fitted to either side is wrong for a third of the window. 2012-06-30 is
    # the quarter that separates the two readings and is pinned for that.
    want = {"2010-12-31": "2011-04-30", "2011-06-30": "2011-09-13",
            "2011-12-31": "2012-03-31", "2012-06-30": "2012-09-13",
            "2013-06-30": "2013-08-14", "2024-12-31": "2025-03-31"}
    got = available_date(pd.to_datetime(list(want)))
    for (pe, exp), g in zip(want.items(), got):
        assert g == pd.Timestamp(exp), (
            f"README dates the {pe} period as available {exp}; "
            f"filing_deadlines.csv now gives {g.date()}"
        )

    # The lag is a research parameter, and `date` is never overwritten.
    d = _tree(TREES / "fin_is/2330.parquet")
    a = with_available_date(d)
    b = with_available_date(d, extra_days=15)
    assert (a["date"] == d["date"]).all() and (b["date"] == d["date"]).all(), (
        "with_available_date overwrote `date`, destroying the key that says "
        "which fiscal period a figure belongs to"
    )
    assert ((b["available_date"] - a["available_date"])
            == pd.Timedelta(days=15)).all(), "extra_days is not additive"

    # The result carries the caller's index. Without that, assigning it onto a
    # filtered frame aligns against a RangeIndex the frame no longer has and
    # fills NaN, which reads downstream as an unruled period rather than as a
    # join that silently missed.
    filtered = d[d["date"] >= "2015-01-01"].copy()
    assert filtered.index[0] != 0, "the case needs a frame whose index was cut"
    filtered["deadline"] = available_date(filtered["date"])
    assert filtered["deadline"].notna().all(), (
        f"available_date reindexed its input, so "
        f"{filtered['deadline'].isna().sum()} of {len(filtered)} deadlines "
        f"assigned onto a filtered frame came back NaT"
    )
    return (f"all {resolved} period ends in fin_is/fin_bs/fin_cf/month_rev "
            f"resolve; 2012 regime boundary holds; extra_days additive; the "
            f"result keeps the caller's index"), resolved


def test_taiwan_month_rev_date_is_the_following_month():
    """The premise the monthly-revenue deadline rests on.

    `month_rev.date` is the first of the month *after* the revenue month —
    2005-01-01 carries `revenue_month` 12 of 2004 — so the 10th-of-the-month
    deadline is nine days later, not a month and nine days. If FinMind ever
    re-keys the table on the revenue month, the deadline silently becomes a
    month too early and every monthly signal gains a month of look-ahead.
    """
    import pyarrow.parquet as pq

    rows = off = first = 0
    for f in sorted(glob.glob(str(TREES / "month_rev/*.parquet"))):
        if not pq.ParquetFile(f).metadata.num_rows:
            continue
        d = _tree(f, columns=["date", "revenue_month", "revenue_year"])
        dt = pd.to_datetime(d["date"])
        per = pd.to_datetime(dict(year=d["revenue_year"], month=d["revenue_month"],
                                  day=1))
        rows += len(d)
        first += int((dt.dt.day == 1).sum())
        off += int((((dt.dt.year * 12 + dt.dt.month)
                     - (per.dt.year * 12 + per.dt.month)) == 1).sum())
    assert rows == 324_016 and off == rows and first == rows, (
        f"README claims month_rev.date is the first of the month after the "
        f"revenue month on all 324,016 rows; the tree holds {rows:,}, "
        f"{rows - off:,} of them a different offset and {rows - first:,} not "
        f"the first of a month"
    )
    return (f"month_rev.date is the 1st of the month after revenue_month on "
            f"all {rows:,} rows"), rows


def test_taiwan_filing_dates_cover_the_statement_trees():
    """CAVEATS.md 9: every company holding a statement is dated.

    The panel exists to say when a figure became public, so a company missing
    from it silently falls back on the deadline — the very bound the caveat says
    is wrong for one quarter in fifteen. Asserting the frames match means a tree
    added later fails here rather than being dated by a rule nobody chose.

    The first assertion ranges over the companies whose tree carries rows, not
    over the tree files. A file is written for every name in the universe and
    176 of them are empty, so the two sets differ by whether the vendor served
    a statement — and a company with no statement has nothing that could fall
    back on a deadline, which is the whole failure this looks for. 175 of the
    176 are dated anyway, because the document server carries filings FinMind
    does not serve; the exception is 3718, a holding company listed on
    2026-09-10 whose page is empty on both the plain and the holdco route while
    its delisted predecessor's carries 382 documents. Requiring a filing date
    for a company that has filed nothing asks the server for a date that does
    not exist.

    The second assertion still ranges over every tree file, because it asks the
    opposite question: a dated code with no tree at all is a page answered for
    someone else, and narrowing that set would turn the 175 into failures.
    """
    import pyarrow.parquet as pq

    path = DATA / "filing_dates.parquet"
    if not path.exists():
        raise Skipped("filing_dates.parquet not built — "
                      "run `filing_dates.py` then `--consolidate`")
    d = pd.read_parquet(path)
    trees, holding = set(), set()
    for f in (TREES / "fin_is").glob("*.parquet"):
        trees.add(f.stem)
        if pq.read_metadata(f).num_rows:
            holding.add(f.stem)
    missing = sorted(holding - set(d["stock_id"]))
    assert not missing, (
        f"CAVEATS.md 9 dates all {len(holding)} companies whose statement "
        f"tree carries rows; {len(missing)} have no filing dates "
        f"({missing[:5]}), so their statements would be dated by the deadline "
        f"the caveat says is a bound and not a date"
    )
    extra = sorted(set(d["stock_id"]) - trees)
    assert not extra, (
        f"{len(extra)} companies carry filing dates but no statement tree "
        f"({extra[:5]}); the panel is keyed on the code its page was asked "
        f"for, so a stray code means a page answered for someone else"
    )
    undated = int(d["first_public"].isna().sum())
    assert not undated, f"{undated} rows carry no 上傳日期 and date nothing"
    assert len(d) == 164029, (
        f"CAVEATS.md 9 consolidates the documents to 164,029 "
        f"company-quarters; the panel holds {len(d):,}")

    # `other` marks the rows the server returns on a company's page under
    # another code. The README calls the four-digit ones earlier codes, which is
    # a claim about order: each company filed under them before it first filed
    # under its own.
    other = d["filed_as"] != d["stock_id"]
    six = other & d["filed_as"].str.fullmatch(r"\d{6}")
    four = other & d["filed_as"].str.fullmatch(r"\d{4}")
    counts = (int(other.sum()), int(six.sum()), int(four.sum()))
    assert counts == (1055, 603, 452), (
        f"CAVEATS.md 9 says 1,055 rows are filed under a code other than the "
        f"company's own, 603 under a six-digit registration number and 452 "
        f"under an earlier four-digit code; the panel has {counts}")
    own_first = d[~other].groupby("stock_id")["first_public"].min()
    four_last = d[four].groupby("stock_id")["first_public"].max()
    after = sorted(four_last.index[
        ~(four_last < own_first.reindex(four_last.index))])
    assert not after, (
        f"CAVEATS.md 9 calls the four-digit codes earlier ones, and {after} "
        f"filed under another four-digit code after first filing under its own")
    return (f"{len(d):,} company-quarters over {d['stock_id'].nunique():,} "
            f"companies, none undated; {len(holding):,} of {len(trees):,} "
            f"trees carry a statement and every one of them is dated", len(d))


def test_taiwan_filing_dates_drop_reports_filed_before_their_quarter():
    """CAVEATS.md 9: 98 documents from 13 companies were uploaded on or
    before the last day of the quarter their filename names, and the panel
    drops them.

    Counted off the collected histories, because the panel no longer holds
    them, and asserted on the panel as well: a panel consolidated without the
    drop fails there while the count still holds. That no observed date moved
    is a claim about the statements, so it ranges over every quarter the three
    trees hold, not only the window's.
    """
    import pyarrow.parquet as pq
    from finmind_data.collect.filing_dates import documents

    path = DATA / "filing_dates.parquet"
    if not path.exists() or not any(
            (TREES / "filing_dates").glob("*.parquet")):
        raise Skipped("filing_dates.parquet or the filing_dates/ histories "
                      "not built")
    d = pd.read_parquet(path)
    bad = d[d["first_public"].dt.normalize() <= d["period_end"]]
    assert not len(bad), (
        f"CAVEATS.md 9 says the panel drops every report uploaded on or "
        f"before the last day of its quarter; {len(bad)} rows are, first "
        f"{bad[['stock_id', 'period_end']].head(3).values.tolist()}")

    docs = documents()
    early = docs[docs["upload_ts"].dt.normalize() <= docs["period_end"]]
    got = (len(early), early["stock_id"].nunique())
    assert got == (98, 13), (
        f"CAVEATS.md 9 says 98 documents from 13 companies were uploaded on "
        f"or before the last day of the quarter their filename names; the "
        f"histories hold {got}")
    q1 = docs.loc[(docs["stock_id"] == "3087")
                  & (docs["period_end"].dt.month == 3)
                  & (docs["period_end"].dt.year >= 2005), "upload_ts"]
    assert (len(q1) and (q1.dt.month == 2).all()
            and q1.dt.day.between(22, 27).all()), (
        f"CAVEATS.md 9 says 3087 uploaded every report it numbered as a "
        f"first quarter from 2005 on between 22 and 27 February; the uploads "
        f"are {sorted(q1.dt.strftime('%Y-%m-%d'))}")
    inwin = sorted(early.loc[early["period_end"].between(COVERAGE_START,
                                                         COVERAGE_END),
                             "stock_id"].unique())
    assert inwin == ["3087", "9104"], (
        f"CAVEATS.md 9 says only 3087 and 9104 filed such a report inside "
        f"the window; {inwin} did")

    lost = set(zip(early["stock_id"], early["period_end"]))
    held = []
    for sid in sorted(early["stock_id"].unique()):
        for tree in ("fin_is", "fin_bs", "fin_cf"):
            f = TREES / tree / f"{sid}.parquet"
            if not f.exists() or not pq.read_metadata(f).num_rows:
                continue
            dates = pd.to_datetime(pd.read_parquet(f, columns=["date"])["date"])
            held += sorted((tree, sid, str(t.date())) for t in set(dates)
                           if (sid, t) in lost)
    assert not held, (
        f"CAVEATS.md 9 says no statement tree holds a quarter one of the 98 "
        f"was filed under, so no statement's observed date moved; {held[:3]}")

    years = set(zip(early["stock_id"], early["period_end"].dt.year))
    frame = d[d["period_end"].between(pd.Timestamp("2011-12-31"),
                                      _LATE_FRAME_END)]
    stay = sorted((s, str(p.date()))
                  for s, p in zip(frame["stock_id"], frame["period_end"])
                  if (s, p.year) in years)
    assert stay == [("3087", "2011-12-31"), ("3087", "2012-12-31")], (
        f"CAVEATS.md 9 says the frame keeps two reports from the years these "
        f"were filed in, 3087's under 2011-12-31 and 2012-12-31; it keeps "
        f"{stay}")
    return (f"{got[0]} documents from {got[1]} companies dropped, none of "
            f"their quarters in a statement tree; the panel holds none uploaded "
            f"by its quarter's end, and the frame keeps {len(stay)} from the "
            f"same years", len(docs))


def test_taiwan_statements_are_published_after_their_deadline():
    """CAVEATS.md 9: 6.56 % of the frame's quarters were published late.

    This is the number the caveat's claim rests on — that joining `fin_is` on
    `available_date` hands a trader one figure in fifteen before it existed. It
    is computed here against the deadline the module actually returns, so a
    change to `filing_deadlines.csv` moves it and this check says by how much.

    Scored on whatever `filing_deadlines.csv` returns, with no correction
    applied here. There used to be one: the table put the 第二季 45-day rule a
    year early, this check patched the FY2012 half-year back to 75 days so a
    table error would not be reported as a market fact, and the rate below was
    always the corrected one. The table now carries §183's deferral itself, so
    the patch is gone and the number is unchanged — which is the evidence that
    it was the same correction in both places.
    """
    from finmind_data.derive.available_date import available_date

    path = DATA / "filing_dates.parquet"
    if not path.exists():
        raise Skipped("filing_dates.parquet not built")
    d = pd.read_parquet(path)
    w = d[(d["period_end"] >= pd.Timestamp("2011-12-31"))
          & (d["period_end"] <= _LATE_FRAME_END)].reset_index(drop=True)
    dl = available_date(w["period_end"])
    late = (w["first_public"].dt.normalize() - dl).dt.days
    n_late = int((late > 0).sum())
    rate = n_late / len(w)
    got = (len(w), n_late, w.loc[late > 0, "stock_id"].nunique(),
           int(late[late > 0].quantile(0.9)), int(late.max()))
    assert got == (93520, 6138, 1421, 234, 1665), (
        f"CAVEATS.md 9 says 6,138 of the frame's 93,520 company-quarters, "
        f"across 1,421 companies, were published late, 234 days late at the "
        f"90th percentile and 1,665 at the worst; the panel gives {got}")
    assert math.isclose(rate, 0.0656, abs_tol=0.005), (
        f"CAVEATS.md 9 says 6.56 % of the frame's company-quarters were "
        f"published after the deadline; the rate is now {rate:.2%} "
        f"({n_late:,} of {len(w):,})"
    )
    med = int(late[late > 0].median())
    assert med == 15, (
        f"CAVEATS.md 9 puts the median lateness at 15 days; it is now {med}"
    )
    on_time = int(-late[late <= 0].median())
    assert on_time == 3, (
        f"CAVEATS.md 9 says an on-time filing lands a median 3 days ahead "
        f"of the deadline, which is what makes the deadline a tight bound; "
        f"it is now {on_time}"
    )
    return (f"{n_late:,}/{len(w):,} = {rate:.2%} published late, median "
            f"{med}d; on-time filings land {on_time}d early", len(w))


def test_taiwan_late_rate_falls_after_the_frame():
    """CAVEATS.md 9: the late rate falls from the frame's last year on, and
    right-censoring is a small part of the fall.

    A report enters `filing_dates.parquet` only once it is uploaded, so a
    period near the pull is short of the late reports still to come. The bound
    divides a period's late reports by the smallest share of late reports that
    the same period of any year in the frame had uploaded within as many days
    of its deadline as the file now reaches past this one's. A year nearer the
    pull holds no report later than its own reach and so scores a share of
    one, which lets every year in the frame take part without a special case.
    """
    from finmind_data.derive.available_date import available_date

    path = DATA / "filing_dates.parquet"
    if not path.exists():
        raise Skipped("filing_dates.parquet not built")
    d = pd.read_parquet(path)
    last = d["first_public"].max().normalize()
    assert last == pd.Timestamp("2026-08-31"), (
        f"CAVEATS.md 9 puts the file's last upload at 2026-08-31; it is now "
        f"{last.date()}")
    d = d[d["period_end"] >= pd.Timestamp("2011-12-31")].reset_index(drop=True)
    deadline = available_date(d["period_end"])
    d["late"] = (d["first_public"].dt.normalize() - deadline).dt.days
    d["reach"] = (last - deadline).dt.days
    frame = d[d["period_end"] <= _LATE_FRAME_END]
    late_days = [(p, g.loc[g["late"] > 0, "late"])
                 for p, g in frame.groupby("period_end")]

    def censored(g):
        """Observed late reports, and how many more the bound allows."""
        share = min((l <= g["reach"].iloc[0]).mean()
                    for p, l in late_days
                    if p.month == g.name.month and len(l))
        n_late = int((g["late"] > 0).sum())
        return pd.Series({"n": len(g), "late": n_late,
                          "missing": n_late * (1 / share - 1)})

    per = d[(d["period_end"] <= _LATE_FRAME_END)
            | (d["period_end"] == pd.Timestamp("2025-12-31"))].groupby(
        "period_end")[["late", "reach"]].apply(censored)

    annual = per[per.index.month == 12]
    annual.index = annual.index.year
    rate = annual["late"] / annual["n"]
    bound = ((annual["late"] + annual["missing"])
             / (annual["n"] + annual["missing"]))
    reach = d[d["period_end"].dt.month == 12].groupby(
        d["period_end"].dt.year)["reach"].first()
    before = rate.loc[2019:2023]
    quoted = {"FY2024": 0.0311, "FY2025": 0.0085, "FY2019-FY2023 min": 0.0666,
              "FY2019-FY2023 max": 0.0768}
    got = {"FY2024": rate[2024], "FY2025": rate[2025],
           "FY2019-FY2023 min": before.min(), "FY2019-FY2023 max": before.max()}
    off = {k: f"{got[k]:.2%}" for k, q in quoted.items()
           if not math.isclose(got[k], q, abs_tol=0.00005)}
    assert not off, (
        f"CAVEATS.md 9 says FY2024's annual reports read 3.11 % late and "
        f"FY2025's 0.85 %, against 6.66-7.68 % for FY2019-FY2023; the file "
        f"gives {off}")
    assert (reach[2025], reach[2024]) == (153, 518), (
        f"CAVEATS.md 9 says the last upload is 153 days past FY2025's annual "
        f"deadline and 518 days past FY2024's; it is {reach[2025]} and "
        f"{reach[2024]}")

    # A bound is quoted rounded up, since a rounded-down one is false.
    def ceil(x, places):
        return math.ceil(x * 10 ** places) / 10 ** places

    fr = per[per.index <= _LATE_FRAME_END]
    head = fr["late"].sum() / fr["n"].sum()
    lifted = ((fr["late"].sum() + fr["missing"].sum())
              / (fr["n"].sum() + fr["missing"].sum()))
    got = (ceil(bound[2025], 3), ceil(bound[2024], 3), ceil(lifted - head, 4))
    assert got == (0.015, 0.037, 0.0011), (
        f"CAVEATS.md 9 says FY2025 will read at most 1.5 % late and FY2024 "
        f"at most 3.7 % on the upload pattern of any year in the frame, and "
        f"that the same bound lifts the frame's 6.56 % by at most 0.11 points; "
        f"the bound gives {bound[2025]:.3%}, {bound[2024]:.3%} and "
        f"{lifted - head:.4%}")

    lag = (d["first_public"].dt.normalize() - d["period_end"]).dt.days
    med = lag[d["period_end"].dt.month == 12].groupby(
        d["period_end"].dt.year).median()
    early = med.loc[2011:2019]
    assert (early.min(), early.max(), med[2024]) == (87, 89, 72), (
        f"CAVEATS.md 9 says the annual reports' median upload came 87-89 "
        f"days after year end for FY2011-FY2019 and 72 days after for FY2024; "
        f"it is {early.min():.0f}-{early.max():.0f} and {med[2024]:.0f}")

    short = d[d["period_end"] <= pd.Timestamp("2023-12-31")]
    alt = (short["late"] > 0).mean()
    assert math.isclose(alt, 0.0681, abs_tol=0.00005), (
        f"CAVEATS.md 9 says a frame ending at 2023-12-31 reads 6.81 %; it "
        f"reads {alt:.2%}")
    return (f"annual late {before.min():.2%}-{before.max():.2%} FY2019-FY2023, "
            f"{rate[2024]:.2%} FY2024, {rate[2025]:.2%} FY2025; censoring bounds "
            f"FY2024 <= {bound[2024]:.3%}, FY2025 <= {bound[2025]:.3%}, frame "
            f"+{lifted - head:.3%}; median upload {early.min():.0f}-"
            f"{early.max():.0f}d -> {med[2024]:.0f}d; 2023-12-31 frame "
            f"{alt:.2%}", int(per["n"].sum()))


def test_taiwan_filing_deadline_q2_boundary_is_fy2013():
    """CAVEATS.md 9: the 第二季 rule starts a year after the rest of §36.

    The 2010-06-02 amendment to 證交法 §36 is in force 一百零一年一月一日 and the
    annual rule bites exactly there. The 第二季 rule does not, and §183 is where
    it says so: 一百零一年一月四日修正公布之第三十六條第一項第二款、自一百零二會計
    年度施行. That is the clause naming a 第二季財務報告, so through FY2012 the
    mid-year document is still the 半年度財務報告 on pre-2012 terms, and
    `filing_deadlines.csv` carries the two as separate rows.

    Read as a deadline the table was wrong for exactly one quarter and wrong by
    a lot — it scored 98 % of the FY2012 half-years late. What keeps this a
    check rather than a correction already banked is that the statute and the
    filings have to agree about *where* the boundary falls: FY2012 must score
    like FY2011 and FY2013 must not. A table edited until one quarter passed
    would still fail here if it put the break in the wrong year.
    """
    from finmind_data.derive.available_date import available_date
    from finmind_data.collect.filing_dates import CLASS_CONSOLIDATED

    path = DATA / "filing_dates.parquet"
    if not path.exists():
        raise Skipped("filing_dates.parquet not built")
    d = pd.read_parquet(path)

    def half(year):
        q = d[d["period_end"] == pd.Timestamp(f"{year}-06-30")]
        late = ((q["first_public"].dt.normalize()
                 - available_date(q["period_end"])).dt.days > 0)
        lag = int((q["first_public"].dt.normalize()
                   - q["period_end"]).dt.days.median())
        return len(q), float(late.mean()), lag

    n11, late11, lag11 = half(2011)
    n12, late12, lag12 = half(2012)
    n13, late13, lag13 = half(2013)
    assert late11 < 0.05 and late12 < 0.05 and lag11 == lag12 == 61, (
        f"CAVEATS.md 9 puts the FY2012 half-year under the same 75-day rule "
        f"as FY2011 — §183 defers §36 I(2) to 一百零二會計年度 — so the two should "
        f"score alike; FY2011 is {late11:.1%} late at a median {lag11}d and "
        f"FY2012 is {late12:.1%} at {lag12}d"
    )
    assert lag13 == 44 and late13 > 2 * max(late11, late12), (
        f"CAVEATS.md 9 reads the regime break off the filings at FY2013, "
        f"where the median lag drops to the 45-day rule; FY2013 files at a "
        f"median {lag13}d and is {late13:.1%} late against FY2012's {late12:.1%}"
    )
    # What the old row scored: FY2012's half-years against the 45-day rule the
    # table now starts at FY2013.
    q45 = (available_date(pd.Series([pd.Timestamp("2013-06-30")])).iloc[0]
           - pd.Timestamp("2013-06-30"))
    h = d[d["period_end"] == pd.Timestamp("2012-06-30")]
    old = int(((h["first_public"].dt.normalize() - h["period_end"]) > q45).sum())
    assert (old, len(h)) == (1592, 1619), (
        f"CAVEATS.md 9 says the 45-day rule scored 1,592 of the 1,619 FY2012 "
        f"half-years late; it scores {old:,} of {len(h):,}")
    # The lag is the symptom; the report type is the cause the paragraph names.
    was = d[d["period_end"] == pd.Timestamp("2012-06-30")]["class_code"].value_counts().idxmax()
    now = d[d["period_end"] == pd.Timestamp("2013-06-30")]["class_code"].value_counts().idxmax()
    assert was != CLASS_CONSOLIDATED and now == CLASS_CONSOLIDATED, (
        f"CAVEATS.md 9 reads the FY2012 boundary off the document as well as "
        f"the statute: the mid-year filing is a 我國GAAP 半年度財務報告 through "
        f"FY2012 and the IFRSs consolidated report ({CLASS_CONSOLIDATED}) from "
        f"FY2013. The modal class is {was} then {now}, so that corroboration is "
        f"gone and the boundary rests on §183 alone"
    )
    return (f"FY2011/FY2012 half-years {late11:.1%}/{late12:.1%} late at a "
            f"median {lag12}d under the 75-day rule; FY2013 {late13:.1%} at "
            f"{lag13}d under the 45-day one; modal report {was} then "
            f"{now}"), n11 + n12 + n13


def test_taiwan_observed_date_leaves_the_undatable_undated():
    """CAVEATS.md 9: the observed date covers `fin_is` bar 20 quarters.

    `observed_date` is only usable as a default if what it cannot date is both
    small and known, and the caveat claims it is: 20 of the window's 106,671
    `fin_is` company-quarters carry no filing, 15 of them an annual report from
    outside the span the document server holds for that company — filed before
    it listed, or after it stopped filing. Pinning the count means a panel that
    quietly loses coverage fails here, rather than dropping those rows out of a
    join that still looks like it ran.

    That they come back `NaT` rather than as the deadline is the other half of
    the claim, and the half that would be invisible if it broke: a substituted
    bound fills the column, and the rows then trade on a date nobody observed.
    """
    from finmind_data.derive.available_date import observed_date

    if not (DATA / "filing_dates.parquet").exists():
        raise Skipped("filing_dates.parquet not built")
    frames = []
    for f in sorted((TREES / "fin_is").glob("*.parquet")):
        d = _tree(f)
        if not len(d) or "date" not in d.columns:
            continue
        frames.append(pd.DataFrame({"stock_id": f.stem,
                                    "period_end": d["date"].drop_duplicates()}))
    p = pd.concat(frames, ignore_index=True)
    obs = observed_date(p["stock_id"], p["period_end"])
    undated = p[obs.isna()]
    assert (len(p), len(undated)) == (106_671, 20), (
        f"CAVEATS.md 9 says 20 of the window's 106,671 fin_is "
        f"company-quarters have no observed filing date; {len(undated)} of "
        f"{len(p):,} do. "
        f"A drop means the panel gained coverage and the caveat undersells it; "
        f"a rise means it lost some, and the rows it lost leave a join silently"
    )
    assert undated["stock_id"].nunique() == 19, (
        f"CAVEATS.md 9 spreads the 20 over 19 companies; they now fall on "
        f"{undated['stock_id'].nunique()}"
    )

    # The caveat explains them as periods outside what the server holds for the
    # company, not as a collector that missed rows. Asserted, because the two
    # have the same count and only one of them is a reason to go back.
    span = (pd.read_parquet(DATA / "filing_dates.parquet")
              .groupby("stock_id")["period_end"].agg(["min", "max"]))
    j = undated.join(span, on="stock_id")
    outside = int(((j["period_end"] < j["min"])
                   | (j["period_end"] > j["max"])).sum())
    assert outside == 15, (
        f"CAVEATS.md 9 puts 15 of the 20 outside the span the document "
        f"server holds for their company — a pre-listing or post-delisting "
        f"report the vendor kept and the server never carried; {outside} are "
        f"now. The rest sit inside the span and are absent from it, which is a "
        f"collection gap rather than a structural one"
    )
    return (f"{len(p) - len(undated):,}/{len(p):,} in-window fin_is quarters "
            f"carry an observed date; the {len(undated)} that do not are NaT, "
            f"{outside} of them outside their company's filing span", len(p))


def test_taiwan_observed_date_rolls_past_the_session_close():
    """CAVEATS.md 9: 14.66 % are untradable by the deadline, not 6.56 %.

    Three quarters of reports are uploaded after TWSE's 13:30 close, so a
    filing that lands *on* its deadline is not tradable until the next session
    and the deadline is a look-ahead for it. That is why `observed_date` rolls
    rather than truncating, and it is the difference between the 6.56 % of
    quarters filed late and the 14.66 % that could not be traded on in time —
    more than double, on the same frame and the same deadline.

    Scored on whatever `filing_deadlines.csv` returns, with no correction
    applied here — for the reason the check above it gives.
    """
    from finmind_data.derive.available_date import (available_date, observed_date,
                                             SESSION_CLOSE)

    path = DATA / "filing_dates.parquet"
    if not path.exists():
        raise Skipped("filing_dates.parquet not built")
    d = pd.read_parquet(path)
    w = d[(d["period_end"] >= pd.Timestamp("2011-12-31"))
          & (d["period_end"] <= _LATE_FRAME_END)].reset_index(drop=True)
    rolled = (w["first_public"] - w["first_public"].dt.normalize()) > SESSION_CLOSE
    assert math.isclose(rolled.mean(), 0.749, abs_tol=0.02), (
        f"CAVEATS.md 9 says three quarters of filings land after the 13:30 "
        f"close, which is what makes the roll worth doing; the share is now "
        f"{rolled.mean():.1%} ({int(rolled.sum()):,} of {len(w):,})"
    )

    dl = available_date(w["period_end"])
    untradable = ((observed_date(w["stock_id"], w["period_end"]) - dl).dt.days > 0)
    late = ((w["first_public"].dt.normalize() - dl).dt.days > 0)
    rate = untradable.mean()
    assert math.isclose(rate, 0.1466, abs_tol=0.005), (
        f"CAVEATS.md 9 says 14.66 % of the frame's company-quarters could "
        f"not be traded on by their deadline; the rate is now {rate:.2%} "
        f"({int(untradable.sum()):,} of {len(w):,})"
    )
    assert untradable.sum() > 2 * late.sum(), (
        f"CAVEATS.md 9 says the untradable share is more than double the "
        f"{late.mean():.2%} filed late, which is the whole reason the observed "
        f"date rolls; it is now {untradable.sum():,} against {late.sum():,}. If "
        f"the two have converged, the close-time roll is no longer load-bearing"
    )
    return (f"{int(rolled.sum()):,}/{len(w):,} = {rolled.mean():.1%} filed after "
            f"the close; {int(untradable.sum()):,} = {rate:.2%} untradable by "
            f"their deadline against {int(late.sum()):,} = {late.mean():.2%} "
            f"filed after it", len(w))


CHECKS = [
    test_taiwan_fundamentals_are_fiscal_dated,
    test_taiwan_statement_trees_drop_old_delistings,
    test_taiwan_filing_deadline_table_covers_the_data,
    test_taiwan_month_rev_date_is_the_following_month,
    test_taiwan_filing_dates_cover_the_statement_trees,
    test_taiwan_filing_dates_drop_reports_filed_before_their_quarter,
    test_taiwan_statements_are_published_after_their_deadline,
    test_taiwan_late_rate_falls_after_the_frame,
    test_taiwan_filing_deadline_q2_boundary_is_fy2013,
    test_taiwan_observed_date_leaves_the_undatable_undated,
    test_taiwan_observed_date_rolls_past_the_session_close,
]
