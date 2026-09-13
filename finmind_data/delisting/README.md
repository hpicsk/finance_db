# The delisting study: what each exit paid

`data/delisted_universe.parquet` says that a name left a board and when. It does
not say why, and the two whys have opposite signs. This subpackage reads the
reason off the tape and the filings, registers the rules before the labels,
and books a terminal value with its basis named. It is CAVEATS.md 8, kept
here whole.

| file | what it is |
|---|---|
| `delisting/delisting_sign.py` | last close against the prior-year high; the pre-registered cuts, the label draw, the held-out band, `terminal_value` |
| `delisting/mops_reason.py` | the reason read off each name's MOPS subject lines |
| `delisting/swap_ratios.py` | a swap's exchange ratio read off the acquirer's filing |
| `delisting/tender_offers.py` | what every filed 公開收購 paid, from the exchange's own summary table |
| `../collect/mops_filings.py` | the MOPS collector the study reads from |
| `../data/delisting_sign.parquet` | each exit as failure / payout / undecided |
| `../data/delisting_labels.csv`, `delisting_band.csv`, `delisting_consideration.csv` | the hand-read labels, the held-out band with its committed calls, the deal terms |
| `../data/mops_reason.parquet`, `tender_offers.parquet`, `mops_*_refusals.csv` | the reason frame, the offer table, the names MOPS will not serve |
| `../data/mops_listing/`, `mops_detail/`, `mops_acquirer_*/` | the filings, one file per name |

    python -m finmind_data.delisting.delisting_sign
    python -m finmind_data.collect.mops_filings listings
    python -m finmind_data.delisting.mops_reason
    python -m finmind_data.delisting.tender_offers
    python -m finmind_data.delisting.swap_ratios

## The caveat, whole

**No delisting reason, and no terminal value.** `delisted_universe.parquet`
carries `date`, `stock_id`, `stock_name` and a derived `year` — that is the
whole of `TaiwanStockDelisting`. Nothing separates a bankruptcy from a
merger, a voluntary buyout or a move to another venue, and no field records
what a holder received when trading stopped. Treating the last observed
price as the terminal value therefore books −100 % where a merger paid a
premium, and a premium where the shell was worthless; which error you make
is decided by the reason the table omits. This is delisting-return bias, and
it is **not** the survivorship bias the universe overlay fixes — a panel can
hold every delisted name and still misprice each one's final return. The
reasons live in 公開資訊觀測站 (`mops.twse.com.tw`) filings, which no FinMind
endpoint mirrors. Those filings are pulled — `collect/mops_filings.py`, and the block
at the end of this caveat says how far they reach — and they settle the
*reason* for 146 of the 164. They do not settle the *amount*: 說明 is served
only for a company still registered as 公開發行, which 14 are, so what a
holder received is still read one filing at a time and a delisting return
that substitutes the last close is still an assumption wearing a number.

**The 164 here are not the 179 above.** This caveat's frame is the
delistings inside 2011-01-25..2024-12-31, frozen on its own dates when its
sample was pre-registered (`delisting/delisting_sign.py`, `_WIN_START.._WIN_END`), so
the 15 that delisted after 2024-12-31 are in the universe and in every
survivorship check but have no reason, label or terminal value read here.
Letting the frame follow coverage would have redrawn a seeded sample whose
labels were already collected;
`test_taiwan_delisting_frame_does_not_follow_coverage` moves `COVERAGE_END`
two years and requires the same 164 names back.

The obvious cheaper source is empty, and it is worth saying so because it is
the first place anyone looks. TWSE's own 終止上市公司 table
(`www.twse.com.tw/rwd/zh/company/suspendListingCsvAndHtml?type=csv`) returns
264 rows over 2001-2026 under exactly three headers — 終止上市日期, 公司名稱,
上市編號 — which is date, name and code, the same three fields
`TaiwanStockDelisting` already carries. Joining it adds nothing. TPEx's
終止櫃檯買賣 list does filter by reason, but reaches back only to 2021 — 46
of the 164 in-window exits, and only the TPEx names among them. Both probed
2026-08-17. The reason is published per company
in a filing, never in a table, and that is what makes it expensive.

The 1,134 post-delisting sessions are the one piece of direct evidence
the package does hold against this. Four delisted names — 1107, 2341, 2381
and 2396 — go on being quoted for 367 to 1,151 sessions after leaving the
exchange, 67 to 415 of them inside the window, and where each converges over
that stretch is a market observation of what the shell was worth, which the
last exchange close is not. It is also a weak signal on the reason, since a
name that left by merger does not go to 興櫃 at all. Four quoted tails is a
sample, not a fix; MOPS is where the fix came from, and
the part of it still owed is the consideration, not the sign.

All four delisted between 2007 and 2010, so the exit itself sits before the
window even though the quotes reach into it — which is also why the vendor
serves no adjusted row for them and the rebuild has to. They are evidence
about the mechanism — that a shell goes on being priced, and where it
settles — and not a check on any name in the frame below.

None of the four invites the opposite reading. Post-delisting median volume
runs at 3.0 % to 49 % of each name's own listed-era median, which is what a
negotiated market looks like rather than a demotion to another board, and
all four stop for good by 2012-11. No ticker in the table outlives the
panel: the 2026-08-17 refresh retracted the one board transfer the table
used to carry and both reused codes, which is why the assertion over this
now reads two empty lists rather than three names.

The reason the table omits is partly legible in the price path, and
`delisting/delisting_sign.py` reads it there. An acquisition is announced, jumps to a
premium and converges flat to the consideration, stopping at its own high; a
failure collapses. On the ratio of the last traded close to the highest
close of the preceding year, **29 of the 164 market exits are
failure-shaped, 98 payout-shaped, and 37 sit between the two cuts**.
Balance-sheet equity would be the obvious second opinion and is available
for all but nine: the vendor's statement history starts 2012-03-31, and nine
of the 164 delisted before it.

The two cuts were fixed before a single reason was looked up, which is the
only thing that makes an accuracy measured against them worth reading, and
`delisting_labels.csv` plus the assertion over it keep that true — the draw
is a function of the cuts, so a cut edited after the labels arrive changes
which names were sampled and fails the suite. 41 names in the frame carry a
label read off exchange announcements and contemporary reporting: 33 drawn
stratified across the cuts and the eras, 8 more that carried no
corroborating feature and were resolved by hand rather than classified. The
file holds 27 further labels marked `prior` — names bought against the frame
the package answered about before 2026-08-17, kept as the record of what was
read and excluded from every rate below, since they were not drawn from the
population those rates are about.

Scored on the names the cuts actually decide, the shape is right on **98.7 %
of the 126** carrying a verdict. That is an estimate from 15 labelled
verdicts weighted up by stratum, not 126 verified ones, and it turns on a
single miss: **1613 台一** stopped 25 % below its peak, which reads as an
acquisition, and was in fact thrown off the exchange for failing to file its
China subsidiary's accounts. A failure that never panicked the tape is the
error this method makes, and forced delistings for non-filing are where to
expect it.

A single cut inside the band was registered on the frame the package
answered about before the refresh, on the reading that the truth turns over
near a drawdown of 0.50. On the corrected frame that reading has weakened
and the alternative registered beside it has overtaken it. Of the 28
labelled names between the cuts, 8 of the 13 below 0.50 are failures and 12
of the 15 above are payouts — 20 right out of 28 — while the free rule that
reads the halt instead of the price is right 25 times on the same 28. The
price path is not doing the work the registered cut assumed, and registering
the alternative at the same time is what made that visible rather than
arguable.

`delisting_band.csv` records what 0.50 calls each of the **9 band names that
were never looked up**, committed while all 9 were blank, along with the
pass mark and the halt rule it has to beat. The 9 are the entire test set —
the band does not grow — and their labels come free with any consideration
pulled, since an announcement names its own reason. But the gate can no
longer be read on them: the smallest sample at which anything short of a
perfect score clears the base rate is 11, and 9 names are held out, so the
threshold is undefined however many of the 9 get labelled. The 8420
correction is what took that minimum from 10 to 11 — it raised the band's
majority class from 16 payouts in 28 to 17, so the free reading a rule has
to beat went from 0.571 to 0.607 and the gate moved further out of reach. That is reported
rather than repaired. Lowering the bar to fit nine names is the move the
registration exists to stop, and the way back is a larger held-out set.
Until then the cuts leave the band undecided at 37 names, ~24 of them
payouts.

**Two of the 9 now carry a label, and they arrived the way this paragraph
said they would.** 3561 昇陽光電 and 6298 崴強 were each one target of a
three-way transaction whose *other* targets were being looked up for a
ratio, so the filings named their reason — both 合併 — without either name
being sought; the sentences are in `delisting_band.csv` beside them. Nothing
about the registration moves: the calls were committed while all 9 were
blank, and a label arriving afterwards is what a held-out set is for. The
gate stays unreadable for the arithmetic reason above and not for this one.
What does move is the settlement — a name whose filing has been read no
longer books NaN — so `terminal_value` reads both label files while
`band_holdout` is shown only the drawn sample, and filling a band label
therefore cannot shrink the set the rules were registered against.

The one candidate feature that could have decided the 9 was priced and
declined, and the pricing was done on the 28 so that it could not be done
on the 9. `TaiwanStockDispositionSecuritiesPeriod` — 處置有價證券, the only
full-window distress-shaped table in the catalogue — is the obvious thing to
reach for when a rule needs a source that is not a filing. It marks abnormal
*trading*: five consecutive sessions on 注意交易資訊 put a name into manual
matching and full prepayment, which an acquisition run-up can trigger as
readily as a collapse. Measured against the frame it reaches 40 of the 164
exits and 8 of the 37 band names in the 12 months before the last trade —
24 % and 22 % — and on the 9 held out it would flag 2. On the 28 labelled
band names it points the wrong way: 6 carry a disposition, 4 of them
payouts, and reading a disposition as distress is right 15 times out of 28,
below the 17 a reader gets by calling every band name a payout and never
looking. Probed 2026-08-25; the table is not stored, which is why those
figures carry a probe date and not an assertion.

None of that is the reason it was declined, though — it is the confirmation.
The binding constraint is the label count and not the feature set: 11 labels
are needed and 9 exist, so a rule registered on this frame returns
"unreadable" whatever it reads, and a feature flagging 2 of 9 cannot change
an arithmetic that does not mention it. Registering it after that was known
would have been registering a rule that cannot fail, which is the same move
as lowering the bar and costs the 9 labels either way.

The payout's **size** is a separate gap, and smaller than it looked. A name
classified as one books its last traded close, and against the 23 deals
whose consideration is now recorded, that substitute is wrong by two very
different amounts depending on how the deal paid. Cash lands it within
**1.5 %** every time — a median **+0.68 %** across twelve deals, +0.09 % to
+1.34 % — so those names never need a filing pulled at all. A share swap
misses it by anything from **−13.9 % to +24.8 %**, median **+9.9 %** across
eleven. The split is the usable part and it decides which lookups are worth
doing. Two of the original six delisted before the window starts and left
the frame with it; they stay in `delisting_consideration.csv` as the record
of what was read.

**The swap side used to be n=2 and one-directional, and growing it retired
the direction.** The cash side was grown twice and held both times: three
going-private tenders came out of the exchange's own summary table (below),
taking it from n=2 to n=5 and the worst residual from under 1 % to +1.34 %,
and four more were transcribed from `delisting_labels.csv`, whose `source`
already carried a per-share cash price read at labelling. The swap side
could not be grown the same way, because a dozen swap labels state a ratio
in conventions that disagree row to row — `0.3562:1`, `1:1.68`, `3.15:1`, a
bare `1.39` — and picking a direction without the filing means taking
whichever reading puts the implied consideration near the last close, which
is the quantity being measured.

So the filings were opened, and the route is worth stating because it is not
the target's. `delisting/swap_ratios.py` reads the ratio off the **acquirer's**
announcement: MOPS gates the 說明 on a company's *current* registration, so
a target that deregistered on the way out is served subject lines and
nothing else, while the buyer is still 公開發行 and files the same
transaction in a sentence that fixes which side is which — 「調整為每3.1560股
雷凌科技普通股股票換發1股本公司增資普通股股票」. Seven of the eleven in-frame swaps
are read there, and 5854 合庫 from its own filing, since a bank converting
into a holding company keeps its registration. Each of those eight rows
quotes the sentence in 「」, and the quote is asserted back against the
cached body of a filing dated as the row says — a `per_share` whose citation
stops resolving is a number with a source that no longer exists, which is
what the labels' bare ratios already were. The remaining three carry no
quote: 5491 and 4733 are 1:1, which reads the same either way, and 3698's
0.275 into Ennostar was read at labelling — the one row still resting on the
shortcut, and one of the cases where the shortcut is unambiguous, since the
other reading implies NT$331 against a last close of NT$22.25.

Seven in-frame swaps are still unpriced, and the gate is the same one a
company over. **Five had a buyer that was itself later bought** — four
buyers across those five deals, since 2456 奇力新 bought two of them, the
others being 2448 晶電, 3698 隆達 and 5317 凱美 — and MOPS refuses a
deregistered acquirer in the words it refuses the targets, recorded per
target in `mops_acquirer_refusals.csv`.
**Two went into a holding company that did not exist before the conversion**
(3428 and 6145 into 永崴投控 3712), so there is no earlier filing of its to
read; its first announcements are dated the conversion day and are
housekeeping. Worth recording about the shortcut that was refused: on every
ratio actually read, the direction in the filing is also the only one that
is not absurd — the wrong reading of 3534's 3.156 implies NT$1,065 against a
last close of NT$102.50. The shortcut would have been right where the ratio
is odd and is a coin-flip where it is near 1, which is `0.93:1` and `1.07:1`,
two of the seven still out. It is safe exactly where it is not needed.

**What eleven swaps overturned is the direction.** 4944 兆遠 was paid 0.02 of a
環球晶 6488 share on 2023-11-01, worth NT$9.99 against a last close of
NT$11.60 — **−13.9 %**, the substitute above what was paid rather than below
it. It is not an artefact of the settlement gap: priced on 兆遠's own last
trade date instead, 6488 closed at 476.50 and the residual is −17.8 %. The
name ran 9.62 → 12.75 over its final five sessions on a float that was about
to disappear. One deal is one deal, but the claim it refutes was a claim
about every deal, and the two-swap sample that supported it is exactly the
sample that could not contain this one.

Where the deals sit was itself read as a finding, and the corrected frame
refutes it. On the 18 payouts labelled before the refresh, all 9 whose form
was stated inside the band were share exchanges and no cash deal had ever
been labelled there, which invited the reading that a conversion's discount
is what drags a payout into the band — the mechanism being that a cash offer
at a premium stops near its own high and should land above the upper cut.
The re-registered draw takes the stated forms to **26 labelled payouts, 17
share exchanges and 9 cash**, and four of the nine cash deals sit *inside*
the band: 4965, 8913, 6211 and 8266, at drawdowns of 0.56 to 0.63. The
mechanism is the part that was wrong. Drawdown is measured against the
highest close of the *preceding year*, so a cash offer at a premium to the
recent price is routinely far below the price a year earlier — 商店街市集 was
bought in at NT$44 after falling most of the way there from its own high,
and the offer was a premium while the drawdown was 0.56. On the 16 stated
forms now in the band, 12 exchanges against a base rate of 17 of 26 is what
chance gives **0.234** of the time (Fisher exact, two-sided). What survives
is the narrower point the comparison was good for: seven of the eleven
swaps measured are band names, so the spread is measured mostly on names the cuts
do not decide rather than on classifier-confirmed payouts.

The obvious next move is to let the gap between the last trade and the formal
date price that error, on the reading that the last close goes *stale*: a
swap's value goes on moving with the acquirer while the target no longer
trades, and the gap would then estimate the error on a name whose acquirer
was never identified. That account used to be untestable here, and the
reason it was is the reason it is testable now. On two swaps the successor
first traded on the day the target left — **zero sessions of overlap**, no
acquirer price to drift against — and both were holding-company
conversions, which followed from the selection rather than from anything
about swaps: a 1:1 or a flat share count is what a conversion looks like,
and the third-party acquisitions carrying an odd ratio were precisely the
ones excluded for want of a direction. The settlement calendar is still what
the gap mostly is — **87 % of the 98 payout-shaped names sit at 7-14 days**.

Reading those directions put **six third-party acquisitions** into the
sample, each with an acquirer that had traded for 1,670 to 2,707 sessions
before the target's last trade. The gap now takes six values across the ten
swaps instead of two, and its rank correlation with the residual is
**+0.85** — the sign staleness predicts. Read that as a measurement, not as
a mechanism: it is ten deals, the reading was adopted after the sample was
assembled rather than committed before it, and the same correlation on the
nine cash deals is **−0.70**, which is the sign staleness forbids. What can
be said is that the two forms order against the gap in opposite directions,
which is also what the pooled figure was reporting under the gap's name all
along: it read 0.80 on four deals, 0.51 once three tenders were added, 0.10
once four transcriptions were, and moves again now. Both within-form figures
are asserted; the pooled one is not, because it never measured anything.

What survives is the split, and not a mechanism for either half. Why a swap
lands where it does is open: a liquidity discount on a name whose exit is
already fixed, terms revised between announcement and effect, a squeeze into
a closing float, and the acquirer's own drift over a two-week gap all fit
somewhere in a spread that runs −13.9 % to +24.8 %. Nothing in this package
separates them at n=10, and none is assumed anywhere in the code. Use the
cash figure as a bound worth relying on and the swap figure as a spread
worth disclosing — not as a correction, which would have to know which of
the four it was undoing.

So `terminal_value()` books on four bases, cut so each names a different
piece of work. **`failed`** is `last_close * (1 - failed_haircut)`, which is
zero by default and nothing else without saying so — zero because it is the
only value in the four that needs no source, and a haircut because a study
modelling a liquidation should be able to state one without editing this
file. The last close is not an alternative to it: these 41 names are frozen a
median of 120 sessions before the exit and 20 of them for more than 180, so
the print a haircut scales is months stale and nobody could have sold at it.
Their median last close is NT$2.57 against NT$31.30 among the substituted,
which is how much less the choice moves than its range suggests.
**`consideration`** is what was actually paid, for the 23 recorded, a swap
priced on the panel at the delisting date.
**`substituted`** is the last close standing in for a consideration nobody
has looked up, carrying the bias above, and one filing closes each. It is
the count that falls when a consideration is recorded — and the count that
*rises* when a held-out band name's filing is read, since that name now has
a sign but still no consideration. Those are the only two movements.
**`undecided`** is NaN and is the only NaN — the sign is what the band does
not know, and a number there would be a guess at the direction rather than
at the size. That distinction is what the column is for: the last two are
both missing something, and it is not the same something, so a study that
meets one has to pull a filing while a study that meets the other has to
resolve the band or drop the name. Either way the count falls out of running
the study instead of being estimated ahead of it.

A hand-read filing outranks a price shape wherever one exists, so the
labels settle the sign and the cuts fill the rest. That empties 28 of the 37
band names, leaving the **9** the single cut is registered against — of
which **2** have since had their filings read, so **7** still book NaN —
and it overturns one verdict outside the band: 1613 books zero rather than
its last close. The 98.7 % above is unchanged by this and should be: it is a
fact about the cuts, and booking the value a label already settled does not
make the cuts better. The counts a study meets are **41 `failed`, 23
`consideration`, 93 `substituted`, 7 `undecided`**, and they are asserted
rather than quoted: the previous pair of them was a name apart from what the
code returned, and survived because the four numbers were only ever printed
in a check's message and never compared to anything.

**The filings are pulled, and this is how far they reach.**
`collect/mops_filings.py` collects 公開資訊觀測站 重大訊息 for every one of the 164,
over the delisting ROC year and the two before it — **19,949 announcements**,
the thinnest name carrying 31 and the median 103. Two hosts answer and they
answer differently. `mopsov.twse.com.tw` serves 14 and refuses 150, 144 with
「公開發行公司不繼續公開發行！」and 6 with 「上市公司已下市！」. The 2025 backend
at `mops.twse.com.tw/mops/api` serves the 主旨 for all 164, which is why it is
the host this package uses. Neither serves the 說明 for a company that has
deregistered: the gate is on the company's registration today rather than on
the filing, it does not move with `marketKind`, and it is the same on both
hosts (probed 2026-08-24). So `mops_detail/` holds 2,555 filing bodies for the 14
that stayed 公開發行公司, `mops_detail_refusals.csv` names the 150 that did
not, and the reason for those is read off subject lines. A pull that reported
only the 14 would be reporting the host's registration policy as a coverage
figure.

**What the subjects decide.** `delisting/mops_reason.py` anchors on the filing that
announces the exit — the 終止上市/終止櫃檯買賣 notice nearest the delisting
date, with bond notices excluded, since a company's convertible bond delists
under almost the same sentence and 5346's would otherwise anchor the stock
930 days early. An anchor is found for **134** of the 164, a median 40 days
ahead of the exit and none earlier than 245, so the 540-day window the module
reads is not binding on any name. Where the anchor names a mechanism it
decides; where it does not, the window's subjects are counted; where the two
sides tie, the answer is `unknown` and stays that way. The frame comes out
**112 merger, 34 distress, 18 unknown**.

Both marker sets are specified positively, and neither started that way. In
Taiwanese accounting 合併 means *consolidated*: 合併負債, 合併現金流量表,
合併及個體財務報告 and 合併自結獲利 are routine quarterly filings, and matching
the bare word marked 24 subjects across 12 of the 116 unlabelled names as
merger evidence. 淨值 alone is the monthly 每股淨值 disclosure and 逾期 alone
the 逾期應收帳款 ageing table, both of which a watch-listed company files
whether or not it is failing. Subtracting such phrases one at a time leaves
whichever phrase was not thought of, so 合併 now counts only against a
merger-specific word and 淨值 only against a negative one. 解散 is not a
distress marker at all — a merger dissolves the company it absorbs.

**Against the price shape.** The shape left **37** names undecided; the
filings decide **30** of them, 19 as payouts and 11 as failures, and 7 stay
unknown. On the 127 the shape did decide, the filings agree on 114, are
silent on 11, and overturn **2** — both in the same direction, a payout on
the tape that was a removal in the filings. One is **1613 台一**, the miss
this caveat names, recovered here without its label. The other, **3562
頂晶科技**, stopped trading at its own peak — a drawdown of 1.00 — under 43
in-window notices of 關務署 penalties and 假扣押 seizures. So the error mode
this caveat describes is not one name; it is two in 127, and both are
failures that never panicked the tape.

**The list stood at four, and two of them were this rule.** Until
2026-08-25 a citation to 營業細則第五十三條之十七 counted as distress, on the
reading that the article removes a suspended company. It does not. The
provision governs one transaction and no other — a listed company that swaps
its shares to an unlisted existing company under 企業併購法第34條, becomes its
wholly-owned subsidiary, and delists on the swap's record date. **5305 敦南**
is that swap into Diodes' 台灣達爾科技 and **8497 格威傳媒** is that swap into
台北博報堂投資, the second step after a tender at NT$69 a share that took
25.2m of a 26.9m ceiling and so left the rest to buy; each files its
企業併購法第33條 notice beside the citation. The marker moved to the merger
side, where it decides at the anchor. Nothing in the rule's output could
have shown this — a misread statute returns a verdict, not an error — so the
reading is now bound to the transaction it names, and a citer that files no
swap fails the assertion. The article appears on 2 subjects in the whole
archive and neither name carries a hand label, so the score below is
arithmetically the score it was before the correction.

**The TPEx notice stays out, and the reason is not symmetry.**
證券商營業處所買賣有價證券業務規則 was described here as the notice doing the
same job on the other exchange; it is not the same job. Six companies file
one and every notice suspends trading or changes the trading method, so it
is matched as neither marker. Adopting it would decide **two** of those six
and no more: 3642, 4152 and 8420 write 變更交易方法, which the distress
pattern already matches on its own, and 3431 is decided elsewhere in its
window. The two left are **1333 恩得利**, whose notices only suspend, and
**6497 亞獅康-KY**, whose notice writes 變更交易方**式** — one character off
the phrase the pattern carries. Both are `unknown` today, both carry a hand
label, and adopting the rule name would decide them into the labels those
hand readings already give them: a second recalibration chosen after seeing
what the first one scored, on the very names the score is read against. It
is recorded as a gap rather than closed, and closing it needs labels this
frame has not spent.

**What it does not close.** The reason is not the amount. 說明 is refused for
150 of the 164, so the consideration a holder actually received is still
read one filing at a time. What changed is the sign: the band the single cut
was registered against is no longer the only way to settle 30 of its 37
names.

**One table is not behind that gate, and it settles three of them.**
公開收購申報資料彙總表 is filed by the *offeror* and served by period rather
than by company, so a deregistered target has nothing to gate: 2325 矽品 and
4180 安成藥業 both answer where their own 說明 does not (probed 2026-08-25).
`delisting/tender_offers.py` takes the whole of it in one request — **119 offers** from
ROC 105/11 (2016-11), the floor the query form states, each with the
per-share 收購對價 in words, who was buying, and how much they got.
**Fifteen** were made on a name in this frame.

Three of those fifteen are booked as the consideration, and the rule that
picks them is a date rather than a judgement. Taiwan's going-private order is
to terminate the listing first and buy out whoever is left after, and
公開收購管理辦法 §18 caps an offer at 50 days — so 4762 三汰-KY, 4965 商店街 and
5304 鼎創達 each open their offer *on* the delisting date and close 49 days
later, and nothing later can have been their exit because there was no market
left for it to precede. The column the offeror files,
被收購公司於收購後是否終止上市, does not decide this and is not used: it reads 是
for two of the three and 不適用 for the third on identical facts.

The other twelve stay out, and eight of them are the reason the amount is
still open. Those were the first step of a two-step deal — a tender, then a
股份轉換 or 合併 that ended the listing between 99 and 648 days later — and
what a holder who did *not* tender received is the squeeze-out's price, which
this table does not carry. Their tender prices sit from **−5.8 %** (3144
新揚科) to **+11.1 %** (5820 日盛金) against the last close. The remaining four
are offers the table itself says did not end the listing: 2823 中壽 was
tendered twice, at NT$35 and NT$23.6, and left by a 股份轉換 four years after
the first.

**Booking the tender price for those eight was considered and declined, and
the reason is not the size of the spread.** A tender price is what the
holders who tendered received; the ones who did not were squeezed out at the
second step's terms, and 5820 is the case that makes the distinction
concrete — 2.03bn shares came in against a 3.77bn ceiling, so a large
minority went to the merger. No assumption turns the first price into the
second. That reason is one of kind, so it holds whatever the spread turns
out to be, which matters because the spread has since been measured against
the wrong yardstick: the eight sit at a median |error| of **3.2 %**, between
the cash deals' 0.68 % and the swaps' 9.9 %, not outside the range being
measured as this paragraph used to say.

Where they *do* differ from the swaps is in shape, and that is the finding.
The gap between the offer closing and the exit orders the eight residuals at
**ρ = +0.86 in absolute value and +0.36 signed** — the last close gets
noisier the longer the second step takes and does not drift one way, where
the swap side's gap orders the *signed* error at +0.85. A two-step target
keeps trading after the offer's terms are public, so its last close is a
post-announcement price and the market has already done the arithmetic; a
swap's last close is a pre-announcement one. Replacing an unbiased wide
substitute with a narrow one belonging to a different holder is the trade
that was declined.

**The exclusion is five names, not eight, and the three have since been
read.** The second step is a 合併 or 股份轉換 that the *buyer* files, and
three of the eight were bought by a company whose filings are still served —
6422 by 國巨 2327, 4725 by 台泥 1101, and 5820 日盛金 by 富邦金 2881, the
largest residual of the eight. Those three are the same defined lookup
`delisting/swap_ratios.py` performs for a ratio, pointed at a buyer who paid cash, and
they are now in `delisting_consideration.csv`:

| target | tender | second step | last close |
|---|---|---|---|
| 6422 君耀-KY | NT$73 | NT$73 「與公開收購對價一致」 | 72.70 |
| 4725 信昌化 | NT$18 | NT$18 「予信昌化公司其餘股東」 | 17.90 |
| 5820 日盛金 | NT$13 | **NT$11.71** after two dividend adjustments | 11.70 |

**That is the reason of kind, measured.** Two of the three second steps
restate the tender exactly — and 4725's filing names the recipients as
其餘股東, the holders who did not tender, so the equality is stated rather
than inferred. The third does not: 2881 cut NT$13 to 12.41 for 日盛金's 109
dividend and to 11.71 for its 110 one, and the exit is **9.9 % below the
offer**. So booking the tender price would have been exact twice and 11.0 %
high once, against a last close that is within **0.6 % all three times** —
the substitute the paragraph above declined to replace beats the one it
declined to adopt, on the only three deals where both can be scored. One
case is one case; what it establishes is that the distinction was real and
not bookkeeping, which is what a reason of kind is asked for.

The other five were bought by unlisted or foreign vehicles — a Cayman
company, a Japanese one, three private holdcos — which file nothing on
公開資訊觀測站 and are the standing part of the gap. Their tender prices stay
out for the reason above, now with a measured rate behind it rather than an
argument alone.

Where the two sources meet they agree. 4965's hand label already read
「PChome bought in minorities at NT$44/share」 and the exchange's table says
每股新台幣 44 元 — the same number from a filing read by hand and from a
summary filed by the buyer. The other two are new: 4762's label recorded the
tender and not its price, and 5304 carries no label at all.

One label did not survive the filings, and is corrected here.
`delisting_labels.csv` read 8420 明揚 as "suspended 6 months, compulsory
termination". Its filings record the opposite: a one-day halt on 113/04/15
for a press conference, trading resumed the next session, and on that same
day two board resolutions — a 股份轉換 with 明安國際, and a 終止上櫃及停止公開
發行 case put to the shareholders' meeting. The swap's base date moved twice
and settled on 113/11/29; TPEx approved termination on exactly that date and
金管會 the end of 公開發行 on it too. The frame's own `suspension_days` for
the name is 9, not six months, a contradiction internal to the sheet and
readable without any filing. The label is now `merger`. `form` stays blank:
no subject states what 明安 paid, and 股份轉換 permits shares, cash or other
property alike, so reading a form in would invent the fact that column
exists to count. The correction leaves the 98.7 %, its miss list and the
verdict count untouched, since a band name carries no verdict to score. It
moves three other things, and all three in the same direction: the band's
payout estimate from ~22 to ~24, the free reading a rule inside the band has
to beat from 0.571 to 0.607, and with it the smallest readable held-out
sample from 10 names to 11 — against the 9 that exist. A label correction
that made the registered gate easier would be worth distrusting; this one
put it further out of reach.

**What the subject rule scores, and why that is not an independent number.**
On the 42 names carrying both a hand label and a decided reason, the rule
now agrees with all 42. It is worth exactly what its provenance allows: the
rule parted from the labels on 8420, that parting is what sent the filings
to be read, and the label rather than the rule was the side that moved. The
number with provenance is **41 of 42 against the sheet as drawn**, followed
by a corrected sheet that no longer disagrees — not a rule that scores
perfectly. The other 41 were agreed before anyone went looking.

**What 42 leaves out, and the part of it that closes without labels.** The
42 are 42 of 164; 116 names carry no hand label, and the statute misreading
corrected on 2026-08-25 moved two of them, so the score read 42/42 before
the rule changed and 42/42 after. Coverage is not even across the rule's own
machinery either. The window vote decides 129 names and 39 of those are
labelled; the anchor override decides 17, outranks the window wherever it
fires, and 3 are. The strongest move is the least witnessed one, and since
labelling is the scarce input the gap is registered here rather than closed:
the names worth reading first are the 14 anchor decisions nobody has, not
the next 14 in ticker order.

One part of it needs no labels at all. Where an anchor decides against the
window it sits in, one of the two readings is wrong whether or not anyone
has read the name. None does as the frame stands; with 53-17 read as
distress exactly two did, and they were 5305 and 8497 — the pair the label
score could not see. `test_taiwan_anchor_overrides_agree_with_their_own_window`
asserts the empty set and that counterfactual together, so the empty half
stays evidence rather than the shape of a check that passes by looking at
nothing.

**The 18 silent names are not a pattern gap.** Every one carries filings —
18 to 191 in its window — so the rule read them and matched nothing. Two
words those filings do use invite closing the gap, and both fail on
measurement. 繼續經營, the auditor's going-concern paragraph, sits in 13 of
the 164 windows and splits 8 distress to 3 merger among the names already
decided: a company can be doubted as a going concern and then be bought, so
adopting it would decide two names on 73 % precision, which is the likelier
of two guesses this rule declines to make. 保留意見 fails in a way its own
hit rate hides. Adopted as a reader would write it, it moves three names and
one of them — 3536 誠創 — lands on its own hand label, so the sheet
certifies it. The match is on 無保留意見, an *un*qualified opinion, which is
the auditor saying the accounts are clean; requiring the negation to be
absent drops 3536 back out. The label was right about the company and had no
way to be wrong about the rule, which is the blind spot the paragraph above
describes arriving from the other direction.
`test_taiwan_silent_names_keep_their_unknown` holds both measurements.

**1469 理隆纖維 is silent for a different reason, and it is a gap in the
taxonomy rather than in the rule.** Its board approved 申請有價證券終止上市及
撤銷公開發行 148 days before the exit, its shareholders 58 days out, and the
exchange ratified it at 21 — while the company was declaring dividends and
holding investor conferences. That is a voluntary delisting by a solvent
company, and `unknown` is right for it on grounds the other 17 do not share:
the filings said plainly what happened, and the merger/distress pair has no
slot to put it in. So a study joining on `reason == "unknown"` is mixing
"the filings did not say" with "an exit this frame does not model", and the
two have nothing in common in the return they imply.

## Frozen baseline

The delisting-reason frame is frozen here, and downstream work is built against
this state rather than against whatever `delisting/mops_reason.py` returns next. What
`test_taiwan_reason_frame_is_frozen` pins:

- **164 names, 2011-05-02 to 2024-11-29** — 112 merger, 34 distress, 18 unknown.
- **Decided 129 by window vote, 17 by anchor, 18 silent.** The 18 silent are
  exactly the 18 unknown; the anchor path decides 15 mergers and 2 distress.
- **68 hand labels = 42 scored + 6 the rule declines + 20 pre-window.** The
  published score is **42/42**, over the names the rule commits on.

The last line is the one worth reading twice, because the obvious join gets it
wrong. Scoring all 68 labels against the frame returns 42/68: 20 of them
delisted before the frame opens and never had a frame name to match, and 6 more
name a company the rule returns `unknown` for, which is an abstention rather
than a miss. Both denominators are asserted, so the sheet and the frame cannot
drift apart without failing.

Which half of that needed pinning was measured, not assumed. Moving three names
from merger to distress already fails a check — a reason that contradicts its
price shape is a new overturn — so the `reason` margin was covered from the
side. Re-basing three names from window vote to anchor, leaving `reason` alone,
failed **nothing** before this check existed: no other assertion reads `basis`.
That is the column worth guarding, because it is what says how much of the frame
rests on the anchor path, and CAVEATS.md 8 is about how little witnesses that path.
