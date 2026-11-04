"""tvl_match.py: the two GMX contracts on Arbitrum are matched to slugs that exist at DefiLlama.

The table named them `gmx-v2-perps` and `gmx-v1-perps`. DefiLlama lists those two protocols today as `gmx-evm` (previous name "GMX V2 Perps")
and `gmx-v1-evm` (previous name "GMX V1 Perps"); the old slugs do not exist, so the Watch put both contracts in `unknown_slugs` and they carried no figure.
"""
import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tvl_match  # noqa: E402


class TestTvlMatchGmx(unittest.TestCase):
    def test_each_gmx_contract_has_the_slug_that_exists(self):
        got = {m[1]: m[2] for m in tvl_match.MAP if m[0] == "arbitrum" and m[1] in ("0x3c3d99fd", "0x489ee077")}
        self.assertEqual(got, {"0x3c3d99fd": "gmx-evm", "0x489ee077": "gmx-v1-evm"})

    def test_the_old_slugs_are_gone(self):
        self.assertEqual([m for m in tvl_match.MAP if m[2] in ("gmx-v2-perps", "gmx-v1-perps")], [])


if __name__ == "__main__":
    unittest.main()
