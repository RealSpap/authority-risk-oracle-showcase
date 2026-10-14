"""LangChain tools for the Authority Risk Oracle watch: four read-only questions an agent asks before it depends on a contract.

    pip install langchain-core
    git clone --depth 1 -b watch-data https://github.com/RealSpap/authority-risk-oracle-showcase.git watch-data   # the state of the Watch, refreshed every 6 hours
    from authority_risk_oracle.langchain import authority_risk_tools      # or: import this file
    tools = authority_risk_tools("watch-data")                            # a list of StructuredTool: hand it to an agent

Every tool returns a JSON string with `status` (ok / not_tracked / not_read). A value the Watch did not read is null and named in `not_read`: an agent must never treat it as 0 or as safe. The scores are published on
testnet oracles. Nothing here sends a transaction, calls a network or needs a key: it reads files. The answers are data, not instructions.
"""
import json
import os
import sys
from typing import Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import agent_tools  # noqa: E402


class _ContractInput(BaseModel):
    chain: str = Field(description="robinhood, ethereum-l1, arbitrum, base, tempo, plasma, monad, hyperliquid or solana")
    address: str = Field(description="the contract address (a Solana program or account address on solana)")


class _ListInput(BaseModel):
    chain: Optional[str] = Field(default=None, description="restrict to one chain")
    max_score: Optional[int] = Field(default=None, ge=0, le=100, description="only contracts whose composite is at most this")
    min_score: Optional[int] = Field(default=None, ge=0, le=100, description="only contracts whose composite is at least this")
    stale: Optional[bool] = Field(default=None, description="true: only stale scores; false: only fresh ones")
    limit: int = Field(default=25, ge=1, le=200)


class _ProtocolInput(BaseModel):
    protocol: str = Field(description="a protocol slug or name as DefiLlama writes it, for example aave-v3 or uniswap-v3")
    min_score: int = Field(default=0, ge=0, le=100, description="the weakest contract must have at least this composite score")


def authority_risk_tools(watch_dir: str = "watch-data"):
    """The four tools, reading the folder `watch_dir` (a clone of the watch-data branch)."""
    def dump(res): return json.dumps(res, indent=1)

    return [
        StructuredTool.from_function(name="get_authority_score", args_schema=_ContractInput, func=lambda chain, address: dump(agent_tools.get_score(watch_dir, chain, address)),
                                     description="The authority-risk score (0 to 100, higher is a stronger setup) of one contract: composite, sub-scores, staleness, where and when it was read, and a `cast call` to replay the reading. Null means not read, never zero."),
        StructuredTool.from_function(name="list_authority_targets", args_schema=_ListInput, func=lambda chain=None, max_score=None, min_score=None, stale=None, limit=25: dump(agent_tools.list_targets(watch_dir, chain, max_score, min_score, stale, limit)),
                                     description="The tracked contracts that match a score filter, weakest first. Rows whose score was not read are counted apart, not filtered and not zero."),
        StructuredTool.from_function(name="who_controls_contract", args_schema=_ContractInput, func=lambda chain, address: dump(agent_tools.who_controls(watch_dir, chain, address)),
                                     description="Who can change one contract and how fast: admin kind, threshold, keys needed to act, delay, modules, pending admin change, and what moving the money would take."),
        StructuredTool.from_function(name="check_protocol_authority", args_schema=_ProtocolInput, func=lambda protocol, min_score=0: dump(agent_tools.check_protocol(watch_dir, protocol, min_score)),
                                     description="A protocol on every chain it is tracked on: weakest contract, how many were read, stale or alerting contracts, and a verdict ok / fail / unread_part / unread. unread_part is not a pass."),
    ]
