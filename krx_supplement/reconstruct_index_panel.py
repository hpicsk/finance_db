"""
reconstruct_index_panel.py
--------------------------
KOSPI 200 / KOSDAQ 150 일별 구성종목 패널 재구성기 (per-ticker, snapshot-truth)
================================================================================
collect_index_members.py 가 만든 *월말 스냅샷* 들 (= ground truth) 과
collect_index_changes.py 가 만든 *편입/편출 이벤트 로그* (= 정확한 변경일자) 를
종목별 timeline 으로 결합해 일별(business-day) 구성종목 패널을 만든다.

## 왜 이렇게 결합하는가
    KRX 의 이벤트 로그는 *불완전* 하다 — 상장폐지/합병으로 자동 편출되는 종목은
    REMOVE 이벤트가 기록되지 않는 경우가 많다 (예: 008810 LG종금, 1999 ADD 후
    REMOVE 없이 사라짐 — 2004 첫 스냅샷에는 이미 없음).

    → snapshot 을 ground truth 로 보고, event log 는 *변경 시점의 정확한 일자
      를 짚어주는 보조 데이터* 로 활용한다. 이벤트 로그가 누락한 변경은 합성
      이벤트(synthetic) 를 snapshot 일자에 주입해 정합성을 맞춘다.

## 입력
    output/index_members.parquet   : 월말 스냅샷 (date, index, ticker, name)
    output/index_changes.parquet   : 이벤트 로그 (date, index, action, isin, ticker, name)

## 출력
    output/index_membership_intervals.parquet
        한 (인덱스, 종목) 의 한 편입 구간 = 한 행
        | index | ticker | name | in_date | out_date | in_source | out_source |
        in_source / out_source ∈ {'log', 'synthetic', 'initial', None}
        - log       : KRX 이벤트 로그에 기록된 편입/편출 일자 (정확)
        - synthetic : snapshot diff 로 imputed 된 일자 (스냅샷 일자, 실제 변경
                      은 직전 스냅샷 다음날 ~ 해당 스냅샷일 사이에서 발생)
        - initial   : 첫 스냅샷 이전부터 편입돼 있던 종목 (정확한 시작일 미상)
        - None      : out_date 가 NaT 면 anchor (= 마지막 스냅샷) 시점까지 편입중

    output/index_panel_daily.parquet
        long-format: 인덱스 출시일 ~ anchor 일자, 영업일별 멤버
        | date | index | ticker |

    output/index_reconstruction_sanity.csv
        모든 스냅샷 일자에 대해 (실제 vs 재구성) 차집합 리포트.
        per-ticker 상태기계가 모든 스냅샷을 ground truth 로 따르므로 only_actual
        = only_recon = 0 이 정상.

    output/index_reconstruction_synthetic.csv
        합성 이벤트 목록 (감사용)

## 알고리즘 (종목별 상태기계)
    각 (인덱스, 종목 T) 에 대해:
      timeline = events_for_T + (snap_date, T_in_snap_bool) for each snap_date
      sorted by (date, event_first then snap)   # 같은 날짜에 이벤트가 스냅샷 직전 적용
      state ∈ {None, 'IN', 'OUT'}, 처음엔 None (=알 수 없음)

      for entry in timeline:
        if event ADD:
            None/OUT → IN (in_date=event 일자, source=log)
            IN       → ignore (이미 IN)
        if event REMOVE:
            None     → 직전까지 IN (initial 멤버) → close interval (NaT, T_d, log)
            IN       → close interval (in_date, T_d, log)
            OUT      → ignore
        if snap with in_bool=True:
            None     → IN (in_date=NaT, source=initial)
            OUT      → IN (in_date=snap_d, source=synthetic, missing ADD)
            IN       → consistent
        if snap with in_bool=False:
            None/OUT → consistent (state=OUT)
            IN       → close interval (in_date, snap_d, synthetic, missing REMOVE)

      end-of-loop: state == IN 이면 open interval (out_date=NaT)

    ⇒ snapshot 을 ground truth 로 따르므로 sanity check 가 자동으로 통과한다.

## 한계
    - synthetic 이벤트 일자 정밀도 = snapshot 주기 (월말). 실제 변경일은 직전
      스냅샷 다음날 ~ 해당 스냅샷일 사이. 월별 snapshot 으로 최대 ~22 영업일 오차.
    - 첫 스냅샷 이전 (KOSPI200: ~ 2004-01-29, KOSDAQ150: ~ 2015-07-30) 의
      편입/편출 일자는 이벤트 로그에 등장한 것만 정확. 미기록 이벤트는 첫 스냅샷
      일자로 imputed.
    - 'initial' 멤버의 시작일은 NaT (인덱스 출시일로 간주하거나 NaT 로 둠).

## 사용법
    python reconstruct_index_panel.py
    python reconstruct_index_panel.py --no-daily         # 일별 패널 생략
    python reconstruct_index_panel.py --start-kospi200 19940615 \\
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
    """종목 t 의 timeline = (date, kind, payload, source) 정렬 리스트.
    kind ∈ {'event', 'snap'}. 같은 날짜는 event → snap 순 (스냅샷이 post-event 상태)."""
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
    """이벤트(ADD/REMOVE) 한 entry 처리. 새 (state, in_date, in_source) 반환."""
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
    """스냅샷 한 entry 처리. 새 (state, in_date, in_source) 반환.
    스냅샷 in/out 과 현재 state 가 어긋나면 synthetic 이벤트 주입."""
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

    # 모든 종목 = 이벤트 + 스냅샷 의 합집합
    all_tickers = set(e["ticker"]) | {t for d in snap_dates for t in snap_state[d]}

    # 종목명 lookup (스냅샷 우선, 이벤트 보조)
    name_map = {}
    for t, n in zip(s["ticker"], s["name"]):
        if t and pd.notna(n) and n:
            name_map[t] = n
    for t, n in zip(e["ticker"], e["name"]):
        if t and t not in name_map and pd.notna(n) and n:
            name_map[t] = n

    # 종목별 이벤트 미리 그룹화
    e_by_ticker = {t: g.sort_values("date") for t, g in e.groupby("ticker")}

    intervals = []
    synthetic = []

    for t in all_tickers:
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
    parser = argparse.ArgumentParser(description="KRX 인덱스 일별 구성종목 패널 재구성")
    parser.add_argument("--start-kospi200", default=DEFAULT_PANEL_START["코스피 200"])
    parser.add_argument("--start-kosdaq150", default=DEFAULT_PANEL_START["코스닥 150"])
    parser.add_argument("--end", default=None,
                        help="패널 종료일 (default: 최신 스냅샷 일자)")
    parser.add_argument("--no-daily", action="store_true",
                        help="일별 패널 parquet 생성 생략")
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
