// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {HardenedConsumer} from "../src/HardenedConsumer.sol";
import {MockOracle} from "../src/MockOracle.sol";

interface Vm { function warp(uint256) external; function expectRevert(bytes calldata) external; }

/// Tests without forge-std (not installed here): the two cheat codes used are declared above.
contract HardenedConsumerTest {
    Vm constant vm = Vm(0x7109709ECfa91a80626fF3989D68f67F5b1DD12D);
    bytes32 constant H3 = 0x7a8280d6128fcfffdfcab3e45d617360c4caa1a521e1ecf4f002e4762b4b3606;   // a real 2026.10.3 hash (Robinhood Chain)
    bytes32 constant H4 = keccak256("a new method version nobody has read");
    address constant T = address(0x1F98431c8aD98523631AE4a59f267346ea31F984);
    MockOracle o; HardenedConsumer c;
    function setUp() public { vm.warp(1_790_000_000); o = new MockOracle(); bytes32[] memory k = new bytes32[](1); k[0] = H3; c = new HardenedConsumer(address(o), 7 days, k); }
    function _check(bool g, string memory m) internal pure { require(g, m); }

    function testGreen_freshKnownScoreGivesTheLinearFactor() public { o.set(T, 60, uint64(block.timestamp - 1 days), H3, false); _check(c.collateralFactorBps(T) == 5_000, "60 -> 5000"); o.set(T, 80, uint64(block.timestamp - 1 days), H3, false); _check(c.collateralFactorBps(T) == 6_500, "80 -> 6500"); o.set(T, 100, uint64(block.timestamp), H3, false); _check(c.collateralFactorBps(T) == 8_000, "100 -> 8000"); }
    function testGreen_belowTheThresholdIsZero() public { o.set(T, 59, uint64(block.timestamp), H3, false); _check(c.collateralFactorBps(T) == 0, "59 -> 0"); }
    function testRed_unknownMethodHashIsRefused() public { o.set(T, 90, uint64(block.timestamp), H4, false); vm.expectRevert(abi.encodeWithSelector(HardenedConsumer.UnknownMethod.selector, H4)); c.collateralFactorBps(T); }
    function testRed_sameNumberUnderTheOldHashStillWorks_butNotUnderTheNewOne() public { o.set(T, 80, uint64(block.timestamp), H3, false); _check(c.collateralFactorBps(T) == 6_500, "old hash ok"); o.set(T, 80, uint64(block.timestamp), H4, false); vm.expectRevert(abi.encodeWithSelector(HardenedConsumer.UnknownMethod.selector, H4)); c.collateralFactorBps(T); }
    function testRed_oracleSaysStale() public { o.set(T, 90, uint64(block.timestamp - 10 days), H3, true); vm.expectRevert(abi.encodeWithSelector(HardenedConsumer.StaleScore.selector, T)); c.collateralFactorBps(T); }
    function testRed_olderThanTheConsumersOwnLimitEvenIfNotStale() public { o.set(T, 90, uint64(block.timestamp - 8 days), H3, false); vm.expectRevert(abi.encodeWithSelector(HardenedConsumer.TooOld.selector, T, uint64(8 days))); c.collateralFactorBps(T); }
    function testGreen_exactlyAtTheAgeLimitPasses() public { o.set(T, 90, uint64(block.timestamp - 7 days), H3, false); _check(c.collateralFactorBps(T) > 0, "7 days ok"); }
}
