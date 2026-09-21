// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {AuthorityRiskOracle} from "../src/AuthorityRiskOracle.sol";
import {ExampleConsumer} from "../src/ExampleConsumer.sol";

/// @notice Deploys AuthorityRiskOracle (admin/updater = the deploying key for the
///         hackathon MVP) and the demo ExampleConsumer wired to it.
///         Usage: forge script script/Deploy.s.sol --rpc-url robinhood --broadcast
///         Requires PRIVATE_KEY set in the environment (never committed).
contract Deploy is Script {
    function run() external returns (AuthorityRiskOracle oracle, ExampleConsumer consumer) {
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
