// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {AuthorityRiskOracle} from "../src/AuthorityRiskOracle.sol";
import {ExampleConsumer} from "../src/ExampleConsumer.sol";

/// @notice Deploys AuthorityRiskOracle (admin/updater = the deploying key for the
///         hackathon MVP) and the demo ExampleConsumer wired to it.
///         Usage: EXPECTED_CHAIN_ID=46630 forge script script/Deploy.s.sol --rpc-url robinhood --broadcast
///         Requires PRIVATE_KEY set in the environment (never committed). EXPECTED_CHAIN_ID is mandatory: the script reverts
///         when the RPC answers another chain, so a wrong alias or URL cannot deploy to a mainnet by accident.
contract Deploy is Script {
    function run() external returns (AuthorityRiskOracle oracle, ExampleConsumer consumer) {
        require(block.chainid == vm.envUint("EXPECTED_CHAIN_ID"), "Deploy: the RPC chain id is not EXPECTED_CHAIN_ID");
        uint256 deployerKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);

        vm.startBroadcast(deployerKey);
        oracle = new AuthorityRiskOracle(deployer);
        consumer = new ExampleConsumer(address(oracle));
        vm.stopBroadcast();

        console.log("AuthorityRiskOracle deployed at:", address(oracle));
        console.log("ExampleConsumer deployed at:", address(consumer));
        console.log("Admin/Updater:", deployer);
    }
}
