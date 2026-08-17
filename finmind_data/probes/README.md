# Probe and verification scripts, session 2026-08-17

The ad-hoc commands behind the delisting-sign work: the endpoint probes that
decided which sources exist, the analyses that produced the numbers `main`
publishes, and the mutation runs that tested whether each assertion catches
anything. Extracted verbatim from the session transcript by
`extract_from_transcript.sh`, which is itself included so the extraction can be
repeated or widened.

**This branch is where they live because `main` is a Minimal Reproducible
Example.** The repo's commit discipline puts exploratory work in a branch or
tag rather than letting it accumulate in `main`, so nothing here is imported by
the package, run by `run_assertions.sh`, or referenced by any documentation on
`main`. Everything on `main` that these scripts produced is already there as a
committed number, an assertion, or a caveat paragraph.

**They are an archive, not a runnable suite.** Paths are the session's own,
including a scratchpad directory that no longer exists; several are deliberate
mutations that edit a tracked file and restore it afterwards; and the API
probes read `finmind_data/.token`, which is gitignored and absent here. Read
them to see what was asked and how; re-run one only after reading it.

`manifest.tsv` lists every script with its transcript call number and what it
did. The four directories:

## `exchange/` — is the delisting reason published anywhere cheaper?

Sixteen probes against TWSE's 終止上市公司 table and TPEx's 終止櫃檯買賣 list,
including the several that failed to find an endpoint at all. The failures are
the point: they are the evidence that no cheaper source than a per-company MOPS
filing exists, which is the claim the caveat rests on. The conclusion — TWSE's
table carries date, name and code and nothing else; TPEx filters by reason but
reaches back only to 2021, which is 7 of the 173 — is in caveat 8 as "Both
probed 2026-08-17".

## `finmind_api/` — what the vendor tier actually serves

Sixteen probes of the FinMind endpoints: which datasets the sponsor tier
unlocks, what date range the adjusted series covers, whether it is a price or
total-return convention, how it behaves at no-trade rows and unpriced capital
reductions, and whether a per-date bulk sweep reaches names the per-stock files
miss. Results are in the endpoint-mapping table and the adjusted-price caveats.

## `delisting/` — the analyses behind the published numbers

Where the 0.50 cut came from, the successor-identification attempt that was
dropped after matching 98 of 99 payouts to unrelated IPOs, the gap-versus-
residual work that ruled out the staleness account, the settlement-gap
distribution over the payout-shaped names, and the deal-form cross-tabulation
that produced 9 of 9 at p=0.175.

Two of these matter more than the rest, because both are negative results that
someone would otherwise pay to rediscover: `641.sh` is why successors are not
identified from prices, and `707.sh` is where the acquirer turned out not to
have been trading at all — it fails with an `IndexError` on an empty slice, and
that empty slice *is* the finding.

## `mutation/` — does each assertion catch anything?

Each run edits a committed file, checks that the intended assertion fails with
the intended message, and restores. Pre-registered cuts moved, gate parameters
moved, the label file emptied, a consideration booked at the wrong price, a
band membership swapped at constant count. `756.sh` and `757.sh` are the same
mutations before and after an ordering fix: in `756` the count assertion fired
ahead of the live test and reported column totals for an event that was not
about counts.
