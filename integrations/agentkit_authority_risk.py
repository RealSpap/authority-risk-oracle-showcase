"""Coinbase AgentKit action provider for the Authority Risk Oracle watch: four read-only actions, no wallet, no transaction, no key.

    pip install coinbase-agentkit
    git clone --depth 1 -b watch-data https://github.com/RealSpap/authority-risk-oracle-showcase.git watch-data
    agent_kit = AgentKit(AgentKitConfig(wallet_provider=wallet, action_providers=[authority_risk_action_provider("watch-data"), ...]))

The actions answer in JSON with `status` (ok / not_tracked / not_read); a value not read is null, never 0. The scores are published on TESTNET oracles for contracts of the networks named in each answer: an agent must not
present them as mainnet data. The provider supports every network (it reads files, it does not use the wallet).
"""
import json
import os
import sys
from typing import Any

from coinbase_agentkit import ActionProvider, create_action
from coinbase_agentkit.network import Network
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import agent_tools  # noqa: E402


class GetScoreSchema(BaseModel):
    chain: str = Field(..., description="robinhood, ethereum-l1, arbitrum, base, tempo, plasma, monad, hyperliquid or solana")
    address: str = Field(..., description="the contract address")


class ListTargetsSchema(BaseModel):
    chain: str | None = Field(default=None, description="restrict to one chain")
    max_score: int | None = Field(default=None, ge=0, le=100)
    min_score: int | None = Field(default=None, ge=0, le=100)
    stale: bool | None = Field(default=None)
    limit: int = Field(default=25, ge=1, le=200)


class CheckProtocolSchema(BaseModel):
    protocol: str = Field(..., description="a protocol slug or name, for example aave-v3")
    min_score: int = Field(default=0, ge=0, le=100)


class AuthorityRiskActionProvider(ActionProvider):
    """Reads who can change a contract and how fast, from the published files of the Authority Risk Oracle watch."""

    def __init__(self, watch_dir: str = "watch-data"):
        super().__init__("authority_risk", [])
        self.watch_dir = watch_dir

    @create_action(name="get_authority_score", description="The authority-risk score (0 to 100, higher is a stronger setup) of one contract: composite, sub-scores, staleness, where and when it was read, and a `cast call` to replay the reading. Null means not read, never zero. Inputs: chain, address.", schema=GetScoreSchema)
    def get_authority_score(self, args: dict[str, Any]) -> str:
        a = GetScoreSchema(**args)
        return json.dumps(agent_tools.get_score(self.watch_dir, a.chain, a.address))

    @create_action(name="list_authority_targets", description="The tracked contracts that match a score filter, weakest first; rows whose score was not read are counted apart. Inputs: chain, max_score, min_score, stale, limit.", schema=ListTargetsSchema)
    def list_authority_targets(self, args: dict[str, Any]) -> str:
        a = ListTargetsSchema(**args)
        return json.dumps(agent_tools.list_targets(self.watch_dir, a.chain, a.max_score, a.min_score, a.stale, a.limit))

    @create_action(name="who_controls_contract", description="Who can change one contract and how fast: admin kind, threshold, keys needed to act, delay, modules, pending admin change, and what moving the money would take. Inputs: chain, address.", schema=GetScoreSchema)
    def who_controls_contract(self, args: dict[str, Any]) -> str:
        a = GetScoreSchema(**args)
        return json.dumps(agent_tools.who_controls(self.watch_dir, a.chain, a.address))

    @create_action(name="check_protocol_authority", description="A protocol on every chain it is tracked on: weakest contract, contracts read, stale or alerting ones, and a verdict ok / fail / unread_part / unread (unread_part is not a pass). Inputs: protocol, min_score.", schema=CheckProtocolSchema)
    def check_protocol_authority(self, args: dict[str, Any]) -> str:
        a = CheckProtocolSchema(**args)
        return json.dumps(agent_tools.check_protocol(self.watch_dir, a.protocol, a.min_score))

    def supports_network(self, network: Network) -> bool:
        return True


def authority_risk_action_provider(watch_dir: str = "watch-data") -> AuthorityRiskActionProvider:
    return AuthorityRiskActionProvider(watch_dir)
