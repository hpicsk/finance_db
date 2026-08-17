# Session 2026-08-17, transcript call 756.
# Mutation-test the new check
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
  "cash deal lands in the band (2470 swap->cash)":
      lambda d: d.assign(form=d["form"].mask(d["stock_id"] == "2470", "cash")),
  "a failure carries a form (2475)":
      lambda d: d.assign(form=d["form"].mask(d["stock_id"] == "2475", "swap")),
  "an unstated form is read in (3080)":
      lambda d: d.assign(form=d["form"].mask(d["stock_id"] == "3080", "swap")),
  "form column emptied":
      lambda d: d.assign(form=pd.NA),
  "a cash deal dragged below the 0.70 cut (8480 -> swap, 2452 -> cash)":
      lambda d: d.assign(form=d["form"].mask(d["stock_id"] == "8480", "swap")
                                       .mask(d["stock_id"] == "2452", "cash")),
}
for name, fn in muts.items():
    d = pd.read_csv(BAK, dtype={"stock_id": str})
    fn(d).to_csv(P, index=False)
    try:
        run(); print(f"  NOT CAUGHT  {name}")
    except AssertionError as e:
        print(f"  caught      {name}\n              -> {str(e).splitlines()[0][:110]}")
shutil.copy(BAK, P)
print("\nrestored:", pd.read_csv(P, dtype={'stock_id': str})["form"].value_counts().to_dict())
PY
