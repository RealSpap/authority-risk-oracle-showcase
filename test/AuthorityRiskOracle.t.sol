// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {AuthorityRiskOracle} from "../src/AuthorityRiskOracle.sol";

contract AuthorityRiskOracleTest is Test {
    AuthorityRiskOracle oracle;
    address admin = makeAddr("admin");
    address updater = makeAddr("updater");
    address stranger = makeAddr("stranger");
    address vault = makeAddr("vault");

    function setUp() public {
        oracle = new AuthorityRiskOracle(admin);

        bytes32 updaterRole = oracle.UPDATER_ROLE();
        vm.prank(admin);
        oracle.grantRole(updaterRole, updater);
    }

    function _sampleScore(uint8 composite) internal view returns (AuthorityRiskOracle.AuthorityScore memory) {
        return _sampleScoreWithExposure(composite, 100);
    }

    function _sampleScoreWithExposure(uint8 composite, uint8 crossExposure)
        internal
        view
        returns (AuthorityRiskOracle.AuthorityScore memory)
    {
        return AuthorityRiskOracle.AuthorityScore({
            adminKeyScore: 70,
            multisigScore: 65,
            timelockScore: 80,
            oracleAuthorityScore: 90,
            crossExposureScore: crossExposure,
            compositeScore: composite,
            lastUpdated: uint64(block.timestamp),
            methodologyHash: keccak256("v1")
        });
    }

    function test_UpdaterCanPushScore() public {
        vm.prank(updater);
        oracle.updateScore(vault, _sampleScore(75));

        AuthorityRiskOracle.AuthorityScore memory stored = oracle.getScore(vault);
        assertEq(stored.compositeScore, 75);
        assertEq(stored.crossExposureScore, 100);
        assertEq(stored.lastUpdated, block.timestamp);
        assertFalse(oracle.isStale(vault));
    }

    function test_CrossExposureScoreStoredAndReadIndependentlyOfComposite() public {
        vm.prank(updater);
        oracle.updateScore(vault, _sampleScoreWithExposure(75, 40));

        AuthorityRiskOracle.AuthorityScore memory stored = oracle.getScore(vault);
        assertEq(stored.compositeScore, 75, "compositeScore must not fold in crossExposureScore");
        assertEq(stored.crossExposureScore, 40);
    }

    function test_StrangerCannotPushScore() public {
        vm.prank(stranger);
        vm.expectRevert();
        oracle.updateScore(vault, _sampleScore(75));
    }

    function test_UnscoredTargetIsStale() public view {
        assertTrue(oracle.isStale(vault));
    }

    function test_ScoreBecomesStaleAfterMaxStaleness() public {
        vm.prank(updater);
        oracle.updateScore(vault, _sampleScore(75));
        assertFalse(oracle.isStale(vault));

        vm.warp(block.timestamp + oracle.maxStaleness() + 1);
        assertTrue(oracle.isStale(vault));
    }

    function test_TrackedTargetsAccumulateWithoutDuplicates() public {
        address vault2 = makeAddr("vault2");

        vm.startPrank(updater);
        oracle.updateScore(vault, _sampleScore(75));
        oracle.updateScore(vault2, _sampleScore(40));
        oracle.updateScore(vault, _sampleScore(80)); // re-score, should not duplicate
        vm.stopPrank();

        assertEq(oracle.trackedTargetsCount(), 2);
        assertEq(oracle.trackedTargets(0), vault);
        assertEq(oracle.trackedTargets(1), vault2);
        assertEq(oracle.getScore(vault).compositeScore, 80);
    }

    function test_BatchUpdateScoresSeveralTargetsInOneTx() public {
        address vault2 = makeAddr("vault2");
        address[] memory targets = new address[](2);
        targets[0] = vault;
        targets[1] = vault2;

        AuthorityRiskOracle.AuthorityScore[] memory scores = new AuthorityRiskOracle.AuthorityScore[](2);
        scores[0] = _sampleScore(75);
        scores[1] = _sampleScore(30);

        vm.prank(updater);
        oracle.updateScores(targets, scores);

        assertEq(oracle.trackedTargetsCount(), 2);
        assertEq(oracle.getScore(vault).compositeScore, 75);
        assertEq(oracle.getScore(vault2).compositeScore, 30);
    }

    function test_BatchUpdateRevertsOnLengthMismatch() public {
        address[] memory targets = new address[](2);
        targets[0] = vault;
        targets[1] = makeAddr("vault2");

        AuthorityRiskOracle.AuthorityScore[] memory scores = new AuthorityRiskOracle.AuthorityScore[](1);
        scores[0] = _sampleScore(75);

        vm.prank(updater);
        vm.expectRevert(AuthorityRiskOracle.ArrayLengthMismatch.selector);
        oracle.updateScores(targets, scores);
    }

    function test_BatchUpdateRevertsOnEmptyBatch() public {
        address[] memory targets = new address[](0);
        AuthorityRiskOracle.AuthorityScore[] memory scores = new AuthorityRiskOracle.AuthorityScore[](0);

        vm.prank(updater);
        vm.expectRevert(AuthorityRiskOracle.EmptyBatch.selector);
        oracle.updateScores(targets, scores);
    }

    function test_AdminCanTuneMaxStaleness() public {
        vm.prank(admin);
        oracle.setMaxStaleness(1 days);
        assertEq(oracle.maxStaleness(), 1 days);
    }

    function test_StrangerCannotTuneMaxStaleness() public {
        vm.prank(stranger);
        vm.expectRevert();
        oracle.setMaxStaleness(1 days);
    }

    // ADDED (item 9, "secure the contract before any paid pitch"): every
    // sub-score is documented as 0-100 everywhere off-chain, but nothing
    // on-chain enforced that before this pass -- a uint8 is only bounded to
    // 0-255 by the type system, and ExampleConsumer.sol's own
    // collateralFactorBps() would silently compute a nonsensical collateral
    // factor (~196% for a compositeScore of 255) if that assumption were
    // ever violated, whether by an off-chain bug or a compromised updater key.

    function test_CompositeScoreAbove100Reverts() public {
        AuthorityRiskOracle.AuthorityScore memory score = _sampleScore(75);
        score.compositeScore = 255;
        vm.prank(updater);
        vm.expectRevert(abi.encodeWithSelector(AuthorityRiskOracle.ScoreOutOfRange.selector, vault, 255));
        oracle.updateScore(vault, score);
    }

    function test_AnySubScoreAbove100Reverts() public {
        AuthorityRiskOracle.AuthorityScore memory score = _sampleScore(75);
        score.adminKeyScore = 101; // compositeScore itself stays in-range; a sub-score doesn't
        vm.prank(updater);
        vm.expectRevert(abi.encodeWithSelector(AuthorityRiskOracle.ScoreOutOfRange.selector, vault, 75));
        oracle.updateScore(vault, score);
    }

    function test_ScoreOfExactly100IsAccepted() public {
        vm.prank(updater);
        oracle.updateScore(vault, _sampleScore(100));
        assertEq(oracle.getScore(vault).compositeScore, 100);
    }

    function test_BatchUpdateRevertsWholeBatchIfAnyEntryOutOfRange() public {
        address vault2 = makeAddr("vault2");
        address[] memory targets = new address[](2);
        targets[0] = vault;
        targets[1] = vault2;

        AuthorityRiskOracle.AuthorityScore memory badScore = _sampleScore(75);
        badScore.crossExposureScore = 200;

        AuthorityRiskOracle.AuthorityScore[] memory scores = new AuthorityRiskOracle.AuthorityScore[](2);
        scores[0] = _sampleScore(75);
        scores[1] = badScore;

        vm.prank(updater);
        vm.expectRevert(abi.encodeWithSelector(AuthorityRiskOracle.ScoreOutOfRange.selector, vault2, 75));
        oracle.updateScores(targets, scores);

        // Neither entry should have been written -- a batch is one transaction,
        // a revert on entry 2 must roll back entry 1 too, not partially apply.
        assertTrue(oracle.isStale(vault));
    }
}
