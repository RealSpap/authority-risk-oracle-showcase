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

    // ADDED 2026-10-11 (second review): a mutation that removed the multisig, timelock and oracleAuthority range checks left all
    // 20 tests green, so each sub-score is now pinned on its own. ScoreOutOfRange reports the composite, whichever field is bad
    // (documented below), so the revert data is the same for the five sub-scores.
    function _expectOutOfRange(AuthorityRiskOracle.AuthorityScore memory score) private {
        vm.prank(updater);
        vm.expectRevert(abi.encodeWithSelector(AuthorityRiskOracle.ScoreOutOfRange.selector, vault, score.compositeScore));
        oracle.updateScore(vault, score);
    }

    function test_EachSubScoreAbove100RevertsOnItsOwn() public {
        AuthorityRiskOracle.AuthorityScore memory s = _sampleScore(75);
        s.adminKeyScore = 101;
        _expectOutOfRange(s);
        s = _sampleScore(75);
        s.multisigScore = 101;
        _expectOutOfRange(s);
        s = _sampleScore(75);
        s.timelockScore = 101;
        _expectOutOfRange(s);
        s = _sampleScore(75);
        s.oracleAuthorityScore = 101;
        _expectOutOfRange(s);
        s = _sampleScore(75);
        s.crossExposureScore = 101;
        _expectOutOfRange(s);
    }

    function test_EachSubScoreOfExactly100IsAccepted() public {
        AuthorityRiskOracle.AuthorityScore memory s = _sampleScore(75);
        s.adminKeyScore = 100;
        s.multisigScore = 100;
        s.timelockScore = 100;
        s.oracleAuthorityScore = 100;
        s.crossExposureScore = 100;
        vm.prank(updater);
        oracle.updateScore(vault, s);
        assertEq(oracle.getScore(vault).timelockScore, 100);
    }

    // DOCUMENTED LIMITS of the deployed contract (found by an independent review on 2026-10-11, not changed because redeploying the
    // nine oracles is not part of this release): lastUpdated is whatever the updater pushes, not block.timestamp, and the
    // freshness check adds maxStaleness to it with checked arithmetic. The Solana program takes the time from the Clock instead.
    // These tests state the behaviour so that nobody reads isStale() as a guarantee against a compromised updater.
    function test_Limitation_LastUpdatedIsTheUpdatersValueNotTheChains() public {
        AuthorityRiskOracle.AuthorityScore memory s = _sampleScore(75);
        s.lastUpdated = uint64(block.timestamp + 100 * 365 days);
        vm.prank(updater);
        oracle.updateScore(vault, s);
        vm.warp(block.timestamp + 50 * 365 days);
        assertFalse(oracle.isStale(vault)); // an updater that sets a far-future time keeps the score looking fresh
    }

    function test_Limitation_IsStaleRevertsOnOverflow() public {
        AuthorityRiskOracle.AuthorityScore memory s = _sampleScore(75);
        s.lastUpdated = type(uint64).max;
        vm.prank(updater);
        oracle.updateScore(vault, s);
        vm.expectRevert(); // Panic(0x11): lastUpdated + maxStaleness overflows uint64
        oracle.isStale(vault);
    }
}
