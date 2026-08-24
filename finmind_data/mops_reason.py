"""Read why each in-window common left the exchange, out of its MOPS subjects.

README caveat 8 says the reason a Taiwanese common delisted is published per
company in a 公開資訊觀測站 filing and in no table, and that until those filings
are pulled a delisting return computed from this package is an assumption
wearing a number. `mops_filings.py` pulls them. This module reads them.

What it reads is the 主旨. The 說明 behind it would say more, but the host
serves it only for a company that is still a 公開發行公司, which 14 of the 164
are (`mops_detail_refusals.csv`), so a reason derived from 說明 would exist for
a ninth of the frame. The subject line is what exists for all of it.

The rule below was written against the 116 names that carry no hand label and
scored afterwards against the 68 that do (`delisting_labels.csv`). That order is
the point: a rule tuned on the labels it is then scored against reports its own
fitting error as an accuracy. The score belongs in the README beside the rule,
not in this docstring, because the rule can be re-run and the score re-earned.

Where the filings do not say, this returns `unknown` rather than the likelier of
two guesses. A frame that marks its silences can be joined against; one that
fills them cannot be told from one that knew.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
FRAME = ROOT / "delisting_sign.parquet"
LISTING_DIR = ROOT / "mops_listing"
OUT = ROOT / "mops_reason.parquet"

# How far ahead of the exit a filing is still about the exit. A merger is
# resolved by the board, approved by shareholders and completed months later,
# and the board resolution is the filing that names the counterparty; 18 months
# is what covers that chain in the design set, where the earliest anchor sits
# 245 days out. Anchors are dated against this and the widest observed one is
# reported, so a name that lands on the edge is visible rather than silently cut.
WINDOW_BEFORE_DAYS = 540
WINDOW_AFTER_DAYS = 30

# The filing that announces the exit itself. 停止買賣 alone is a suspension and
# not always terminal, but it is the only notice some names get, so it anchors
# when nothing stronger is present.
DELISTING_SUBJECT = r"終止上市|終止.{0,3}櫃檯|終止.{0,3}買賣|停止買賣|終止在櫃檯"

# A company's *bonds* delist too, and their notices read almost identically to
# the stock's. Without this, 5346 anchors on a convertible bond that matured 930
# days before the stock left.
NOT_THE_STOCK = r"公司債|轉換公司債|債券|受益證券|認購權證|存託憑證"

# A filing filed *for* someone else. 代子公司 announcements are the subsidiary's
# news and say nothing about why the parent left the exchange; 代收購人 is the
# acquirer announcing a tender for this company's own shares and is the strongest
# merger evidence there is, so the two are separated rather than dropped together.
SUBSIDIARY_PROXY = r"代子公司|代重要子公司|代轉投資|本公司之子公司|代持股"

# The exit was a corporate action that paid the holder something: an absorbing
# merger, a share swap into a holding company, a tender offer, a going-private.
#
# 合併 is specified positively rather than by exclusion because in Taiwanese
# accounting it means *consolidated*, not *merged* — 合併負債, 合併現金流量表,
# 合併及個體財務報告, 合併自結獲利 are routine quarterly disclosures. Matching the
# bare word and subtracting the accounting phrases one at a time leaves whichever
# phrase was not thought of: on the 116 names that carry no hand label, that
# error marked 24 subjects across 12 companies. So 合併 counts only where a
# merger-specific word follows it or a counterparty precedes it.
MERGER = (r"合併(?:案|契約|基準日|解散|消滅|存續|新設)|"
          r"(?:與|向|由|經)[^，。\s]{2,24}合併|吸收合併|簡易合併|"
          r"股份轉換|股份交換|"
          r"公開收購|承諾收購|收購.{0,8}(?:股權|股份|本公司)|"
          r"存續公司|消滅公司|私有化|概括讓與|概括承受")

# The exit was the exchange removing a company that had failed a listing
# condition. Specified positively for the same reason: 淨值 alone is the routine
# 每股淨值 disclosure and 逾期 alone is the routine 逾期應收帳款 ageing table,
# both of which every watch-listed company files monthly. 解散 is left out
# entirely — a merger dissolves the absorbed company too, so it does not separate
# the two. 營業細則第五十三條之十七 is the TWSE provision under which a suspended
# company is delisted outright, and names the mechanism where the subject line
# otherwise gives only a date.
DISTRESS = (r"未能依|未依.{0,6}期限|"
            r"淨值(?:為負|轉負|低於|不足|已為負)|每股淨值.{0,4}低於|"
            r"重整|破產|聲請清算|"
            r"退票|存款不足|"
            r"全額交割|變更交易方法|"
            r"五十三條之十七|53條之17|"
            r"接獲.{0,12}通知.{0,10}停止買賣|"
            r"財務困難|無法.{0,6}償還|支付命令|假扣押")

REASONS = ("merger", "distress", "unknown")


def _roc_to_ts(s: str) -> pd.Timestamp:
    """MOPS dates are ROC `YYY/MM/DD`; ROC 1 is 1912."""
    m = re.match(r"(\d{2,3})/(\d{1,2})/(\d{1,2})", str(s or ""))
    if not m:
        return pd.NaT
    y, mo, d = (int(x) for x in m.groups())
    return pd.Timestamp(y + 1911, mo, d)


def _subjects(stock_id: str, delist: pd.Timestamp) -> pd.DataFrame:
    """This company's announcements, dated relative to its exit and windowed."""
    path = LISTING_DIR / f"{stock_id}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} — run `mops_filings.py listings` first")
    d = pd.read_parquet(path)
    if not len(d):
        return d.assign(dt=pd.NaT, rel=pd.NA)
    d = d.assign(dt=d.spoke_date.map(_roc_to_ts))
    d = d.assign(rel=(d.dt - delist).dt.days)
    return d[(d.rel >= -WINDOW_BEFORE_DAYS) & (d.rel <= WINDOW_AFTER_DAYS)]


def read_one(stock_id: str, delist: pd.Timestamp) -> dict:
    """The reason one company left, and the filing that says so."""
    w = _subjects(stock_id, delist)
    subj = w.subject.fillna("")
    is_stock = ~subj.str.contains(NOT_THE_STOCK, regex=True, na=False)
    anchors = w[subj.str.contains(DELISTING_SUBJECT, regex=True, na=False) & is_stock]

    anchor_subject, anchor_rel = "", pd.NA
    if len(anchors):
        a = anchors.iloc[anchors.rel.abs().values.argmin()]
        anchor_subject, anchor_rel = a.subject, int(a.rel)

    # The anchor decides when it names a mechanism: it is the filing about this
    # exit, so what it says outranks anything counted over the window.
    # A subsidiary's news is excluded from both counts; the acquirer's notice
    # about this company's own shares is not a subsidiary's news.
    own = is_stock & ~subj.str.contains(SUBSIDIARY_PROXY, regex=True, na=False)
    n_mer = int(subj[own].str.contains(MERGER, regex=True, na=False).sum())
    n_dis = int(subj[own].str.contains(DISTRESS, regex=True, na=False).sum())
    a_mer = bool(re.search(MERGER, anchor_subject or ""))
    a_dis = bool(re.search(DISTRESS, anchor_subject or ""))

    if a_mer and not a_dis:
        reason, basis = "merger", "anchor"
    elif a_dis and not a_mer:
        reason, basis = "distress", "anchor"
    elif n_mer > n_dis:
        reason, basis = "merger", "window"
    elif n_dis > n_mer:
        reason, basis = "distress", "window"
    else:
        reason, basis = "unknown", "silent"

    return {"stock_id": stock_id, "reason": reason, "basis": basis,
            "anchor_rel_days": anchor_rel, "anchor_subject": anchor_subject,
            "n_merger_subjects": n_mer, "n_distress_subjects": n_dis,
            "n_subjects_in_window": int(len(w))}


def build() -> pd.DataFrame:
    f = pd.read_parquet(FRAME)
    rows = [read_one(r.stock_id, pd.Timestamp(r.delist_date))
            for r in f.itertuples()]
    out = f[["stock_id", "stock_name", "delist_date", "sign"]].merge(
        pd.DataFrame(rows), on="stock_id", how="left", validate="1:1")
    out = out.rename(columns={"sign": "price_shape_sign"})
    if out.reason.isna().any():
        raise AssertionError("a name in the frame got no reason row")
    return out


def main() -> None:
    out = build()
    out.to_parquet(OUT, index=False)
    print(f"{len(out)} names -> {OUT.name}")
    print(out.reason.value_counts().to_string())
    print()
    print("basis:")
    print(out.basis.value_counts().to_string())
    anch = out.anchor_rel_days.dropna()
    print(f"\nanchor found for {len(anch)}/{len(out)}; "
          f"earliest {int(anch.min())}d, latest {int(anch.max())}d from exit")


if __name__ == "__main__":
    main()
