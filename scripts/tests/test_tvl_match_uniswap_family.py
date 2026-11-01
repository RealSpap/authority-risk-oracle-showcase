"""tvl_match.py: each Uniswap contract on Robinhood Chain is matched to the DefiLlama protocol it belongs to.

On 31 October 2026 the table sent the v4 PoolManager, the v2 factory and the UniswapX reactor to `uniswap-v3`, so the v3 figure was shown for
three contracts of other protocols and the v4 and v2 figures were never counted. DefiLlama lists uniswap-v2, uniswap-v3 and uniswap-v4 on
Robinhood Chain and no UniswapX protocol: a contract of a protocol DefiLlama does not list carries no figure (the page says so).
"""
import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tvl_match  # noqa: E402


class TestTvlMatchUniswapFamily(unittest.TestCase):
    def test_each_surface_has_its_own_protocol(self):
        got = {m[1]: m[2] for m in tvl_match.MAP if m[0] == "robinhood" and m[1] in ("0x1f7d7550", "0x8366a39c", "0x8bceaa40")}
        self.assertEqual(got, {"0x1f7d7550": "uniswap-v3", "0x8366a39c": "uniswap-v4", "0x8bceaa40": "uniswap-v2"})

    def test_the_uniswapx_reactor_has_no_figure(self):
        self.assertEqual([m for m in tvl_match.MAP if m[0] == "robinhood" and "0x000000007a1c".startswith(m[1])], [])


if __name__ == "__main__":
    unittest.main()
