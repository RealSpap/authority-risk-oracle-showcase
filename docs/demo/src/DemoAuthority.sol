// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/// Made-up contracts for a local demo. DemoAuthority is NOT a real multisig: it stores three numbers that stand for
/// "how many signers must agree", "how many owners there are" and "the notice period in seconds".
/// Anyone can call the setters: that is on purpose, the demo runs on a private local chain.
contract DemoAuthority {
    uint256 public threshold;
    uint256 public ownerCount;
    uint256 public minDelay;

    constructor(uint256 t, uint256 o, uint256 d) { threshold = t; ownerCount = o; minDelay = d; }

    function setThreshold(uint256 t) external { threshold = t; }
    function setMinDelay(uint256 d) external { minDelay = d; }
}

/// A made-up contract that does not answer the three questions: every call reverts. It stands for an authority nobody could read.
contract DemoOpaque {
    fallback() external { revert(); }
}
