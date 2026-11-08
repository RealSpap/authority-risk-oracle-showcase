#!/usr/bin/env python3
"""Tempo push with a completeness check: refuses a push that is missing a tracked target, in a dry run too.

score_all() drops Held's arbiter with only a printed line ("... NOT scored this run") when the testnet answers badly, so a 14-line push
would otherwise go out without any alarm (found in a code review on 7 Nov 2026). This wrapper runs push_scores.py unchanged and stops right after
score_all(), before anything is encoded. It is a separate file on purpose: push_scores.py is one of the files that make up Tempo's method
hash, and this guard changes no score, so the published hash stays the one of the reviewed code.

Usage: the same arguments as push_scores.py (scripts/repush_all_oracles.sh calls this file for the Tempo step).
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("tempo_push_scores", os.path.join(HERE, "push_scores.py"))
ps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ps)
import scorers  # noqa: E402  (push_scores.py has put chains/tempo on sys.path)


def expected_count() -> int:
    """Lines of a complete Tempo push: the chain baseline, every token, the Vault V2 targets, Morpho Blue and Held's arbiter."""
    mt = scorers.mt
    return 1 + len(mt.TOKENS) + len(mt.VAULT_V2_TARGETS) + len(mt.MORPHO_BLUE_TARGETS) + len(mt.HELD_ARBITER_TARGETS)


def require_all_tracked(scored):
    want = expected_count()
    have = {str(e["target"]).lower() for e in scored}
    missing = [label for label, addr in scorers.mt.HELD_ARBITER_TARGETS.items() if addr.lower() not in have]
    if missing or len(scored) != want:
        raise SystemExit(f"REFUSING: {len(scored)} scored lines, {want} expected; not scored this run: {missing or 'see the lines above'}. "
                         "Re-run once, then read why (a 'NOT scored this run' line above).")


def main():
    real = ps.score_all

    def checked(*args, **kwargs):
        scored = real(*args, **kwargs)
        if scored:  # an empty result already stops push_scores.main() with its own message
            require_all_tracked(scored)
        return scored

    ps.score_all = checked
    ps.main()


if __name__ == "__main__":
    main()
