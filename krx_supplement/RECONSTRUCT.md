# Reconstructing the daily index membership panel

`reconstruct_index_panel.py` combines `index_members.parquet` (month-end
snapshots) with `index_changes.parquet` (the entry/exit event log) into a
**business-daily panel** and a set of **per-ticker membership spells**. Both
코스피 200 and 코스닥 150 are supported.

---

## Inputs

| File | Written by | Role |
|---|---|---|
| `output/index_members.parquet` | `collect_index_members.py` | month-end snapshots (ground truth) |
| `output/index_changes.parquet` | `collect_index_changes.py` | the exact entry/exit events (timing) |

The snapshots say *who*; the events say *when*. The reconstruction takes each
from the source that has it.

---

## Why the two cannot simply be concatenated

KRX's `index_changes` log is **incomplete**. Measured:

- KOSPI 200: 152 ISINs have an ADD and no REMOVE
- KOSDAQ 150: the same pattern, many times
- Rolling the event log forward on its own therefore leaves *ghosts* at the
  anchor — 12 names for KOSPI200 and 5 for KOSDAQ150 that are still counted as
  members long after they left.

Cases the log misses:

- `008810 LG종금` — added 1999-06-11, gone on a merger/delisting, no REMOVE
- `068270 셀트리온` — moved from KOSDAQ to KOSPI in 2018, dropped from
  코스닥 150 automatically, no REMOVE recorded
- `035720 카카오` — the same KOSDAQ-to-KOSPI move in 2017
- `036420 제이콘텐트리` — renamed through a split/merger, no REMOVE recorded

So the **snapshots are trusted as ground truth** and the events supply only the
exact dates. A change a snapshot proves happened but no event explains gets a
**synthetic** event injected at the snapshot's date.

---

## The algorithm — a state machine per ticker

For each (index, ticker T), build a timeline:

```
timeline = [(event_date, 'event', 'ADD'|'REMOVE', 'log')]
         + [(snap_date,  'snap',  T_in_snap_bool, None)]
sorted by (date, events before snapshots)   # a snapshot shows the post-event state
```

`state` is one of `{None, 'IN', 'OUT'}`, starting at `None`. Walking the
timeline:

| Input | Transition | Spell / synthetic |
|---|---|---|
| ADD, state in {None, OUT} | -> IN | in_date=event_d, source=log |
| ADD, state = IN | ignored (duplicate ADD) | — |
| REMOVE, state = IN | -> OUT | close the spell, out_source=log |
| REMOVE, state = None | -> OUT | close the spell (in_date=NaT, in_source=initial) |
| REMOVE, state = OUT | ignored (duplicate REMOVE) | — |
| snapshot in, state = None | -> IN | in_date=NaT, source=initial |
| snapshot in, state = OUT | -> IN | in_date=snap_d, source=**synthetic** (ADD missing) |
| snapshot in, state = IN | consistent | — |
| snapshot out, state = IN | -> OUT | close the spell, out_source=**synthetic** (REMOVE missing) |
| snapshot out, state in {None, OUT} | consistent, state -> OUT | — |

A ticker still `IN` when the loop ends gets an open spell (`out_date=NaT`).

---

## Outputs

### `output/index_membership_intervals.parquet`
One row per membership spell; a ticker that entered and left several times has
several rows.

| Column | Type | Meaning |
|---|---|---|
| `index` | str | `코스피 200` / `코스닥 150` |
| `ticker` | str | 6-digit issue code |
| `name` | str | short issue name (snapshot spelling preferred) |
| `in_date` | datetime | entry date; NaT means already in at the first snapshot |
| `in_source` | str | `log` / `synthetic` / `initial` |
| `out_date` | datetime | exit date, exclusive; NaT means still a member |
| `out_source` | str | `log` / `synthetic` / null (when NaT) |

Read a spell as `[in_date, out_date)`: the ticker is a member from `in_date` up
to but not including `out_date`, because KRX's effective date is the day the new
composition applies.

### `output/index_panel_daily.parquet`
The spells expanded to one row per business day.

| Column | Type |
|---|---|
| `date` | datetime (business day) |
| `index` | str |
| `ticker` | str |

The CLI `--start-*` defaults are the index launch dates — 코스피 200
1994-06-15, 코스닥 150 2015-07-07 — but the panel actually begins at the first
date the event log or a snapshot covers (KOSPI 200: 1999-01-04; see Limits).

### `output/index_reconstruction_sanity.csv`
Every snapshot date, cross-checked actual against reconstructed. Working
correctly, `only_actual = only_recon = 0` on every snapshot.

### `output/index_reconstruction_synthetic.csv`
The injected synthetic events, for audit.

---

## Results on the current data (as of 2026-04-27)

```
[코스피 200] 238 snapshots: 2004-01-30 ~ 2026-02-27 (200 anchor members)
[코스피 200] intervals: 730, synthetic events: 12
[코스피 200] sanity: 238/238 snapshots match exactly
[코스피 200] daily panel: 1,257,120 rows (1999-01-04 ~ 2026-02-27)

[코스닥 150] 113 snapshots: 2015-07-31 ~ 2026-02-27 (150 anchor members)
[코스닥 150] intervals: 656, synthetic events: 9
[코스닥 150] sanity: 113/113 snapshots match exactly
[코스닥 150] daily panel: 416,115 rows (2015-07-07 ~ 2026-02-27)
```

`in_source` / `out_source` distribution:

```
in_source                  out_source
  initial    331           log         1,015
  log      1,055           synthetic      21
                           NaN (still in) 350
```

Of 1,386 membership changes, 21 (~1.5 %) are imputed as synthetic events; the
other 98.5 % carry KRX's own exact date.

All 21 synthetic events are REMOVEs — automatic exits on a delisting or a move
to the other board that the event log never recorded (셀트리온, 카카오,
우리은행 among them).

---

## Limits

1. **Synthetic dates are only as precise as the snapshot spacing.** With
   month-end snapshots the true change falls somewhere between the day after the
   previous snapshot and the snapshot itself — up to about 22 business days.
   For more precision, re-collect with
   `collect_index_members.py --freq weekly` (or `daily`) and re-run the
   reconstruction.

2. **Between an index's launch and its first snapshot.**
   - KOSPI 200 launched 1994-06-15, but the event log starts 1999-01-04, so the
     daily panel starts there and does not cover 1994–1998. Membership over
     1999–2004 is accumulated from the event log alone, so the count grows
     gradually — one name on 1999-01-04, reaching 200 by the end of 2004. The
     2005–2024 analysis window is a complete 200 every day.
   - KOSDAQ 150 has the same issue over 2015-07-07..2015-07-30, the ~24 days
     after launch.

3. **Changes before the event log starts.** The reconstruction treats the log as
   KRX's *complete* change history. A KOSPI 200 change before 1999, or a
   KOSDAQ 150 change before 2010, would be invisible to it.

4. **The snapshots themselves are taken as correct.** Whatever the snapshot API
   returns for a date is treated as that day's true composition. Corporate
   actions can leave a day counting 199 or 201 depending on when the exchange
   booked them (KOSPI200 mode 200, range 200–202; KOSDAQ150 mode 150, range
   149–150); the reconstruction follows the snapshot rather than smoothing it.

5. **Board transfers (KOSDAQ to KOSPI).** A transferring name typically leaves
   코스닥 150 and joins 코스피 200. Using both panels together, no ticker
   appears in both on the same day — the move is one-directional.

---

## Usage

```bash
python reconstruct_index_panel.py

# the daily panel is the large output; skip it when only spells are wanted
python reconstruct_index_panel.py --no-daily

# custom panel bounds
python reconstruct_index_panel.py \
    --start-kospi200 19940615 \
    --start-kosdaq150 20150707 \
    --end 20251231
```

```python
import pandas as pd

iv = pd.read_parquet("output/index_membership_intervals.parquet")

# members of an index on a given date
def members_at(iv, idx, d):
    d = pd.Timestamp(d)
    sub = iv[iv["index"] == idx]
    in_d = sub["in_date"].fillna(pd.Timestamp.min)
    out_d = sub["out_date"].fillna(pd.Timestamp.max)
    return sub.loc[(in_d <= d) & (d < out_d), "ticker"].tolist()

print(len(members_at(iv, "코스피 200", "2020-06-30")))  # about 200

# one ticker's membership history
samsung = iv[(iv["index"] == "코스피 200") & (iv["ticker"] == "005930")]
print(samsung)

# drop the imputed dates, where the exact date matters
exact_in_only = iv[iv["in_source"] == "log"]
exact_both = iv[(iv["in_source"] == "log") &
                (iv["out_source"].isin(["log", None]))]
```

---

## Relation to the collectors

`reconstruct_index_panel.py` consumes the two collectors' outputs unchanged, and
both collectors are kept for re-collection and for the sanity check:

- `collect_index_members.py` — new month-end snapshots (the anchor, and the
  input the reconciliation is against)
- `collect_index_changes.py` — a fresh event log
- `reconstruct_index_panel.py` — combines the two

After refreshing either input, only `reconstruct_index_panel.py` needs re-running.
