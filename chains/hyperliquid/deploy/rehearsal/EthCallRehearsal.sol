// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {AuthorityRiskOracle} from "../../../../src/AuthorityRiskOracle.sol";
import {ExampleConsumer} from "../../../../src/ExampleConsumer.sol";

/// @notice Read-only deploy rehearsal harness for HyperEVM Testnet (chain 998).
///         NEVER broadcast. It is only ever executed as the init code of an
///         `eth_call` with no `to` field (a simulated contract creation), so
///         nothing is written on-chain, no key signs anything and no balance
///         is needed. Inside that one simulated creation it:
///           1. deploys the unmodified `src/AuthorityRiskOracle.sol` (admin/updater = this harness)
///           2. deploys the unmodified `src/ExampleConsumer.sol` wired to it
///           3. pushes the scores via the real `updateScores()` entry point
///           4. reads every score back through SEPARATE external `getScore()` calls
///           5. returns everything ABI-encoded as the "runtime code" of the creation
///         so the caller can compare what went in against what came back out.
///         Written 2026-09-19 because Foundry (anvil/forge/cast) is no longer
///         installed on the host that runs this pipeline -- see ../README.md.
contract EthCallRehearsal {
    constructor(address[] memory targets, AuthorityRiskOracle.AuthorityScore[] memory scores) {
        uint256[3] memory gasUsed; // [oracle deploy, consumer deploy, updateScores], execution gas only (no intrinsic/calldata gas)
        uint256 g = gasleft();
        AuthorityRiskOracle oracle = new AuthorityRiskOracle(address(this));
        gasUsed[0] = g - gasleft();
        g = gasleft();
        ExampleConsumer consumer = new ExampleConsumer(address(oracle));
        gasUsed[1] = g - gasleft();
        bool updaterBefore = oracle.hasRole(oracle.UPDATER_ROLE(), address(this));

        g = gasleft();
        oracle.updateScores(targets, scores);
        gasUsed[2] = g - gasleft();

        AuthorityRiskOracle.AuthorityScore[] memory back = new AuthorityRiskOracle.AuthorityScore[](targets.length);
        bool[] memory stale = new bool[](targets.length);
        for (uint256 i = 0; i < targets.length; i++) {
            back[i] = oracle.getScore(targets[i]);
            stale[i] = oracle.isStale(targets[i]);
        }

        bytes memory out = abi.encode(
            address(oracle),
            address(consumer),
            address(consumer.ORACLE()),
            updaterBefore,
            oracle.trackedTargetsCount(),
            address(oracle).codehash,
            back,
            stale,
            gasUsed
        );
        assembly {
            return(add(out, 32), mload(out))
        }
    }
}
