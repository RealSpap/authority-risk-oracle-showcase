// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.20;

// Scenarios for the complete coordinator of Coordinator8107.sol. Each scenario is aimed at ONE step. Run with MUTANT=<step> to switch that step off:
// the scenario aimed at it must then fail (the coordinator wrongly accepts), and the others must still pass.
//   S0 expired edge                                         -> verify              (decision refuses)
//   S1 nothing happens                                      -> none (control)      (decision and execution accept)
//   S2 a name on the path is registered again before the decision -> continuity    (decision refuses)
//   S3 a name on the path is registered again after the decision, in the executing block -> deadline    (execution refuses)
//   S4 a name on the path is renewed in its grace period after the decision -> none (control)           (execution accepts)
//   S5 a wrapped trustor in the middle of the path loses its controller between the decision and the execution (the case added to the ERC by PR #2098)
//                                                           -> liveness-execution  (execution refuses)
//   S6 a wrapped trustor has no controller at the decision  -> liveness-decision   (decision refuses)
import "./Base8107.sol";
import {Coordinator8107} from "./Coordinator8107.sol";

contract CompleteCoordinatorTest is Base8107 {
    struct World { bytes32 g; bytes32 t; bytes32 x; string tl; uint256 e0; }

    // G (gate) > T (middle, registered for one year) > X (agent, resolves to X). T is optionally wrapped.
    function world(bool wrapT) internal returns (World memory w) {
        vm.recordLogs();
        string memory gl = name("gate"); w.tl = name("mid"); string memory xl = name("agent");
        w.g = registerName(gl, G, 5 * YEAR); closeBlock();
        w.t = registerName(w.tl, A, YEAR); closeBlock();
        w.x = registerName(xl, X, 5 * YEAR); closeBlock();
        if (wrapT) { wrapName(w.tl, A); closeBlock(); }
        setAddr(w.x, X, X);
        w.e0 = IBaseRegistrar(BASE_REGISTRAR).nameExpires(id(w.tl));
        endorse(PK_G, w.g, w.t); closeBlock();
        endorse(PK_A, w.t, w.x); closeBlock();
        openGate(w.g, true);
    }
    function decide(TrustPath memory p) internal view returns (bool ok, string memory why, Coordinator8107.Record memory rec) {
        return Coordinator8107.decide(reg, p, true, nameProofs(p.nodes), history(), mutation());
    }
    function execute(TrustPath memory p, address participant, Coordinator8107.Record memory rec) internal view returns (bool ok, string memory why) {
        return Coordinator8107.execute(reg, COORD, CTYPE, participant, p, rec, mutation());
    }
    function say(string memory scenario, string memory stage, bool ok, string memory why) internal view {
        console.log(string.concat("OBS|", scenario, "|mutant=", mutation(), "|", stage, "=", ok ? "accepts" : "refuses", ok ? "" : string.concat(" (", why, ")")));
    }
    function controllerRegisters(string memory label, address who) internal { // a BaseRegistrar controller registers a lapsed name (the real controller does the same after the premium)
        vm.prank(CONTROLLER); IBaseRegistrar(BASE_REGISTRAR).register(id(label), who, YEAR);
    }

    function testS0_expired_edge() public {
        World memory w = world(false);
        // an edge with an end date: G endorses T until 30 days from now, then the date passes
        TrustAttestation memory a = attestation(w.g, w.t, uint64(vm.getBlockTimestamp() + 30 days), reg.getNonce(w.g) + 1);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(PK_G, reg.hashAttestation(a)); reg.setTrust(a, abi.encodePacked(r, s, v)); closeBlock();
        TrustPath memory p = pathOf3(w.g, w.t, w.x);
        (bool ok0,,) = decide(p); assertTrue(ok0, "control: the path is accepted before the end date");
        vm.warp(vm.getBlockTimestamp() + 31 days);
        (bool ok, string memory why,) = decide(p); say("S0 expired edge", "decision", ok, why);
        assertFalse(ok, "the decision must refuse an edge past its end date");
    }
    function testS1_nothing_happens() public {
        World memory w = world(false); TrustPath memory p = pathOf3(w.g, w.t, w.x);
        (bool ok, string memory why, Coordinator8107.Record memory rec) = decide(p); say("S1 nothing happens", "decision", ok, why);
        assertTrue(ok, "control: the decision accepts");
        vm.warp(vm.getBlockTimestamp() + 1 hours);
        (bool ex, string memory why2) = execute(p, X, rec); say("S1 nothing happens", "execution", ex, why2);
        assertTrue(ex, "control: the execution accepts");
        bytes32 stranger = registerName(name("stranger"), M, YEAR); closeBlock(); setAddr(stranger, M, X);
        assertFalse(reg.validateParticipantAddress(COORD, CTYPE, X, pathOf2(w.g, stranger)), "negative control: a name G never endorsed is refused");
    }
    function testS2_registered_again_before_decision() public {
        World memory w = world(false); TrustPath memory p = pathOf3(w.g, w.t, w.x);
        vm.warp(w.e0 + GRACE + 1); controllerRegisters(w.tl, M); closeBlock();
        assertTrue(reg.verifyPath(p, ValidationParams({maxPathLength: 4, minEdgeTrust: TrustLevel.Full, scope: bytes32(0), enforceExpiry: true, requiredAnchors: new bytes32[](0)})), "the registry alone still accepts the path (this is why the coordinator checks continuity)");
        (bool ok, string memory why,) = decide(p); say("S2 registered again before the decision", "decision", ok, why);
        assertFalse(ok, "the decision must refuse a path whose middle name was registered again after the endorsement");
    }
    function testS3_registered_again_after_decision() public {
        World memory w = world(false); TrustPath memory p = pathOf3(w.g, w.t, w.x);
        (bool ok, string memory why, Coordinator8107.Record memory rec) = decide(p); say("S3 registered again after the decision", "decision", ok, why);
        assertTrue(ok, "control: the decision accepts");
        vm.warp(w.e0 + GRACE + 1); controllerRegisters(w.tl, M); // in the executing block, before the executing transaction
        assertTrue(reg.validateParticipantAddress(COORD, CTYPE, X, p), "the registry evaluation still accepts at execution");
        (bool ex, string memory why2) = execute(p, X, rec); say("S3 registered again after the decision", "execution", ex, why2);
        assertFalse(ex, "the execution must refuse");
    }
    function testS4_renewed_in_grace_after_decision() public {
        World memory w = world(false); TrustPath memory p = pathOf3(w.g, w.t, w.x);
        (bool ok,, Coordinator8107.Record memory rec) = decide(p); assertTrue(ok, "control: the decision accepts");
        vm.warp(w.e0 + 10 days); vm.prank(CONTROLLER); IBaseRegistrar(BASE_REGISTRAR).renew(id(w.tl), YEAR);
        (bool ex, string memory why) = execute(p, X, rec); say("S4 renewed in grace after the decision", "execution", ex, why);
        assertTrue(ex, "control: a renewal is not a registration, the execution accepts");
    }
    function testS5_wrapped_middle_trustor_loses_control() public {
        vm.recordLogs();
        bytes32 g = registerName(name("gate"), G, 5 * YEAR); string memory pl = name("parent"); bytes32 pn = registerName(pl, A, 5 * YEAR); bytes32 c = registerName(name("agent"), M, 5 * YEAR); closeBlock();
        wrapName(pl, A); closeBlock(); vm.prank(A); INameWrapper(NAME_WRAPPER).setFuses(pn, 1);          // CANNOT_UNWRAP: the parent can emancipate subnames
        uint64 xexp = uint64(vm.getBlockTimestamp()) + 90 days;
        vm.prank(A); bytes32 xn = INameWrapper(NAME_WRAPPER).setSubnodeRecord(pn, "x", H, RESOLVER, 0, 65536, xexp); // PARENT_CANNOT_CONTROL: emancipated
        labelOf[xn] = "x"; parentOf[xn] = pn; closeBlock();
        setAddr(c, M, M);
        endorse(PK_G, g, xn); endorse(PK_H, xn, c); closeBlock();
        openGate(g, true); TrustPath memory p = pathOf3(g, xn, c);
        (bool ok, string memory why, Coordinator8107.Record memory rec) = decide(p); say("S5 wrapped middle trustor loses control", "decision", ok, why);
        assertTrue(ok, "control: the decision accepts, the emancipated subname has a holder");
        vm.warp(xexp + 1);
        assertTrue(INameWrapper(NAME_WRAPPER).ownerOf(uint256(xn)) == address(0), "the subname passed its NameWrapper expiry: no holder");
        assertTrue(reg.validateParticipantAddress(COORD, CTYPE, M, p), "the registry evaluation still accepts at execution (PR #2098: it reads the controller of the terminal node only)");
        (bool ex, string memory why2) = execute(p, M, rec); say("S5 wrapped middle trustor loses control", "execution", ex, why2);
        assertFalse(ex, "the execution must refuse");
    }
    function testS6_wrapped_trustor_without_controller_at_decision() public {
        World memory w = world(true); TrustPath memory p = pathOf3(w.g, w.t, w.x);
        vm.warp(w.e0 + GRACE + 1);   // the NameWrapper expiry of a wrapped second-level name is the registrar expiry plus the grace period: nobody controls T, nobody registered it again
        assertTrue(INameWrapper(NAME_WRAPPER).ownerOf(uint256(w.t)) == address(0), "T has no controller");
        (bool ok, string memory why,) = decide(p); say("S6 wrapped trustor without controller at decision", "decision", ok, why);
        assertFalse(ok, "the decision must refuse");
    }
}
