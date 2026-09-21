"""Oracle key uniqueness guard, shared by the per-ecosystem push scripts.

The oracle stores ONE score per key (`_scores[target] = score` in AuthorityRiskOracle.sol, one PDA slot per target on Solana),
so two scored entries that map to the same key silently overwrite each other: `updateScores()` succeeds, the tracked count
is lower than the number of scores pushed, and the first entry can no longer be read back. This happened for real on
Hyperliquid (2026-09-19: 15 scores pushed, 13 stored, see chains/hyperliquid/deploy/push_scores.py `resolve_oracle_keys`)
and every other push script assembled its key list with no check at all. `assert_unique_oracle_keys` is the pre-flight
check they now share: it runs before any key is read and before any transaction is built, and refuses the whole push when
two entries collide.

WHICH KEY. The eight push scripts that call this (Arbitrum, Base, Monad, Plasma, Tempo, Ethereum L1, Robinhood Chain,
Solana) push `entry["target"]` and ignore any `oracleKey`, so the default here is `target` alone: a derived `oracleKey` must
NOT hide a collision there. Hyperliquid's push script does honour `oracleKey` (derived keys for HIP-3 dexes that sit at a
contract's address) and keeps its own resolution; `honour_oracle_key=True` mirrors that and is used by the audit tool for it.

HOW KEYS ARE COMPARED. EVM addresses are normalised like `Web3.to_checksum_address` sees them: case-insensitive, `0x` / `0X`
prefix optional, surrounding spaces ignored, raw bytes accepted. A Solana public key is base58, which is case-sensitive, so it
is compared exactly (`exact=True`).
"""

_HEX = set("0123456789abcdef")


def _evm_normalize(raw):
    if isinstance(raw, (bytes, bytearray)):
        return "0x" + bytes(raw).hex()
    s = str(raw).strip().lower()
    if not s.startswith("0x") and len(s) == 40 and set(s) <= _HEX:
        s = "0x" + s
    return s


def entry_key(entry, exact=False, honour_oracle_key=False):
    raw = entry.get("oracleKey", entry["target"]) if honour_oracle_key else entry["target"]
    return str(raw) if exact else _evm_normalize(raw)


def find_key_collisions(entries, exact=False, honour_oracle_key=False):
    """{key: [label, ...]} for every key that two or more entries map to. Empty when every key is unique."""
    groups = {}
    for e in entries:
        groups.setdefault(entry_key(e, exact, honour_oracle_key), []).append(e.get("label", "<no label>"))
    return {k: labels for k, labels in groups.items() if len(labels) > 1}


def assert_unique_oracle_keys(entries, exact=False, where="", honour_oracle_key=False):
    """Raise SystemExit, naming every colliding key and the entries on it, unless all keys are unique."""
    dupes = find_key_collisions(entries, exact, honour_oracle_key)
    if dupes:
        detail = "; ".join(f"{k} <- {labels}" for k, labels in sorted(dupes.items()))
        raise SystemExit(f"REFUSING{(' ' + where) if where else ''}: {len(dupes)} oracle key collision(s), "
                         f"a push would silently overwrite scores (the oracle keeps one score per key): {detail}")
