// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.20;

// S7: the case raised on the ERC-8107 thread (post of 2026-11-02 22:49Z) and tested in ethereum/ERCs PR #2101 as test_Wrapped2LDTrustorPastWrapperExpiry:
// a wrapped .eth second-level trustor T in the middle of the path is decided on IN ITS GRACE PERIOD (BaseRegistrar expiry E has passed, the NameWrapper still has a holder),
// then passes its NameWrapper expiry (E + GRACE) with nothing registered. nameExpires still returns E, so the deadline step is satisfied; the registry evaluation still accepts
// (it reads the controller of the terminal node only). Only the liveness check at execution refuses.
// Written here from that description, in this harness, not copied from the PR. Run with MUTANT=<step>: only `liveness-execution` must make S7 fail.
import "./CompleteCoordinator.t.sol";

contract Wrapped2LDGraceTest is CompleteCoordinatorTest {
    function testS7_wrapped_2LD_trustor_decided_in_grace_passes_wrapper_expiry() public {
        console.log(string.concat("OBS|fork|chainid=", vm.toString(block.chainid), "|block=", vm.toString(block.number), "|timestamp=", vm.toString(vm.getBlockTimestamp())));
        World memory w = world(true); TrustPath memory p = pathOf3(w.g, w.t, w.x);   // T = wrapped .eth 2LD, registered for one year
        vm.warp(w.e0 + 30 days);                                                     // in the grace period of the BaseRegistrar
        assertTrue(vm.getBlockTimestamp() > w.e0 && vm.getBlockTimestamp() <= w.e0 + GRACE, "T is in its grace period at the decision");
        assertTrue(INameWrapper(NAME_WRAPPER).ownerOf(uint256(w.t)) != address(0), "T still has a holder at the decision");
        (bool ok, string memory why, Coordinator8107.Record memory rec) = decide(p); say("S7 wrapped 2LD trustor decided in grace", "decision", ok, why);
        assertTrue(ok, "control: the decision accepts");
        vm.warp(w.e0 + GRACE + 1);
        assertTrue(INameWrapper(NAME_WRAPPER).ownerOf(uint256(w.t)) == address(0), "T has no holder: passed its NameWrapper expiry");
        assertEq(IBaseRegistrar(BASE_REGISTRAR).nameExpires(id(w.tl)), w.e0, "nothing was registered: nameExpires is unchanged");
        assertTrue(reg.validateParticipantAddress(COORD, CTYPE, X, p), "the registry evaluation still accepts at execution (terminal node only)");
        (bool ex, string memory why2) = execute(p, X, rec); say("S7 wrapped 2LD trustor decided in grace", "execution", ex, why2);
        assertFalse(ex, "the execution must refuse");
    }

    // S7b (anticipated question: does the path-aware registry check refuse where the address-only check accepts?): same setup as S7, then both registry evaluations are logged at execution time.
    function testS7b_path_aware_registry_check_at_execution() public {
        World memory w = world(true); TrustPath memory p = pathOf3(w.g, w.t, w.x);
        vm.warp(w.e0 + 30 days);
        (bool ok, , ) = decide(p); assertTrue(ok, "control: the decision accepts");
        vm.warp(w.e0 + GRACE + 1);
        assertTrue(INameWrapper(NAME_WRAPPER).ownerOf(uint256(w.t)) == address(0), "T has no holder");
        bool byAddress = reg.validateParticipantAddress(COORD, CTYPE, X, p);
        bool byPath = reg.validateParticipantWithPath(COORD, CTYPE, p.nodes[p.nodes.length - 1], p);
        console.log(string.concat("OBS|S7b|block=", vm.toString(block.number), "|validateParticipantAddress=", byAddress ? "accepts" : "refuses", "|validateParticipantWithPath=", byPath ? "accepts" : "refuses"));
    }

    // S7c (anticipated question: the boundary): decision at the last second of the BaseRegistrar grace period (E + GRACE), execution one second later.
    function testS7c_decision_at_last_second_of_grace() public {
        World memory w = world(true); TrustPath memory p = pathOf3(w.g, w.t, w.x);
        vm.warp(w.e0 + GRACE);
        address holder = INameWrapper(NAME_WRAPPER).ownerOf(uint256(w.t));
        (bool ok, string memory why, Coordinator8107.Record memory rec) = decide(p);
        console.log(string.concat("OBS|S7c|at E+GRACE|ownerOf nonzero=", holder != address(0) ? "yes" : "no", "|decision=", ok ? "accepts" : "refuses", "|", why));
        if (!ok) return;
        vm.warp(w.e0 + GRACE + 1);
        (bool ex, string memory why2) = execute(p, X, rec);
        console.log(string.concat("OBS|S7c|at E+GRACE+1|execution=", ex ? "accepts" : "refuses", "|", why2));
        assertFalse(ex, "the execution must refuse");
    }
}
