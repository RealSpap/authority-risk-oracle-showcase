// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice The two calls of the Authority Risk Oracle that a consumer needs. Same signature as the deployed oracle:
///         getScore(address) returns (admin, multisig, timelock, oracleAuthority, crossExposure, composite, lastUpdated, methodologyHash).
interface IAuthorityOracle {
    struct AuthorityScore {
        uint8 adminKeyScore; uint8 multisigScore; uint8 timelockScore; uint8 oracleAuthorityScore; uint8 crossExposureScore; uint8 compositeScore;
        uint64 lastUpdated; bytes32 methodologyHash;
    }
    function getScore(address target) external view returns (AuthorityScore memory);
    function isStale(address target) external view returns (bool);
}

/// @title HardenedConsumer
/// @notice The example consumer of the repository, with two more refusals: a score older than the consumer's OWN age limit, and a score written under a
///         method version the consumer does not know. A score is a number under a rule; if the rule changes (a new methodologyHash), the same number can mean
///         something else, so the consumer refuses until a person has read the new method and deployed a version that lists its hash.
///         Trade-off (stated, not hidden): the list is fixed at deployment. Adding a hash means a new deployment; an admin function would put a key in front of
///         the very thing this contract exists to distrust. Demo code, not a lending market; nothing here is deployed.
contract HardenedConsumer {
    IAuthorityOracle public immutable ORACLE;
    uint64 public immutable MAX_AGE;                         // seconds; stricter than the oracle's own nine-day isStale
    uint8 public constant MIN_SAFE_SCORE = 60;
    uint256 public constant MIN_FACTOR_BPS = 5_000;
    uint256 public constant MAX_FACTOR_BPS = 8_000;
    mapping(bytes32 => bool) public knownMethod;

    error StaleScore(address target);
    error TooOld(address target, uint64 ageSeconds);
    error UnknownMethod(bytes32 methodologyHash);

    constructor(address oracle, uint64 maxAgeSeconds, bytes32[] memory knownHashes) {
        ORACLE = IAuthorityOracle(oracle); MAX_AGE = maxAgeSeconds;
        for (uint256 i = 0; i < knownHashes.length; i++) knownMethod[knownHashes[i]] = true;
    }

    function collateralFactorBps(address target) external view returns (uint256) {
        if (ORACLE.isStale(target)) revert StaleScore(target);
        IAuthorityOracle.AuthorityScore memory s = ORACLE.getScore(target);
        if (block.timestamp > s.lastUpdated && block.timestamp - s.lastUpdated > MAX_AGE) revert TooOld(target, uint64(block.timestamp - s.lastUpdated));
        if (!knownMethod[s.methodologyHash]) revert UnknownMethod(s.methodologyHash);
        if (s.compositeScore < MIN_SAFE_SCORE) return 0;
        return MIN_FACTOR_BPS + (uint256(s.compositeScore - MIN_SAFE_SCORE) * (MAX_FACTOR_BPS - MIN_FACTOR_BPS)) / (100 - MIN_SAFE_SCORE);
    }
}
