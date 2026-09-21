// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {AuthorityRiskOracle} from "../src/AuthorityRiskOracle.sol";
import {ExampleConsumer} from "../src/ExampleConsumer.sol";

contract ExampleConsumerTest is Test {
    AuthorityRiskOracle oracle;
    ExampleConsumer consumer;
    address admin = makeAddr("admin");
    address vault = makeAddr("vault");

    function setUp() public {
        vm.prank(admin);
        oracle = new AuthorityRiskOracle(admin);
        consumer = new ExampleConsumer(address(oracle));
    }

    function _pushScore(uint8 composite) internal {
        vm.prank(admin);
        oracle.updateScore(
            vault,
            AuthorityRiskOracle.AuthorityScore({
                adminKeyScore: composite,
                multisigScore: composite,
                timelockScore: composite,
                oracleAuthorityScore: composite,
                crossExposureScore: 100,
                compositeScore: composite,
                lastUpdated: uint64(block.timestamp),
                methodologyHash: keccak256("v1")
            })
        );
    }

    function test_RevertsOnStaleScore() public {
        vm.expectRevert(abi.encodeWithSelector(ExampleConsumer.StaleScore.selector, vault));
        consumer.collateralFactorBps(vault);
    }

    function test_WeakAuthorityFreezesCollateral() public {
        _pushScore(40); // below MIN_SAFE_SCORE (60)
        assertEq(consumer.collateralFactorBps(vault), 0);
    }

    function test_ScoreAtFloorGivesMinFactor() public {
        _pushScore(60);
        assertEq(consumer.collateralFactorBps(vault), 5_000);
    }

    function test_PerfectScoreGivesMaxFactor() public {
        _pushScore(100);
        assertEq(consumer.collateralFactorBps(vault), 8_000);
    }

    function test_MidScoreInterpolatesLinearly() public {
        _pushScore(80); // halfway between 60 and 100
        assertEq(consumer.collateralFactorBps(vault), 6_500); // halfway between 5000 and 8000
    }
}
