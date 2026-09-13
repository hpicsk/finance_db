"""Where this package keeps each kind of file, named once.

Five directories, sorted by what a file is rather than by which script wrote it.

``raw/``       what a vendor answered, as it answered it: one dated vintage per
               sweep, never edited afterwards. Gitignored, about 1 GB a vintage.
``trees/``     the per-stock panel the loaders and the checks read: the graded
               vintage with its repairs applied. Gitignored, 1.6 GB.
``data/``      the small derived artifacts the checks read and git tracks: the
               universe, the calendar, the spans, the event tables, the labels.
``records/``   what each repair added or replaced, the old value beside the new,
               so a tree can be read back to what the vendor first served.
``_internal/`` logs, run state and fingerprints. Nothing a reader needs.

Every module takes its paths from here. Twenty-eight modules used to spell
``Path(__file__).resolve().parent / "ohlcv"``, which is right until the file
moves.
"""
from pathlib import Path

PKG = Path(__file__).resolve().parent
RAW = PKG / "raw"
TREES = PKG / "trees"
DATA = PKG / "data"
RECORDS = PKG / "records"
# The date-keyed price tape `collect/tape_universe.py` sweeps: every 4-digit code
# that traded each session, four columns. `raw/<vintage>/ohlcv/` carries the
# same sessions with the full schema from the first dated sweep on.
TAPE = RAW / "tape"
INTERNAL = PKG / "_internal"
TOKEN_FILE = PKG / ".token"
