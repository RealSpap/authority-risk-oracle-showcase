"""Hold, before a push, every score a person should look at first. Read-only; it never changes a score.

ADDED 2026-10-04 after a depth review: no push script had a drop or degradation guard, so a scorer that fell into its
"unresolved, conservative score" branch was published like any other result. Found live: the Plasma Ethena USDe OFT moved
to a TimelockController on 2026-09-29, its scorer read the Timelock as an unresolvable Safe, and the next push would have
published composite 14 against 52 (the right value was 57), an improved posture shown as a 38-point drop.

An entry is HELD when:
- its scorer took a degraded / unresolved branch (a marker in its notes, or the 20/20/0 floor) AND its composite differs
  from the published one (a known, unchanged degraded score is not news), or the published one could not be read; or
- its composite drops by more than MAX_DROP points from the published one; or
- its oracleAuthorityScore (not part of the composite) drops by more than MAX_DROP points, moves while its notes say a
  material price path was UNREAD or the price walk failed (price_authority's markers), or rises to 100 from a lower
  published value (a path that stopped counting is how a walk fails open). Added 2026-10-04 with the price-consumer rule:
  the first push under that rule moves several targets from 100 to 52 on purpose, and a person accepts those once.

In a dry run the report is printed only. Before a real send, the published scores are read from the oracle itself and the
push is refused while any entry is held, unless that entry's address is passed in `--accept-held=0xA,0xB` after a person
looked at it. A failed read of the published scores refuses the push too (`--skip-published-check` overrides it, by hand).
"""
import re
import sys

from web3 import Web3

MAX_DROP = 15
ORACLE_UNREAD = re.compile(r"material price path\(s\) UNREAD|price walk failed")  # price_authority.UNREAD_MARK, FAILED_MARK (a test pins both)
DEGRADED = re.compile(r"degraded|unresolved authority|treat as unresolved|treat as unverified|conservative score|"
                      r"not resolvable|did not (?:fully )?resolve", re.I)
GET_SCORE_ABI = [{"name": "getScore", "type": "function", "stateMutability": "view", "inputs": [{"type": "address"}],
                  "outputs": [{"type": "tuple", "components": [
                      {"name": "adminKeyScore", "type": "uint8"}, {"name": "multisigScore", "type": "uint8"},
                      {"name": "timelockScore", "type": "uint8"}, {"name": "oracleAuthorityScore", "type": "uint8"},
                      {"name": "crossExposureScore", "type": "uint8"}, {"name": "compositeScore", "type": "uint8"},
                      {"name": "lastUpdated", "type": "uint64"}, {"name": "methodologyHash", "type": "bytes32"}]}]}]


def is_degraded(entry) -> bool:
    floor = (entry.get("adminKeyScore"), entry.get("multisigScore"), entry.get("timelockScore")) == (20, 20, 0)
    return floor or any(DEGRADED.search(str(n)) for n in entry.get("notes", []))


def key_of(entry) -> str:
    """The address the entry is stored under on-chain: Hyperliquid moves a colliding HIP-3 dex to a derived `oracleKey`."""
    return entry.get("oracleKey", entry["target"])


def _read_scores(oracle_w3, oracle_address, targets) -> dict:
    """{target lowercase: getScore tuple} for the targets the oracle already holds (lastUpdated != 0). Raises on a failed
    read: the caller must not treat it as 'nothing published'."""
    c = oracle_w3.eth.contract(address=Web3.to_checksum_address(oracle_address), abi=GET_SCORE_ABI)
    out = {}
    for t in targets:
        s = c.functions.getScore(Web3.to_checksum_address(t)).call()
        if s[6]:
            out[t.lower()] = s
    return out


def read_published(oracle_w3, oracle_address, targets) -> dict:
    """{target lowercase: published composite}; raises on a failed read."""
    return {t: s[5] for t, s in _read_scores(oracle_w3, oracle_address, targets).items()}


def review(scored, published, accepted=(), published_oracle=None):
    """(held entries, report lines). published: {target lowercase: composite}, or None when it was not read.
    published_oracle: {target lowercase: oracleAuthorityScore}, or None when not read."""
    accepted = {a.lower() for a in accepted}
    held, lines = [], []
    for e in scored:
        t, new = key_of(e).lower(), e["compositeScore"]
        old = None if published is None else published.get(t)
        why = []
        if is_degraded(e) and (published is None or old != new):
            why.append("scorer took a degraded/unresolved branch" + ("" if published is None else f", published {old} -> new {new}"))
        if old is not None and old - new > MAX_DROP:
            why.append(f"composite drops {old} -> {new} (more than {MAX_DROP})")
        old_o, new_o = (published_oracle or {}).get(t), e.get("oracleAuthorityScore")
        unread = any(ORACLE_UNREAD.search(str(n)) for n in e.get("notes", []))
        if old_o is not None and new_o is not None and new_o != old_o:
            if unread:
                why.append(f"oracleAuthorityScore {old_o} -> {new_o} (a material price path is UNREAD)")
            elif old_o - new_o > MAX_DROP:
                why.append(f"oracleAuthorityScore {old_o} -> {new_o} (drops more than {MAX_DROP})")
            elif new_o == 100:
                why.append(f"oracleAuthorityScore {old_o} -> 100 (no material price path left: check it is really not applicable)")
        if why:
            status = "accepted by hand" if t in accepted else "HELD"
            lines.append(f"  {status}: {e.get('label', '')} {key_of(e)}: {'; '.join(why)}")
            if t not in accepted:
                held.append(e)
    return held, lines


def _accepted(argv):
    """--accept-held=0xA,0xB or --accept-held 0xA,0xB (the form argparse also accepts)."""
    argv = list(argv)
    for i, a in enumerate(argv):
        if a.startswith("--accept-held="):
            return [x.strip() for x in a.split("=", 1)[1].split(",") if x.strip()]
        if a == "--accept-held" and i + 1 < len(argv):
            return [x.strip() for x in argv[i + 1].split(",") if x.strip()]
    return []


def enforce(scored, oracle_w3=None, oracle_address=None, argv=None, accepted=None, skip_published_check=None):
    """Dry run (oracle_w3 None): print the report. Real send: read the published scores, print, and SystemExit while any
    entry is held and not accepted by address. `accepted` / `skip_published_check` are passed explicitly by a script
    that parses its own flags (argparse); otherwise they are read from argv (default sys.argv)."""
    argv = sys.argv if argv is None else argv
    accepted = _accepted(argv) if accepted is None else [a.strip() for a in accepted if a.strip()]
    skip = ("--skip-published-check" in argv) if skip_published_check is None else skip_published_check
    if oracle_w3 is None:
        held, lines = review(scored, None, accepted)
        print(f"\nPush guard (dry run, published scores not read): {len(held)} entr{'y' if len(held) == 1 else 'ies'} would be held "
              "for a degraded branch; the composite-drop and oracleAuthorityScore checks run only before a real send")
        print("\n".join(lines) if lines else "  none")
        return held
    try:
        raw = _read_scores(oracle_w3, oracle_address, [key_of(e) for e in scored])
        published, published_oracle = {t: s[5] for t, s in raw.items()}, {t: s[3] for t, s in raw.items()}
    except Exception as e:  # noqa: BLE001 -- a failed read is never 'nothing changed'
        if not skip:
            raise SystemExit(f"Push guard: published scores UNREAD ({type(e).__name__}: {e}); refusing to push. "
                             "Re-run, or pass --skip-published-check after checking by hand.")
        published = published_oracle = None
        print("Push guard: published scores UNREAD, --skip-published-check given: drop check not run")
    held, lines = review(scored, published, accepted, published_oracle)
    print(f"\nPush guard: {len(held)} entr{'y' if len(held) == 1 else 'ies'} held")
    print("\n".join(lines) if lines else "  none")
    if held:
        raise SystemExit("Push guard: refusing to push. Look at each HELD entry, then re-run with "
                         f"--accept-held={','.join(key_of(e) for e in held)} if it is right.")
    return held
