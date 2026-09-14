#!/usr/bin/env bash
# finance_db/run_assertions.sh — run every package's claim assertions.
#
# This directory is a container and holds no test logic. Each package owns the
# assertions behind the claims its own documentation makes, in its own
# test_assertions.py; this script finds them, runs them, and fails if any
# package fails. There is no CI, so this is the gate.
#
# Prerequisites: the data trees populated (marcap/ cloned, caches built) and a
# conda env carrying the packages' dependencies on PATH — the preflight below
# names any that are missing rather than leaving it to this comment. E.g.
#   source /home/st/miniconda3/bin/activate

set -uo pipefail
cd "$(dirname "$0")"

files=(*/test_assertions.py)
if [ ! -e "${files[0]}" ]; then
  echo "no */test_assertions.py found — wrong directory?" >&2
  exit 1
fi

# The study window is duplicated in each package whose figures are quoted on
# one, because the container holds no shared module to import it from. Drift
# between the copies would silently change what every downstream check measures
# without failing anything, so the copies are compared here rather than trusted.
# A package holding data and no study defines neither constant and is not
# counted: its checks are quoted on the span its own downloads reached, which
# moves when they are re-run and is nobody else's to agree with.
windows=$(grep -h '^WIN_START\|^WIN_END' "${files[@]}" | sort -u)
if [ "$(echo "$windows" | wc -l)" -ne 2 ]; then
  echo "FAIL  study-window constants disagree across packages:" >&2
  echo "$windows" >&2
  exit 1
fi

# The runner block at the foot of every test_assertions.py — the loop that
# calls CHECKS, holds `n` against populations.json and decides the exit code —
# is duplicated per package for the same reason the window is, and drifted the
# same way: five copies sat at five revisions, and only one of them could
# re-seed a population that had legitimately moved. The copies are compared
# here, from `if __name__ == "__main__":` to end of file, before any check
# runs. Edit one, then copy it to the rest.
runner_of() { sed -n '/^if __name__ == "__main__":/,$p' "$1" | md5sum | cut -d' ' -f1; }
if [ "$(for f in "${files[@]}"; do runner_of "$f"; done | sort -u | wc -l)" -ne 1 ]; then
  echo "FAIL  the runner block differs between packages' test_assertions.py:" >&2
  for f in "${files[@]}"; do echo "  $(runner_of "$f")  $f" >&2; done
  exit 1
fi

# A check the runner never calls reports nothing and fails nothing, which reads
# from the outside exactly like a check that passes. Every `def test_*` in a
# package must therefore appear in a CHECKS list; the omission is invisible in
# the per-package output, which is why it is caught here. A package may keep its
# checks in `<pkg>/checks/<topic>.py` modules, each with its own CHECKS, which
# `test_assertions.py` concatenates as `*<topic>.CHECKS`: then every check
# module has to be concatenated too, or a whole module's checks never run.
unregistered=$(python - "${files[@]}" <<'EOF'
import ast, sys
from pathlib import Path
bad = []
for path in sys.argv[1:]:
    runner = Path(path)
    modules = sorted(p for p in (runner.parent / "checks").glob("*.py")
                     if not p.name.startswith("_"))
    defined, registered = [], set()
    for f in [runner, *modules]:
        tree = ast.parse(f.read_text())
        defined += [f"{f}: {n.name}" for n in tree.body
                    if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
        registered |= {e.id for n in tree.body if isinstance(n, ast.Assign)
                       and any(getattr(t, "id", "") == "CHECKS" for t in n.targets)
                       for e in n.value.elts if isinstance(e, ast.Name)}
    bad += [d for d in defined if d.split(": ")[1] not in registered]
    if modules:
        tree = ast.parse(runner.read_text())
        spliced = {e.value.value.id for n in tree.body if isinstance(n, ast.Assign)
                   and any(getattr(t, "id", "") == "CHECKS" for t in n.targets)
                   for e in n.value.elts if isinstance(e, ast.Starred)
                   and isinstance(e.value, ast.Attribute) and e.value.attr == "CHECKS"
                   and isinstance(e.value.value, ast.Name)}
        bad += [f"{path}: checks/{m.stem}.py is not spliced into CHECKS"
                for m in modules if m.stem not in spliced]
print("\n".join(bad))
EOF
)
if [ -n "$unregistered" ]; then
  echo "FAIL  assertions defined but absent from CHECKS, so they never run:" >&2
  echo "$unregistered" >&2
  exit 1
fi

# The suite's verdict must not depend on which interpreter invoked it. An env
# short of one module turns the handful of checks that reach it into ERROR lines
# that read like data problems, while every other package reports a clean pass —
# and which env is active can differ between two runs on the same machine, so a
# header comment naming the right one is read by nobody. Every module reachable
# from a test_assertions.py is resolved here, before any check runs, so a wrong
# interpreter is named as one. It also closes the regenerate-and-compare checks:
# a committed artifact diffed against a fresh run says nothing about drift if the
# two runs had different libraries underneath them.
preflight=$(python - "${files[@]}" <<'EOF'
import ast, importlib.util, sys
from pathlib import Path

ROOT = Path.cwd()
local = {p.name for p in ROOT.iterdir() if p.is_dir()}


def targets(path):
    for n in ast.walk(ast.parse(path.read_text())):
        if isinstance(n, ast.Import):
            yield from (a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom) and not n.level and n.module:
            yield n.module
            # `from finmind_data import adjust` names the submodule in `names`,
            # so following n.module alone stops at the package directory and
            # misses everything that module imports in turn.
            yield from (f"{n.module}.{a.name}" for a in n.names)


seen, queue, need = set(), [Path(a) for a in sys.argv[1:]], set()
while queue:
    f = queue.pop()
    if f in seen or not f.is_file():
        continue
    seen.add(f)
    for m in targets(f):
        top = m.split(".")[0]
        if top in local:
            queue.append(ROOT / (m.replace(".", "/") + ".py"))
        elif top not in sys.stdlib_module_names:
            need.add(top)

absent = []
for m in sorted(need):
    try:
        if importlib.util.find_spec(m) is None:
            absent.append(m)
    except (ImportError, ValueError):     # a namespace parent that will not load
        absent.append(m)
if absent:
    print(f"  interpreter: {sys.executable}")
    print(f"  reached:     {len(seen)} modules from {len(sys.argv) - 1} packages")
    for m in absent:
        print(f"  missing:     {m}")
EOF
)
if [ -n "$preflight" ]; then
  echo "FAIL  the interpreter on PATH cannot import what the assertions need," >&2
  echo "      so some checks would error out while the rest reported a pass:" >&2
  echo "$preflight" >&2
  echo "      activate the project env — e.g. source /home/st/miniconda3/bin/activate" >&2
  exit 1
fi

failed=()
for f in "${files[@]}"; do
  pkg=$(dirname "$f")
  echo "── $pkg ──────────────────────────────────────────────"
  python "$f" "$@" || failed+=("$pkg")
  echo
done

if [ ${#failed[@]} -ne 0 ]; then
  echo "FAILED: ${failed[*]}"
  exit 1
fi
echo "all packages passed"
