"""The FinMind API token, read from `.token` at the moment a request needs it.

Every collector here authenticates against the same endpoint with the same
file, so the read is written once. Two properties are what it is written for.

**It happens at the call, not at import.** `.token` is gitignored, so a fresh
clone does not have one — and a module that reads it at import cannot be
imported at all without it, which puts a credential in front of every checker
that wanted one pure function out of the file.

**A missing file raises.** The alternative is an empty token, which does not
skip authentication: the datasets this package downloads are sponsor-tier, so
the vendor answers a blank one with a tier refusal that reads from the caller's
side like a dataset that does not exist.

**It travels in a header.** A token in the query string is part of the URL, and
`requests` writes the URL into the message of the connection error it raises
once its retries run out, and into every `HTTPError`. A collector that logs or
re-raises one of those writes the token with it. FinMind documents the
`Authorization: Bearer` header as the way to send it.
"""
from __future__ import annotations

from pathlib import Path

TOKEN_FILE = Path(__file__).resolve().parent / ".token"


def token() -> str:
    """The API token. Raises if `.token` is absent — it is never optional."""
    if not TOKEN_FILE.exists():
        raise FileNotFoundError(
            f"{TOKEN_FILE} is missing. The FinMind datasets this package reads "
            f"are sponsor-tier, so a request without a token is refused rather "
            f"than served a free-tier subset. Write your token to that file "
            f"(it is gitignored) — see finmind_data/README.md.")
    return TOKEN_FILE.read_text().strip()


def headers() -> dict[str, str]:
    """The request header carrying the token, read at the call like `token`."""
    return {"Authorization": f"Bearer {token()}"}
