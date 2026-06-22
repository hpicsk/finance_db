"""Shared classification logic for delisting reasons."""

TRANSFER_REASONS = {"코스닥시장 이전상장", "유가증권시장 상장", "코스닥시장 상장"}
MERGER_SUBSTRINGS = ("피흡수합병", "완전자회사화", "완전자회사로 편입",
                     "스팩소멸합병", "주식교환")


def classify(reason: str) -> str:
    """Classify a delisting reason as genuine (Y) or non-genuine (N)."""
    if reason in TRANSFER_REASONS:
        return "N"
    if any(k in reason for k in MERGER_SUBSTRINGS):
        return "N"
    return "Y"
