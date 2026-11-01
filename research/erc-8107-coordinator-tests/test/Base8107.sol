// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.20;

// Shared setup for the ERC-8107 coordinator tests: a fork of Ethereum mainnet (read only: nothing is sent to the network, everything runs in forge's memory),
// the real ENS contracts, and the reference TrustRegistry of ethereum/ERCs deployed on the fork.
import "forge-std/Test.sol";
import {TrustRegistry} from "../ercs/contracts/TrustRegistry.sol";
import {TrustLevel, TrustAttestation, ValidationParams, TrustPath} from "../ercs/contracts/ITrustRegistry.sol";
import {RegistrationBoundary} from "../ercs/tests/continuity/RegistrationBoundary.sol";

struct Price { uint256 base; uint256 premium; }
struct Registration { string label; address owner; uint256 duration; bytes32 secret; address resolver; bytes[] data; uint8 reverseRecord; bytes32 referrer; }
interface IController {
    function makeCommitment(Registration calldata) external pure returns (bytes32);
    function commit(bytes32) external;
    function register(Registration calldata) external payable;
    function rentPrice(string calldata, uint256) external view returns (Price memory);
}
interface IBaseRegistrar {
    function nameExpires(uint256) external view returns (uint256);
    function GRACE_PERIOD() external view returns (uint256);
    function setApprovalForAll(address, bool) external;
    function register(uint256, address, uint256) external returns (uint256);
    function renew(uint256, uint256) external returns (uint256);
}
interface INameWrapper {
    function ownerOf(uint256) external view returns (address);
    function wrapETH2LD(string calldata, address, uint16, address) external returns (uint64);
    function setFuses(bytes32, uint16) external returns (uint32);
    function setSubnodeRecord(bytes32, string calldata, address, address, uint64, uint32, uint64) external returns (bytes32);
    function extendExpiry(bytes32, bytes32, uint64) external returns (uint64);
}
interface IEnsRegistry { function owner(bytes32) external view returns (address); }
interface IPublicResolver { function setAddr(bytes32, address) external; }

abstract contract Base8107 is Test {
    address constant ENS = 0x00000000000C2E074eC69A0dFb2997BA6C7d2e1e;
    address constant NAME_WRAPPER = 0xD4416b13d2b3a9aBae7AcD5D6C2BbDBE25686401;
    address constant BASE_REGISTRAR = 0x57f1887a8BF19b14fC0dF6Fd9B2acc9Af147eA85;
    address constant CONTROLLER = 0x59E16fcCd424Cc24e280Be16E11Bcd56fb0CE547;
    address constant RESOLVER = 0xF29100983E058B709F3D539b0c765937B804AC15;
    bytes32 constant ETH_NODE = 0x93cdeb708b7545dc668eb9280176169d1c33cfd8ed6f04690a0bcc88a93fc4ae;
    uint256 constant YEAR = 365 days;
    uint256 constant GRACE = 90 days;
    address constant COORD = address(0xC00D);       // the coordinator contract that owns the identity gate
    bytes32 constant CTYPE = keccak256("erc-8107-coordinator-tests");

    TrustRegistry reg;
    uint256 constant PK_G = uint256(keccak256("t-G")); uint256 constant PK_A = uint256(keccak256("t-A"));
    uint256 constant PK_X = uint256(keccak256("t-X")); uint256 constant PK_M = uint256(keccak256("t-M"));
    uint256 constant PK_H = uint256(keccak256("t-H"));
    address G; address A; address X; address M; address H;
    uint256 seq;
    mapping(bytes32 => string) labelOf; mapping(bytes32 => bytes32) parentOf;   // the name behind a node, for the coordinator's name proofs

    // logs of the registry, the BaseRegistrar and the NameWrapper, as the coordinator would have fetched them with eth_getLogs
    RegistrationBoundary.Log[] chainLogs;

    function setUp() public virtual {
        G = vm.addr(PK_G); A = vm.addr(PK_A); X = vm.addr(PK_X); M = vm.addr(PK_M); H = vm.addr(PK_H);
        reg = new TrustRegistry(ENS, NAME_WRAPPER);
    }

    function mutation() internal view returns (string memory) { return vm.envOr("MUTANT", string("none")); }
    function mutated(string memory m) internal view returns (bool) { return keccak256(bytes(mutation())) == keccak256(bytes(m)); }

    function id(string memory label) internal pure returns (uint256) { return uint256(keccak256(bytes(label))); }
    function nodeOf(string memory label) internal pure returns (bytes32) { return keccak256(abi.encodePacked(ETH_NODE, keccak256(bytes(label)))); }
    function name(string memory prefix) internal returns (string memory) { return string.concat("zt8107-", prefix, "-", vm.toString(++seq)); } // a prefix no real name has

    function registerName(string memory label, address who, uint256 duration) internal returns (bytes32) {
        vm.deal(who, 100 ether);
        bytes32 secret = keccak256(abi.encode(label, "t"));
        Registration memory r = Registration(label, who, duration, secret, RESOLVER, new bytes[](0), 0, bytes32(0));
        vm.prank(who); IController(CONTROLLER).commit(IController(CONTROLLER).makeCommitment(r));
        vm.warp(vm.getBlockTimestamp() + 61);
        Price memory p = IController(CONTROLLER).rentPrice(label, duration);
        vm.prank(who); IController(CONTROLLER).register{value: p.base + p.premium + 1 ether}(r);
        bytes32 n = nodeOf(label); labelOf[n] = label; parentOf[n] = ETH_NODE;
        return n;
    }
    function wrapName(string memory label, address who) internal {
        vm.startPrank(who);
        IBaseRegistrar(BASE_REGISTRAR).setApprovalForAll(NAME_WRAPPER, true);
        INameWrapper(NAME_WRAPPER).wrapETH2LD(label, who, 0, RESOLVER);
        vm.stopPrank();
    }
    function setAddr(bytes32 node, address controller, address target) internal { vm.prank(controller); IPublicResolver(RESOLVER).setAddr(node, target); }

    function attestation(bytes32 from, bytes32 to, uint64 expiry, uint64 nonce) internal pure returns (TrustAttestation memory) {
        return TrustAttestation({trustorNode: from, trusteeNode: to, level: TrustLevel.Full, scope: bytes32(0), expiry: expiry, nonce: nonce});
    }
    function endorse(uint256 signerKey, bytes32 from, bytes32 to) internal {
        TrustAttestation memory a = attestation(from, to, 0, reg.getNonce(from) + 1);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(signerKey, reg.hashAttestation(a));
        reg.setTrust(a, abi.encodePacked(r, s, v));
    }
    function pathOf2(bytes32 a, bytes32 b) internal pure returns (TrustPath memory p) { p.nodes = new bytes32[](2); p.nodes[0] = a; p.nodes[1] = b; }
    function pathOf3(bytes32 a, bytes32 b, bytes32 c) internal pure returns (TrustPath memory p) { p.nodes = new bytes32[](3); p.nodes[0] = a; p.nodes[1] = b; p.nodes[2] = c; }
    function openGate(bytes32 gatekeeper, bool enforceExpiry) internal {
        vm.prank(COORD);
        reg.setIdentityGate(CTYPE, gatekeeper, ValidationParams({maxPathLength: 4, minEdgeTrust: TrustLevel.Full, scope: bytes32(0), enforceExpiry: enforceExpiry, requiredAnchors: new bytes32[](0)}));
    }

    // Close a simulated block: keep the logs of the three emitters (what eth_getLogs would return), then move to the next block.
    function closeBlock() internal {
        Vm.Log[] memory ls = vm.getRecordedLogs();
        for (uint256 i = 0; i < ls.length; i++) {
            if (ls[i].emitter == BASE_REGISTRAR || ls[i].emitter == address(reg) || ls[i].emitter == NAME_WRAPPER) {
                chainLogs.push(RegistrationBoundary.Log(ls[i].emitter, ls[i].topics, ls[i].data, uint64(block.number), 0, uint32(i)));
            }
        }
        if (ls.length > 0) vm.roll(block.number + 1);
    }
    // The name behind a node, label by label up to the root ("x.parent.eth" is ["x", "parent", "eth"]).
    function nameProof(bytes32 node) internal view returns (RegistrationBoundary.NameProof memory pr) {
        uint256 count = 0; bytes32 cur = node;
        while (cur != ETH_NODE) { require(bytes(labelOf[cur]).length != 0 && count < 12, "unknown name"); count++; cur = parentOf[cur]; }
        string[] memory ls = new string[](count + 1); cur = node;
        for (uint256 i = 0; i < count; i++) { ls[i] = labelOf[cur]; cur = parentOf[cur]; }
        ls[count] = "eth";
        pr = RegistrationBoundary.NameProof(true, ls);
    }
    function nameProofs(bytes32[] memory nodes) internal view returns (RegistrationBoundary.NameProof[] memory ps) {
        ps = new RegistrationBoundary.NameProof[](nodes.length);
        for (uint256 i = 0; i < nodes.length; i++) ps[i] = nameProof(nodes[i]);
    }
    function history() internal view returns (RegistrationBoundary.History memory h) {
        h = RegistrationBoundary.History(0, uint64(block.number), chainLogs);
    }
    function yn(bool b) internal pure returns (string memory) { return b ? "yes" : "no"; }
}
