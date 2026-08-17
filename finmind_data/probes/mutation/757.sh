# Session 2026-08-17, transcript call 757.
# Re-run mutation tests after reordering
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && /home/st/miniconda3/bin/python - <<'PY'
import importlib.util, shutil, pandas as pd
from pathlib import Path
P = Path("finmind_data/delisting_labels.csv")
BAK = Path("/tmp/claude-1001/-home-st-research-finance-db-finmind-data/013bad53-ea1c-455c-8f0b-2e6e1120e8d2/scratchpad/labels.bak.csv")
shutil.copy(P, BAK)

def run():
    spec = importlib.util.spec_from_file_location("ta", "finmind_data/test_assertions.py")
    ta = importlib.util.module_from_spec(spec); spec.loader.exec_module(ta)
    return ta.test_taiwan_cash_payouts_land_outside_the_band()

muts = {
  "a cash deal lands in the band (2470 swap->cash)":
      lambda d: d.assign(form=d["form"].mask(d["stock_id"] == "2470", "cash")),
  "a cash deal below the 0.70 cut but outside the band (2335 -> cash payout)":
      lambda d: d.assign(label=d["label"].mask(d["stock_id"] == "2335", "merger"),
                         form=d["form"].mask(d["stock_id"] == "2335", "cash")),
  "a failure carries a form (2475)":
      lambda d: d.assign(form=d["form"].mask(d["stock_id"] == "2475", "swap")),
  "an unstated form is read in (3080)":
      lambda d: d.assign(form=d["form"].mask(d["stock_id"] == "3080", "swap")),
  "form column emptied":
      lambda d: d.assign(form=pd.NA),
  "a 13th band exchange added, p moves (5854 out-of-band -> unstated)":
      lambda d: d.assign(form=d["form"].mask(d["stock_id"] == "5854", pd.NA)),
}
for name, fn in muts.items():
    fn(pd.read_csv(BAK, dtype={"stock_id": str})).to_csv(P, index=False)
    try:
        run(); print(f"  NOT CAUGHT  {name}")
    except AssertionError as e:
        print(f"  caught  {name}\n          -> {str(e).splitlines()[0][:100]}")
shutil.copy(BAK, P)
print("\nrestored ok:", run()[1] == 18)
PY
