"""Daily KOSPI 200 / KOSDAQ 150 membership, per ticker, snapshots as truth.

Combines the month-end snapshots `collect_index_members.py` writes with the
entry/exit event log `collect_index_changes.py` writes, resolving each ticker
on its own timeline into a business-daily membership panel.

**Why both, rather than the event log alone.** The log is incomplete: a name
leaving the index because it delisted or merged often has no REMOVE event at
all — 008810 (LG종금) was added in 1999, never removed, and is simply absent
from the first snapshot in 2004. So the snapshots are the ground truth and the
log supplies only the *exact date* a change took effect. Where the log has no
event for a change a snapshot proves happened, a synthetic event is injected at
the snapshot date.

Input
    ``output/index_members.parquet``  month-end snapshots
                                      (date, index, ticker, name)
    ``output/index_changes.parquet``  the event log
                                      (date, index, action, isin, ticker, name)

Output
    ``output/index_membership_intervals.parquet`` — one row per (index, ticker)
    spell of membership:

        | index | ticker | name | in_date | out_date | in_source | out_source |

    with ``in_source`` / ``out_source`` in {log, synthetic, initial, None}

        ``log``        the date KRX recorded for the entry or exit — exact
        ``synthetic``  imputed from a snapshot difference, so it carries the
                       snapshot's date while the change itself fell somewhere
                       between the previous snapshot and this one
        ``initial``    already a member at the first snapshot, so the true start
                       is unknown
        ``None``       ``out_date`` is NaT: still a member at the anchor, which
                       is the last snapshot

    ``output/index_panel_daily.parquet`` — long format, one row per business day
    of membership from the index's launch to the anchor: | date | index | ticker |

    ``output/index_reconstruction_sanity.csv`` — for every snapshot date, the
    two set differences between the actual snapshot and the reconstruction.
    The state machine follows every snapshot as truth, so both columns being
    zero is the expected result rather than a passing grade.

    ``output/index_reconstruction_synthetic.csv`` — the injected events, for audit.

Algorithm, a state machine per (index, ticker)
    timeline = that ticker's events, plus (snapshot date, in-snapshot?) for
    every snapshot, sorted by date with events before snapshots on a shared
    date — a snapshot shows the state *after* that day's events.

    state is one of {None, IN, OUT}, starting at None, meaning not yet known.

        ADD event      None/OUT -> IN      (in_date = event date, source=log)
                       IN       -> ignored, already in
        REMOVE event   None     -> it was an initial member: close the spell
                                   (NaT, event date, log)
                       IN       -> close the spell (in_date, event date, log)
                       OUT      -> ignored
        snapshot, in   None     -> IN      (in_date = NaT, source=initial)
                       OUT      -> IN      (source=synthetic; the ADD is missing)
                       IN       -> consistent
        snapshot, out  None/OUT -> consistent
                       IN       -> close the spell (source=synthetic; the
                                   REMOVE is missing)

    A ticker still IN when the timeline ends gets an open spell, out_date = NaT.

Limits
    A synthetic date is only as precise as the snapshot spacing: the change
    happened somewhere between the day after the previous snapshot and the
    snapshot itself, so month-end snapshots put it within about 22 business
    days.

    Before the first snapshot (KOSPI200 2004-01-29, KOSDAQ150 2015-07-30) only
    changes the event log recorded are exact; the rest are imputed to the first
    snapshot date.

    An ``initial`` member's start date is NaT rather than the index launch date,
    which is not the same claim.

    python reconstruct_index_panel.py
    python reconstruct_index_panel.py --no-daily          # skip the daily panel
    python reconstruct_index_panel.py --start-kospi200 19940615 \
                                      --start-kosdaq150 20150707
"""

import argparse
from pathlib import Path

import pandas as pd

from krx_utils import save_with_csv, setup_logging

log = setup_logging()

OUT = Path(__file__).parent / "output"

DEFAULT_PANEL_START = {
    "코스피 200": "19940615",
    "코스닥 150": "20150707",
}


def load():
    snaps = pd.read_parquet(OUT / "index_members.parquet")
    events = pd.read_parquet(OUT / "index_changes.parquet")
    snaps["date"] = pd.to_datetime(snaps["date"])
    events["date"] = pd.to_datetime(events["date"])
    return snaps, events


def _build_ticker_timeline(t, e_by_ticker, snap_dates, snap_state):
    """One ticker's timeline: a sorted list of (date, kind, payload, source).

    ``kind`` is 'event' or 'snap'. On a shared date the event sorts first,
    because a snapshot shows the state after that day's events."""
    timeline = []
    if t in e_by_ticker:
        for _, r in e_by_ticker[t].iterrows():
            timeline.append((r["date"], "event", r["action"], "log"))
    for d in snap_dates:
        timeline.append((d, "snap", t in snap_state[d], None))
    timeline.sort(key=lambda x: (x[0], 0 if x[1] == "event" else 1))
    return timeline


def _process_event(state, in_date, in_source, payload, src, d, t,
                   index_name, name_map, intervals):
    """Apply one ADD/REMOVE entry. Returns the new (state, in_date, in_source)."""
    if payload == "ADD":
        if state == "IN":
            return state, in_date, in_source  # duplicate ADD
        return "IN", d, src
    # REMOVE
    if state in ("IN", None):
        intervals.append({
            "index": index_name, "ticker": t,
            "name": name_map.get(t),
            "in_date": in_date if state == "IN" else pd.NaT,
            "in_source": in_source if state == "IN" else "initial",
            "out_date": d, "out_source": src,
        })
        return "OUT", None, None
    return state, in_date, in_source  # noise REMOVE on OUT


def _process_snap(state, in_date, in_source, in_bool, d, t,
                  index_name, name_map, intervals, synthetic):
    """Apply one snapshot entry. Returns the new (state, in_date, in_source).

    Where the snapshot and the current state disagree, the event log missed a
    change, and a synthetic event is injected to carry it."""
    if in_bool:
        if state is None:
            return "IN", pd.NaT, "initial"
        if state == "OUT":
            synthetic.append({"index": index_name, "date": d,
                              "action": "ADD", "ticker": t,
                              "name": name_map.get(t)})
            return "IN", d, "synthetic"
        return state, in_date, in_source  # IN consistent
    # snap False
    if state == "IN":
        intervals.append({
            "index": index_name, "ticker": t,
            "name": name_map.get(t),
            "in_date": in_date, "in_source": in_source,
            "out_date": d, "out_source": "synthetic",
        })
        synthetic.append({"index": index_name, "date": d,
                          "action": "REMOVE", "ticker": t,
                          "name": name_map.get(t)})
        return "OUT", None, None
    if state is None:
        return "OUT", None, None
    return state, in_date, in_source  # OUT consistent


def reconstruct_one(events: pd.DataFrame, snaps: pd.DataFrame, index_name: str):
    e = events[events["index"] == index_name].copy()
    e = e[e["ticker"].notna() & (e["ticker"] != "")].sort_values("date")
    s = snaps[snaps["index"] == index_name].copy().sort_values(["date", "ticker"])

    if s.empty:
        log.error("No snapshots for %s — cannot anchor", index_name)
        return None

    snap_dates = sorted(s["date"].unique())
    snap_state = {d: set(s.loc[s["date"] == d, "ticker"]) for d in snap_dates}
    log.info("[%s] %d snapshots: %s ~ %s (%d members at anchor)",
             index_name, len(snap_dates), snap_dates[0].date(),
             snap_dates[-1].date(), len(snap_state[snap_dates[-1]]))

    # every ticker either source mentions
    all_tickers = set(e["ticker"]) | {t for d in snap_dates for t in snap_state[d]}

    # name lookup, preferring the snapshot spelling over the event log
    name_map = {}
    for t, n in zip(s["ticker"], s["name"]):
        if t and pd.notna(n) and n:
            name_map[t] = n
    for t, n in zip(e["ticker"], e["name"]):
        if t and t not in name_map and pd.notna(n) and n:
            name_map[t] = n

    # group the events by ticker once, rather than filtering per ticker
    e_by_ticker = {t: g.sort_values("date") for t, g in e.groupby("ticker")}

    intervals = []
    synthetic = []

    # sorted(), not `all_tickers`: str hashing is randomised per process, so
    # iterating the set writes index_reconstruction_synthetic.csv in a different
    # row order on every run. `intervals` is sorted before it is written and
    # hides this; the synthetic log is not, and a re-run then shows up as a diff
    # against the committed artifact with nothing actually changed.
    for t in sorted(all_tickers):
        timeline = _build_ticker_timeline(t, e_by_ticker, snap_dates, snap_state)
        state, in_date, in_source = None, None, None

        for d, kind, payload, src in timeline:
            if kind == "event":
                state, in_date, in_source = _process_event(
                    state, in_date, in_source, payload, src, d, t,
                    index_name, name_map, intervals,
                )
            else:
                state, in_date, in_source = _process_snap(
                    state, in_date, in_source, payload, d, t,
                    index_name, name_map, intervals, synthetic,
                )

        if state == "IN":
            intervals.append({
                "index": index_name, "ticker": t,
                "name": name_map.get(t),
                "in_date": in_date, "in_source": in_source,
                "out_date": pd.NaT, "out_source": None,
            })

    iv_df = (pd.DataFrame(intervals)
             .sort_values(["index", "in_date", "ticker"], na_position="first")
             .reset_index(drop=True))
    syn_df = pd.DataFrame(synthetic)

    log.info("[%s] intervals: %d, synthetic events: %d",
             index_name, len(iv_df), len(syn_df))

    return {
        "intervals": iv_df,
        "synthetic": syn_df,
        "snap_dates": snap_dates,
        "snap_state": snap_state,
        "name_map": name_map,
    }


def membership_at_from_intervals(iv_df: pd.DataFrame, query_date,
                                 floor=pd.Timestamp.min) -> set:
    """Members of an index on ``query_date``.

    ``floor`` is the date assigned to ``initial`` members whose true in_date is
    NaT (unknown — they were already in the index at the first snapshot). Pass
    the first snapshot date so these members are not asserted *before* there is
    any evidence of their membership (which would fabricate pre-first-snapshot
    constituents and back-project the snapshot's survivors).
    """
    in_d = iv_df["in_date"].fillna(floor)
    out_d = iv_df["out_date"].fillna(pd.Timestamp.max)
    mask = (in_d <= query_date) & (query_date < out_d)
    return set(iv_df.loc[mask, "ticker"])


def sanity_check(snaps: pd.DataFrame, recon: dict, index_name: str) -> pd.DataFrame:
    iv = recon["intervals"]
    iv_idx = iv[iv["index"] == index_name]
    rows = []
    first_snap = recon["snap_dates"][0]
    for d in recon["snap_dates"]:
        actual = recon["snap_state"][d]
        recon_set = membership_at_from_intervals(iv_idx, d, floor=first_snap)
        only_a = actual - recon_set
        only_r = recon_set - actual
        rows.append({
            "index": index_name, "date": d,
            "n_actual": len(actual), "n_recon": len(recon_set),
            "matches": len(actual & recon_set),
            "only_actual": len(only_a), "only_recon": len(only_r),
            "only_actual_tickers": ",".join(sorted(only_a)) if only_a else "",
            "only_recon_tickers": ",".join(sorted(only_r)) if only_r else "",
        })
    return pd.DataFrame(rows).sort_values(["index", "date"]).reset_index(drop=True)


def build_daily_panel(iv_df: pd.DataFrame, index_name: str,
                      panel_start: pd.Timestamp,
                      panel_end: pd.Timestamp,
                      first_snap: pd.Timestamp) -> pd.DataFrame:
    iv = iv_df[iv_df["index"] == index_name]
    if iv.empty:
        return pd.DataFrame(columns=["date", "index", "ticker"])
    rows = []
    for _, r in iv.iterrows():
        # `initial` members (NaT in_date) are only known to be members from the
        # first snapshot onward — flooring at the index launch date would
        # fabricate ~a decade of membership and back-project the first
        # snapshot's survivors (survivorship bias). Real log-event ADDs keep
        # their actual (possibly pre-first-snapshot) in_date.
        in_d = r["in_date"] if pd.notna(r["in_date"]) else first_snap
        out_d = r["out_date"] if pd.notna(r["out_date"]) else (panel_end + pd.Timedelta(days=1))
        start = max(in_d, panel_start)
        end_excl = min(out_d, panel_end + pd.Timedelta(days=1))
        if start >= end_excl:
            continue
        bdays = pd.bdate_range(start, end_excl - pd.Timedelta(days=1))
        for bd in bdays:
            rows.append((bd, index_name, r["ticker"]))
    return pd.DataFrame(rows, columns=["date", "index", "ticker"])


def main():
    parser = argparse.ArgumentParser(description="Reconstruct the daily KRX index membership panel")
    parser.add_argument("--start-kospi200", default=DEFAULT_PANEL_START["코스피 200"])
    parser.add_argument("--start-kosdaq150", default=DEFAULT_PANEL_START["코스닥 150"])
    parser.add_argument("--end", default=None,
                        help="last date of the panel (default: the latest snapshot)")
    parser.add_argument("--no-daily", action="store_true",
                        help="skip writing the daily panel parquet")
    args = parser.parse_args()

    snaps, events = load()
    log.info("Loaded snapshots: %d rows, events: %d rows", len(snaps), len(events))

    panel_starts = {
        "코스피 200": pd.Timestamp(args.start_kospi200),
        "코스닥 150": pd.Timestamp(args.start_kosdaq150),
    }

    all_iv, all_sn, all_dl, all_syn = [], [], [], []
    for idx in ["코스피 200", "코스닥 150"]:
        log.info("─" * 60)
        recon = reconstruct_one(events, snaps, idx)
        if recon is None:
            continue

        all_iv.append(recon["intervals"])
        if not recon["synthetic"].empty:
            all_syn.append(recon["synthetic"])

        sn = sanity_check(snaps, recon, idx)
        all_sn.append(sn)
        n_perfect = (sn["only_actual"] + sn["only_recon"] == 0).sum()
        log.info("[%s] sanity: %d/%d snapshots match exactly", idx, n_perfect, len(sn))

        if not args.no_daily:
            anchor = recon["snap_dates"][-1]
            panel_end = pd.Timestamp(args.end) if args.end else anchor
            daily = build_daily_panel(recon["intervals"], idx, panel_starts[idx],
                                      panel_end, recon["snap_dates"][0])
            log.info("[%s] daily panel: %d rows (%s ~ %s)", idx, len(daily),
                     daily["date"].min().date() if not daily.empty else None,
                     daily["date"].max().date() if not daily.empty else None)
            all_dl.append(daily)

    iv_df = pd.concat(all_iv, ignore_index=True) if all_iv else pd.DataFrame()
    sn_df = pd.concat(all_sn, ignore_index=True) if all_sn else pd.DataFrame()

    out_iv = OUT / "index_membership_intervals.parquet"
    save_with_csv(iv_df, out_iv)
    log.info("Saved: %s  (%d intervals)", out_iv, len(iv_df))

    out_sn = OUT / "index_reconstruction_sanity.csv"
    sn_df.to_csv(out_sn, index=False, encoding="utf-8-sig")
    log.info("Saved: %s  (%d snapshot rows)", out_sn, len(sn_df))

    if all_syn:
        syn_df = pd.concat(all_syn, ignore_index=True)
        out_sy = OUT / "index_reconstruction_synthetic.csv"
        syn_df.to_csv(out_sy, index=False, encoding="utf-8-sig")
        log.info("Saved: %s  (%d synthetic events)", out_sy, len(syn_df))

    if not args.no_daily and all_dl:
        dl_df = pd.concat(all_dl, ignore_index=True)
        dl_df = dl_df.sort_values(["index", "date", "ticker"]).reset_index(drop=True)
        out_dl = OUT / "index_panel_daily.parquet"
        dl_df.to_parquet(out_dl, index=False)
        log.info("Saved: %s  (%d daily-member rows)", out_dl, len(dl_df))


if __name__ == "__main__":
    main()
