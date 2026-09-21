// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {AuthorityRiskOracle} from "./AuthorityRiskOracle.sol";

/// @title ExampleConsumer
/// @notice Demonstrates how a lending-style contract would consume AuthorityRiskOracle
///         directly: it reads a vault's authority score and derives a collateral factor
///         from it, freezing collateral it considers governed by too weak an authority
///         and refusing a stale read outright. This is demo scaffolding for the
///         hackathon submission, not a production lending market.
contract ExampleConsumer {
    AuthorityRiskOracle public immutable ORACLE;

    /// @notice Below this composite score, a vault's collateral factor is forced to zero.
    uint8 public constant MIN_SAFE_SCORE = 60;

    /// @notice Collateral factor at MIN_SAFE_SCORE, in basis points (50.00%).
    uint256 public constant MIN_FACTOR_BPS = 5_000;

    /// @notice Collateral factor at a perfect 100 score, in basis points (80.00%).
    uint256 public constant MAX_FACTOR_BPS = 8_000;

    error StaleScore(address target);

    constructor(address oracleAddress) {
        ORACLE = AuthorityRiskOracle(oracleAddress);
    }

    /// @notice Collateral factor (basis points) this market would apply to `target`
    ///         right now, based solely on its live authority-risk score.
    function collateralFactorBps(address target) external view returns (uint256) {
        if (ORACLE.isStale(target)) revert StaleScore(target);

        AuthorityRiskOracle.AuthorityScore memory score = ORACLE.getScore(target);
        if (score.compositeScore < MIN_SAFE_SCORE) return 0;

        uint256 scoreRange = 100 - MIN_SAFE_SCORE;
        uint256 factorRange = MAX_FACTOR_BPS - MIN_FACTOR_BPS;
        uint256 scoreAboveMin = score.compositeScore - MIN_SAFE_SCORE;
        return MIN_FACTOR_BPS + (scoreAboveMin * factorRange) / scoreRange;
    }
}
