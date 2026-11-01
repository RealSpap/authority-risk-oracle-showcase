// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.20;

// Two ENS names that resolve to the same address. Question: when the gatekeeper denies one of them at universal scope, does validateParticipantAddress still admit that address through the other?
// agent.eth (a1) and backup.eth (a2) both have the address record X. The gatekeeper G endorses both (two valid edges G > a1 and G > a2) and then denies a1 at universal scope.
// MUTANT=skipsecond: the scenario "G denies BOTH names" leaves out the second denial; its assertion (X refused) must then fail.
import "./Base8107.sol";

contract TwoAliasesTest is Base8107 {
    struct Aliases { bytes32 g; bytes32 a1; bytes32 a2; }

    function aliases() internal returns (Aliases memory s) {
        vm.recordLogs();
        s.g = registerName(name("gate"), G, 5 * YEAR); s.a1 = registerName(name("agent"), A, 5 * YEAR); s.a2 = registerName(name("backup"), M, 5 * YEAR); closeBlock();
        setAddr(s.a1, A, X); setAddr(s.a2, M, X);                       // both names resolve to X
        endorse(PK_G, s.g, s.a1); endorse(PK_G, s.g, s.a2); closeBlock();   // two valid paths from G
        openGate(s.g, false);
    }
    function byAddress(Aliases memory s, bool viaFirst) internal view returns (bool) { return reg.validateParticipantAddress(COORD, CTYPE, X, pathOf2(s.g, viaFirst ? s.a1 : s.a2)); }
    function byNode(Aliases memory s, bool viaFirst) internal view returns (bool) { bytes32 t = viaFirst ? s.a1 : s.a2; return reg.validateParticipantWithPath(COORD, CTYPE, t, pathOf2(s.g, t)); }
    function say(string memory what, Aliases memory s) internal view {
        console.log(string.concat("OBS|", what, "|mutant=", mutation(), "|address X via [G, agent.eth]=", yn(byAddress(s, true)), "|via [G, backup.eth]=", yn(byAddress(s, false)),
            "|node agent.eth=", yn(byNode(s, true)), "|node backup.eth=", yn(byNode(s, false))));
    }
    function deny(Aliases memory s, bytes32 node) internal { vm.prank(G); reg.setDenial(s.g, node, bytes32(0), bytes32("compromised")); }

    function testA0_no_denial() public {
        Aliases memory s = aliases(); say("A0 no denial", s);
        assertTrue(reg.resolveAgent(s.a1) == X && reg.resolveAgent(s.a2) == X, "both names resolve to X");
        assertTrue(byAddress(s, true) && byAddress(s, false), "positive control: X is admitted through each path");
        bytes32 other = registerName(name("other"), CHARLIE(), YEAR); closeBlock(); setAddr(other, CHARLIE(), X);
        assertFalse(reg.validateParticipantAddress(COORD, CTYPE, X, pathOf2(s.g, other)), "negative control: a name that resolves to X but that G never endorsed is refused");
    }
    function CHARLIE() internal pure returns (address) { return address(uint160(uint256(keccak256("t-other")))); }
    function testA1_deny_one_alias() public {
        Aliases memory s = aliases(); deny(s, s.a1); say("A1 G denies agent.eth", s);
        assertFalse(byAddress(s, true), "the path to the denied name is refused");
        assertFalse(byNode(s, true), "the denied node is refused");
        assertTrue(byAddress(s, false), "OBSERVATION: X is still admitted through [G, backup.eth], a path with no denied node");
    }
    function testA2_deny_both_aliases() public {
        Aliases memory s = aliases(); deny(s, s.a1);
        if (!mutated("skipsecond")) deny(s, s.a2);
        say("A2 G denies both names", s);
        assertFalse(byAddress(s, true) || byAddress(s, false), "if G denies BOTH names, X is refused through both paths");
    }
    function testA3_deny_then_clear() public {
        Aliases memory s = aliases(); deny(s, s.a1);
        assertFalse(byAddress(s, true), "denied");
        uint64 nonce = reg.getNonce(s.g); vm.prank(G); reg.clearDenial(s.g, s.a1, bytes32(0), nonce, bytes32("reviewed"));
        say("A3 denial cleared", s);
        assertTrue(byAddress(s, true), "control: clearing the denial makes the path valid again");
    }
}
