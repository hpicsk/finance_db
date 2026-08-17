# Session 2026-08-17, transcript call 769.
# Verify only the form column changed in the label file
# Verbatim as run; paths are the session's and it is an archive, not a runnable script.

cd /home/st/research/finance_db && /home/st/miniconda3/bin/python - <<'PY'
import pandas as pd, subprocess, io
old = pd.read_csv(io.StringIO(subprocess.run(
    ["git", "show", "HEAD:finmind_data/delisting_labels.csv"],
    capture_output=True, text=True).stdout), dtype=str)
new = pd.read_csv("finmind_data/delisting_labels.csv", dtype=str)
print("added columns:", set(new.columns) - set(old.columns))
print("dropped columns:", set(old.columns) - set(new.columns))
print("every other column byte-identical:",
      new[old.columns].fillna("").equals(old.fillna("")))
PY
