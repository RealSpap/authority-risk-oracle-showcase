// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";

/// @title AuthorityRiskOracle
/// @notice Publishes a continuously-updated, independently-computed authority-risk score
///         (admin key concentration, multisig weakness, timelock delay, oracle-signer
///         authority, cross-protocol signer exposure) for on-chain protocols, so other
///         contracts can read it directly instead of trusting a closed dashboard or a
///         risk provider paid by the protocol it rates.
/// @dev Scores are computed off-chain (eth_call/eth_getLogs against 2+ independent RPCs,
///      reusing this project's existing classify_holder()/resolve_roles()/
///      getUniqueSignersThreshold() methodology from defi-admin-key-risk, and the
///      signer-overlap-across-protocols methodology from multisig-overlap for
///      crossExposureScore) and pushed on-chain by an address holding UPDATER_ROLE. The
///      contract itself does not attempt on-chain computation of the score - it is a
///      verifiable publication point, not a computation engine.
contract AuthorityRiskOracle is AccessControl {
    bytes32 public constant UPDATER_ROLE = keccak256("UPDATER_ROLE");

    /// @notice A score is considered stale after this many seconds without an update.
    uint64 public maxStaleness = 9 days;

    struct AuthorityScore {
        uint8 adminKeyScore; // 0-100: bare EOA (low) .. Safe .. real Timelock (high)
        uint8 multisigScore; // 0-100: signer threshold/dispersion strength
        uint8 timelockScore; // 0-100: delay length and absence of bypass paths
        uint8 oracleAuthorityScore; // 0-100: price-report signer threshold, where applicable
        uint8 crossExposureScore; // 0-100: 100 = no root signer shared with any other
            // tracked target (or none checked for); each OTHER tracked target on the SAME
            // ecosystem sharing at least one resolved root signer with this one costs 20
            // points, floored at 0, and a root committee identical to a tracked target's on
            // ANOTHER ecosystem is capped at a flat 80 (METHODOLOGY.md, "Convention (decided
            // 2026-09-20)"). A separate dimension from the four above (a property of the
            // tracked SET, not of this target alone) -- deliberately NOT folded into
            // compositeScore, which stays exactly what it always meant: this target's own
            // authority setup. Full evidence (which signer, which other targets) lives
            // off-chain in data/, not on this contract.
        uint8 compositeScore; // 0-100: off-chain weighted aggregate of adminKey/multisig/timelock
        uint64 lastUpdated; // block.timestamp of the last update
        bytes32 methodologyHash; // hash identifying the scoring script/version used
    }

    mapping(address target => AuthorityScore score) private _scores;

    /// @notice Every address ever scored, in the order first scored. Lets a consumer or
    ///         frontend enumerate coverage without needing an off-chain indexer.
    address[] public trackedTargets;
    mapping(address target => bool tracked) private _isTracked;

    event ScoreUpdated(
        address indexed target,
        uint8 compositeScore,
        uint64 timestamp,
        bytes32 methodologyHash
    );
    event MaxStalenessUpdated(uint64 oldValue, uint64 newValue);

    error EmptyBatch();
    error ArrayLengthMismatch();
    /// @dev ADDED (item 9, "secure the contract before any paid pitch" -- see
    ///      data/contract_review_2026-09-17-llamaguard-comparison.md): none of
    ///      the five 0-100 sub-scores were previously validated on-chain. A
    ///      uint8 is mechanically bounded to 0-255 by the type system alone,
    ///      so nothing stopped a pushed value from 101 to 255 -- which
    ///      ExampleConsumer.sol's own collateralFactorBps() would silently
    ///      turn into a collateral factor far outside its intended 50-80%
    ///      range (a compositeScore of 255 computes to ~196%), a real bug in
    ///      a downstream consumer this contract itself ships as reference
    ///      code, not a hypothetical.
    error ScoreOutOfRange(address target, uint8 badValue);

    constructor(address admin) {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(UPDATER_ROLE, admin);
    }

    /// @notice Push a freshly-computed score for one target.
    function updateScore(address target, AuthorityScore calldata score) external onlyRole(UPDATER_ROLE) {
        _updateScore(target, score);
    }

    /// @notice Push scores for several targets in one transaction, to amortize the
    ///         weekly off-chain scoring run into a single on-chain call.
    function updateScores(address[] calldata targets, AuthorityScore[] calldata scores)
        external
        onlyRole(UPDATER_ROLE)
    {
        if (targets.length == 0) revert EmptyBatch();
        if (targets.length != scores.length) revert ArrayLengthMismatch();
        for (uint256 i = 0; i < targets.length; i++) {
            _updateScore(targets[i], scores[i]);
        }
    }

    function _updateScore(address target, AuthorityScore calldata score) private {
        // ADDED (item 9): every sub-score is documented, everywhere off-chain
        // (METHODOLOGY.md, every scorer's own convention), as 0-100 -- now
        // enforced here too, not just assumed by every off-chain caller and
        // every downstream on-chain consumer.
        if (
            score.adminKeyScore > 100 || score.multisigScore > 100 || score.timelockScore > 100
                || score.oracleAuthorityScore > 100 || score.crossExposureScore > 100 || score.compositeScore > 100
        ) {
            revert ScoreOutOfRange(target, score.compositeScore);
        }
        if (!_isTracked[target]) {
            _isTracked[target] = true;
            trackedTargets.push(target);
        }
        _scores[target] = score;
        emit ScoreUpdated(target, score.compositeScore, score.lastUpdated, score.methodologyHash);
    }

    /// @notice Read the current authority-risk score for `target`.
    /// @dev Consumers should check `isStale(target)` before trusting the result --
    ///      an unstaled zero score and a genuinely-uncovered target both read as zero.
    function getScore(address target) external view returns (AuthorityScore memory) {
        return _scores[target];
    }

    /// @notice True if `target` has never been scored, or its score is older than `maxStaleness`.
    function isStale(address target) public view returns (bool) {
        if (!_isTracked[target]) return true;
        return block.timestamp > _scores[target].lastUpdated + maxStaleness;
    }

    function trackedTargetsCount() external view returns (uint256) {
        return trackedTargets.length;
    }

    /// @notice Admin-only: adjust how long a score stays valid before reads should
    ///         treat it as stale. Kept tunable rather than a true constant since the
    ///         right cadence may change as off-chain RPC costs/rate limits evolve.
    function setMaxStaleness(uint64 newMaxStaleness) external onlyRole(DEFAULT_ADMIN_ROLE) {
        emit MaxStalenessUpdated(maxStaleness, newMaxStaleness);
        maxStaleness = newMaxStaleness;
    }
}
