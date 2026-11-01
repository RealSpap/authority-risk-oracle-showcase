// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.20;

// A complete coordinator for ERC-8107 identity gates, written from the text of the ERC at commit 6b7a48ff, in two stages.
//
//   decide()   the coordinator's own check, at block B (off-chain in practice: it needs event logs):
//                1. verifyPath with enforceExpiry
//                2. continuity of registration (the reference RegistrationBoundary; Unknown fails closed)
//                3. liveness of every wrapped trustor on the path: does the name have a controller now?
//                4. record, for each .eth second-level name on the path, the expiry E that the BaseRegistrar returns at block B
//   execute()  the checks made in the transaction that executes (on-chain):
//                5. the registry's own evaluation (validateParticipantAddress)
//                6. for each recorded name: block.timestamp <= E + GRACE_PERIOD, or nameExpires still returns E (no registration since block B)
//                7. liveness again: the NameWrapper's ownerOf for each wrapped trustor on the path (not the terminal node) is not the zero address
//
// Every step can be switched off with a `skip` name. The tests switch one off at a time and check that the scenario aimed at that step is then wrongly accepted:
// a step that no scenario can distinguish from "off" would not be tested.
import {TrustRegistry} from "../ercs/contracts/TrustRegistry.sol";
import {ITrustRegistry, TrustLevel, ValidationParams, TrustPath} from "../ercs/contracts/ITrustRegistry.sol";
import {RegistrationBoundary} from "../ercs/tests/continuity/RegistrationBoundary.sol";

interface IBaseRegistrarRead { function nameExpires(uint256) external view returns (uint256); function GRACE_PERIOD() external view returns (uint256); }
interface INameWrapperRead { function ownerOf(uint256) external view returns (address); }
interface IEnsRead { function owner(bytes32) external view returns (address); }

library Coordinator8107 {
    address internal constant ENS = 0x00000000000C2E074eC69A0dFb2997BA6C7d2e1e;
    address internal constant NAME_WRAPPER = 0xD4416b13d2b3a9aBae7AcD5D6C2BbDBE25686401;
    address internal constant BASE_REGISTRAR = 0x57f1887a8BF19b14fC0dF6Fd9B2acc9Af147eA85;

    /// What the decision records for the execution: per path node, the BaseRegistrar token id and the expiry E read at block B (0 when the node is not a .eth second-level name).
    struct Record { uint256[] tokenId; uint256[] expiry; }

    function _skip(string memory skip, string memory step) private pure returns (bool) { return keccak256(bytes(skip)) == keccak256(bytes(step)); }

    function isWrapped(bytes32 node) internal view returns (bool) { return IEnsRead(ENS).owner(node) == NAME_WRAPPER; }

    function decide(
        TrustRegistry reg, TrustPath memory p, bool enforceExpiry,
        RegistrationBoundary.NameProof[] memory proofs, RegistrationBoundary.History memory h, string memory skip
    ) internal view returns (bool ok, string memory why, Record memory rec) {
        uint256 n = p.nodes.length;
        rec = Record(new uint256[](n), new uint256[](n));
        if (!_skip(skip, "verify") && !reg.verifyPath(p, ValidationParams({maxPathLength: 4, minEdgeTrust: TrustLevel.Full, scope: bytes32(0), enforceExpiry: enforceExpiry, requiredAnchors: new bytes32[](0)}))) {
            return (false, "verifyPath", rec);
        }
        if (!_skip(skip, "continuity")) {
            RegistrationBoundary.Result memory r = RegistrationBoundary.evaluate(ITrustRegistry(address(reg)), BASE_REGISTRAR, NAME_WRAPPER, p.nodes, bytes32(0), proofs, h, uint64(block.number));
            if (r.verdict != RegistrationBoundary.Verdict.Eligible) return (false, r.verdict == RegistrationBoundary.Verdict.Unknown ? "continuity: unknown (fails closed)" : "continuity: registered again", rec);
        }
        if (!_skip(skip, "liveness-decision")) {
            for (uint256 i = 0; i + 1 < n; i++) {
                if (isWrapped(p.nodes[i]) && INameWrapperRead(NAME_WRAPPER).ownerOf(uint256(p.nodes[i])) == address(0)) return (false, "liveness at decision", rec);
            }
        }
        for (uint256 i = 0; i < n; i++) {
            if (proofs[i].labels.length == 2) { // "label.eth": a second-level name
                rec.tokenId[i] = uint256(keccak256(bytes(proofs[i].labels[0])));
                rec.expiry[i] = IBaseRegistrarRead(BASE_REGISTRAR).nameExpires(rec.tokenId[i]);
            }
        }
        return (true, "", rec);
    }

    function execute(
        TrustRegistry reg, address coordinator, bytes32 coordinationType, address participant, TrustPath memory p, Record memory rec, string memory skip
    ) internal view returns (bool ok, string memory why) {
        if (!reg.validateParticipantAddress(coordinator, coordinationType, participant, p)) return (false, "registry evaluation");
        if (!_skip(skip, "deadline")) {
            uint256 grace = IBaseRegistrarRead(BASE_REGISTRAR).GRACE_PERIOD();
            for (uint256 i = 0; i < p.nodes.length; i++) {
                if (rec.expiry[i] == 0) continue;
                bool noRegistrationSinceB = block.timestamp <= rec.expiry[i] + grace || IBaseRegistrarRead(BASE_REGISTRAR).nameExpires(rec.tokenId[i]) == rec.expiry[i];
                if (!noRegistrationSinceB) return (false, "deadline: a registration may have happened since block B");
            }
        }
        if (!_skip(skip, "liveness-execution")) {
            for (uint256 i = 0; i + 1 < p.nodes.length; i++) {
                if (isWrapped(p.nodes[i]) && INameWrapperRead(NAME_WRAPPER).ownerOf(uint256(p.nodes[i])) == address(0)) return (false, "liveness at execution");
            }
        }
        return (true, "");
    }
}
