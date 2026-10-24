// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {IAuthorityOracle} from "./HardenedConsumer.sol";

/// @notice Test double: the score of a target is whatever the test writes. Never deployed.
contract MockOracle is IAuthorityOracle {
    mapping(address => AuthorityScore) public scores; mapping(address => bool) public stale;
    function set(address t, uint8 composite, uint64 lastUpdated, bytes32 hash_, bool isStale_) external { scores[t] = AuthorityScore(5, 5, 5, 5, 5, composite, lastUpdated, hash_); stale[t] = isStale_; }
    function getScore(address t) external view returns (AuthorityScore memory) { return scores[t]; }
    function isStale(address t) external view returns (bool) { return stale[t]; }
}
