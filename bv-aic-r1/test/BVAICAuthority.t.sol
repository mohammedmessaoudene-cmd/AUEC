// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "../contracts/BVAICAuthority.sol";
import "../contracts/MockERC20.sol";

interface Vm {
    function prank(address) external;
    function warp(uint256) external;
    function assume(bool) external;
    function expectRevert(bytes4) external;
    function expectRevert(bytes calldata) external;
}

contract BVAICAuthorityTest {
    Vm constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    address constant PRINCIPAL = address(0xA11CE);
    address constant AI = address(0xA10001);
    address constant VERIFIER = address(0xBEEF);
    address constant VENDOR = address(0xC0FFEE);
    address constant ATTACKER = address(0xBAD);

    BVAICAuthority auth;
    MockERC20 token;
    bytes32 mandateId;

    bytes32 constant OBS = keccak256("observation:v1");
    bytes32 constant MODEL = keccak256("model:v1");
    bytes32 constant POLICY = keccak256("policy:v1");
    bytes32 constant EVIDENCE = keccak256("evidence:v1");

    function setUp() public {
        token = new MockERC20();
        auth = new BVAICAuthority(VERIFIER);
        token.mint(address(auth), 1_000_000);
        mandateId = _createMandate(auth, address(token), 100, 250, 50, true, VENDOR);
    }

    function _createMandate(
        BVAICAuthority authority,
        address asset,
        uint128 maxPer,
        uint128 maxTotal,
        uint128 humanGate,
        bool requireVerification,
        address target
    ) internal returns (bytes32 id) {
        address[] memory targets = new address[](1);
        targets[0] = target;
        vm.prank(PRINCIPAL);
        id = authority.createMandate(
            AI,
            asset,
            maxPer,
            maxTotal,
            humanGate,
            uint64(block.timestamp),
            uint64(block.timestamp + 7 days),
            requireVerification,
            targets
        );
    }

    function _submit(bytes32 execId, address target, address asset, uint128 amount, uint64 deadline)
        internal returns (bytes32 decisionHash)
    {
        vm.prank(AI);
        decisionHash = auth.submitDecision(execId, mandateId, target, asset, amount, deadline, OBS, MODEL, POLICY);
    }

    function _verify(bytes32 execId, bytes32 decisionHash, uint64 validUntil) internal {
        vm.prank(VERIFIER);
        auth.recordVerification(execId, decisionHash, BVAICAuthority.Verdict.PASS, EVIDENCE, validUntil);
    }

    function _assertEq(uint256 a, uint256 b, string memory what) internal pure {
        require(a == b, what);
    }

    function _assertTrue(bool v, string memory what) internal pure { require(v, what); }

    function test_NormalVerifiedTransfer() public {
        bytes32 id = keccak256("normal");
        uint64 deadline = uint64(block.timestamp + 1 hours);
        bytes32 h = _submit(id, VENDOR, address(token), 20, deadline);
        _verify(id, h, deadline);
        (BVAICAuthority.AuthorityResult r,) = auth.evaluate(id);
        _assertEq(uint256(r), uint256(BVAICAuthority.AuthorityResult.ALLOW), "not ALLOW");
        auth.execute(id);
        _assertEq(token.balanceOf(VENDOR), 20, "vendor balance");
        _assertTrue(auth.isConsumed(id), "not consumed");
        _assertEq(auth.spentOf(mandateId), 20, "spent");
    }

    function test_UnauthorizedCannotSubmit() public {
        vm.prank(ATTACKER);
        vm.expectRevert(BVAICAuthority.Unauthorized.selector);
        auth.submitDecision(keccak256("x"), mandateId, VENDOR, address(token), 1, uint64(block.timestamp + 1 hours), OBS, MODEL, POLICY);
    }

    function test_UnlistedTargetBlocked() public {
        bytes32 id = keccak256("bad-target");
        uint64 deadline = uint64(block.timestamp + 1 hours);
        bytes32 h = _submit(id, ATTACKER, address(token), 20, deadline);
        _verify(id, h, deadline);
        (BVAICAuthority.AuthorityResult r,) = auth.evaluate(id);
        _assertEq(uint256(r), uint256(BVAICAuthority.AuthorityResult.BLOCK), "target escaped");
    }

    function test_WrongAssetBlocked() public {
        MockERC20 other = new MockERC20();
        bytes32 id = keccak256("wrong-asset");
        uint64 deadline = uint64(block.timestamp + 1 hours);
        bytes32 h = _submit(id, VENDOR, address(other), 20, deadline);
        _verify(id, h, deadline);
        (BVAICAuthority.AuthorityResult r,) = auth.evaluate(id);
        _assertEq(uint256(r), uint256(BVAICAuthority.AuthorityResult.BLOCK), "asset escaped");
    }

    function test_PerEffectOverflowBlocked() public {
        bytes32 id = keccak256("over-per-effect");
        uint64 deadline = uint64(block.timestamp + 1 hours);
        bytes32 h = _submit(id, VENDOR, address(token), 101, deadline);
        _verify(id, h, deadline);
        (BVAICAuthority.AuthorityResult r,) = auth.evaluate(id);
        _assertEq(uint256(r), uint256(BVAICAuthority.AuthorityResult.BLOCK), "per effect escaped");
    }

    function test_ZeroAmountBlocked() public {
        bytes32 id = keccak256("zero");
        uint64 deadline = uint64(block.timestamp + 1 hours);
        bytes32 h = _submit(id, VENDOR, address(token), 0, deadline);
        _verify(id, h, deadline);
        (BVAICAuthority.AuthorityResult r,) = auth.evaluate(id);
        _assertEq(uint256(r), uint256(BVAICAuthority.AuthorityResult.BLOCK), "zero escaped");
    }

    function test_StaleDecisionBlocked() public {
        bytes32 id = keccak256("stale");
        uint64 deadline = uint64(block.timestamp + 10);
        bytes32 h = _submit(id, VENDOR, address(token), 20, deadline);
        _verify(id, h, deadline);
        vm.warp(block.timestamp + 11);
        (BVAICAuthority.AuthorityResult r,) = auth.evaluate(id);
        _assertEq(uint256(r), uint256(BVAICAuthority.AuthorityResult.BLOCK), "stale escaped");
    }

    function test_MissingVerificationBlocked() public {
        bytes32 id = keccak256("no-verification");
        _submit(id, VENDOR, address(token), 20, uint64(block.timestamp + 1 hours));
        (BVAICAuthority.AuthorityResult r,) = auth.evaluate(id);
        _assertEq(uint256(r), uint256(BVAICAuthority.AuthorityResult.BLOCK), "verification bypass");
    }

    function test_VerificationBoundToDecisionHash() public {
        bytes32 id = keccak256("binding");
        uint64 deadline = uint64(block.timestamp + 1 hours);
        _submit(id, VENDOR, address(token), 20, deadline);
        vm.prank(VERIFIER);
        vm.expectRevert(BVAICAuthority.InvalidDecision.selector);
        auth.recordVerification(id, keccak256("wrong hash"), BVAICAuthority.Verdict.PASS, EVIDENCE, deadline);
    }

    function test_HighRiskEscalatesThenHumanAllows() public {
        bytes32 id = keccak256("human");
        uint64 deadline = uint64(block.timestamp + 1 hours);
        bytes32 h = _submit(id, VENDOR, address(token), 80, deadline);
        _verify(id, h, deadline);
        (BVAICAuthority.AuthorityResult beforeApproval,) = auth.evaluate(id);
        _assertEq(uint256(beforeApproval), uint256(BVAICAuthority.AuthorityResult.ESCALATE), "no escalation");
        vm.prank(PRINCIPAL);
        auth.approveHighRisk(id);
        (BVAICAuthority.AuthorityResult afterApproval,) = auth.evaluate(id);
        _assertEq(uint256(afterApproval), uint256(BVAICAuthority.AuthorityResult.ALLOW), "human approval ignored");
    }

    function test_RevocationAfterVerificationStillBlocks() public {
        bytes32 id = keccak256("revoked");
        uint64 deadline = uint64(block.timestamp + 1 hours);
        bytes32 h = _submit(id, VENDOR, address(token), 20, deadline);
        _verify(id, h, deadline);
        vm.prank(PRINCIPAL);
        auth.revokeMandate(mandateId);
        (BVAICAuthority.AuthorityResult r,) = auth.evaluate(id);
        _assertEq(uint256(r), uint256(BVAICAuthority.AuthorityResult.BLOCK), "revocation bypass");
    }

    function test_ReplayCannotExecuteTwice() public {
        bytes32 id = keccak256("replay");
        uint64 deadline = uint64(block.timestamp + 1 hours);
        bytes32 h = _submit(id, VENDOR, address(token), 20, deadline);
        _verify(id, h, deadline);
        auth.execute(id);
        vm.expectRevert(BVAICAuthority.AlreadyConsumed.selector);
        auth.execute(id);
        _assertEq(token.balanceOf(VENDOR), 20, "replay moved funds");
    }

    function test_TotalBudgetCannotBeExceeded() public {
        for (uint256 i = 0; i < 2; i++) {
            bytes32 id = keccak256(abi.encode("budget", i));
            uint64 deadline = uint64(block.timestamp + 1 hours);
            bytes32 h = _submit(id, VENDOR, address(token), 90, deadline);
            _verify(id, h, deadline);
            vm.prank(PRINCIPAL);
            auth.approveHighRisk(id);
            auth.execute(id);
        }
        bytes32 last = keccak256("budget-last");
        uint64 dl = uint64(block.timestamp + 1 hours);
        bytes32 hh = _submit(last, VENDOR, address(token), 80, dl);
        _verify(last, hh, dl);
        vm.prank(PRINCIPAL);
        auth.approveHighRisk(last);
        (BVAICAuthority.AuthorityResult r,) = auth.evaluate(last);
        _assertEq(uint256(r), uint256(BVAICAuthority.AuthorityResult.BLOCK), "aggregate budget escaped");
        _assertEq(auth.spentOf(mandateId), 180, "spent mismatch");
    }

    function test_CompromisedVerifierCannotBypassTargetOrBudget() public {
        bytes32 id1 = keccak256("compromised-verifier-target");
        uint64 dl = uint64(block.timestamp + 1 hours);
        bytes32 h1 = _submit(id1, ATTACKER, address(token), 20, dl);
        _verify(id1, h1, dl); // verifier deliberately says PASS
        (BVAICAuthority.AuthorityResult r1,) = auth.evaluate(id1);
        _assertEq(uint256(r1), uint256(BVAICAuthority.AuthorityResult.BLOCK), "verifier bypassed target");

        bytes32 id2 = keccak256("compromised-verifier-budget");
        bytes32 h2 = _submit(id2, VENDOR, address(token), 200, dl);
        _verify(id2, h2, dl);
        (BVAICAuthority.AuthorityResult r2,) = auth.evaluate(id2);
        _assertEq(uint256(r2), uint256(BVAICAuthority.AuthorityResult.BLOCK), "verifier bypassed budget");
    }

    function test_FailedTokenTransferRollsBackAuthorityState() public {
        MockFalseERC20 bad = new MockFalseERC20();
        BVAICAuthority a = new BVAICAuthority(VERIFIER);
        bad.mint(address(a), 1_000);
        bytes32 m = _createMandate(a, address(bad), 100, 250, 0, true, VENDOR);
        bytes32 id = keccak256("false-token");
        uint64 dl = uint64(block.timestamp + 1 hours);
        vm.prank(AI);
        bytes32 h = a.submitDecision(id, m, VENDOR, address(bad), 20, dl, OBS, MODEL, POLICY);
        vm.prank(VERIFIER);
        a.recordVerification(id, h, BVAICAuthority.Verdict.PASS, EVIDENCE, dl);
        vm.expectRevert(BVAICAuthority.TransferFailed.selector);
        a.execute(id);
        _assertTrue(!a.isConsumed(id), "consumed not rolled back");
        _assertEq(a.spentOf(m), 0, "spent not rolled back");
    }

    function test_ReentrantTokenCannotTriggerSecondEffect() public {
        MockReentrantERC20 evil = new MockReentrantERC20();
        BVAICAuthority a = new BVAICAuthority(VERIFIER);
        evil.mint(address(a), 1_000);
        bytes32 m = _createMandate(a, address(evil), 100, 250, 0, true, VENDOR);
        uint64 dl = uint64(block.timestamp + 1 hours);

        bytes32 id1 = keccak256("reentry-1");
        bytes32 id2 = keccak256("reentry-2");
        vm.prank(AI);
        bytes32 h1 = a.submitDecision(id1, m, VENDOR, address(evil), 20, dl, OBS, MODEL, POLICY);
        vm.prank(AI);
        bytes32 h2 = a.submitDecision(id2, m, VENDOR, address(evil), 30, dl, OBS, MODEL, POLICY);
        vm.prank(VERIFIER);
        a.recordVerification(id1, h1, BVAICAuthority.Verdict.PASS, EVIDENCE, dl);
        vm.prank(VERIFIER);
        a.recordVerification(id2, h2, BVAICAuthority.Verdict.PASS, EVIDENCE, dl);
        evil.configureAttack(address(a), id2);

        a.execute(id1);
        _assertTrue(!evil.reentrySucceeded(), "reentry succeeded");
        _assertTrue(a.isConsumed(id1), "outer not consumed");
        _assertTrue(!a.isConsumed(id2), "nested consumed");
        _assertEq(a.spentOf(m), 20, "nested altered spent");
    }

    function testFuzz_AllowedLowRiskAmountsAreAllowed(uint128 amount) public {
        vm.assume(amount > 0 && amount <= 50);
        bytes32 id = keccak256(abi.encode("fuzz-low", amount));
        uint64 dl = uint64(block.timestamp + 1 hours);
        bytes32 h = _submit(id, VENDOR, address(token), amount, dl);
        _verify(id, h, dl);
        (BVAICAuthority.AuthorityResult r,) = auth.evaluate(id);
        _assertEq(uint256(r), uint256(BVAICAuthority.AuthorityResult.ALLOW), "valid fuzz blocked");
    }

    function testFuzz_HighRiskAmountsEscalate(uint128 amount) public {
        amount = uint128((uint256(amount) % 50) + 51);
        bytes32 id = keccak256(abi.encode("fuzz-high", amount));
        uint64 dl = uint64(block.timestamp + 1 hours);
        bytes32 h = _submit(id, VENDOR, address(token), amount, dl);
        _verify(id, h, dl);
        (BVAICAuthority.AuthorityResult r,) = auth.evaluate(id);
        _assertEq(uint256(r), uint256(BVAICAuthority.AuthorityResult.ESCALATE), "high risk not escalated");
    }

    function testFuzz_ArbitraryUnlistedTargetsBlocked(address target, uint128 amount) public {
        vm.assume(target != VENDOR && target != address(0));
        vm.assume(amount > 0 && amount <= 100);
        bytes32 id = keccak256(abi.encode("fuzz-target", target, amount));
        uint64 dl = uint64(block.timestamp + 1 hours);
        bytes32 h = _submit(id, target, address(token), amount, dl);
        _verify(id, h, dl);
        (BVAICAuthority.AuthorityResult r,) = auth.evaluate(id);
        _assertEq(uint256(r), uint256(BVAICAuthority.AuthorityResult.BLOCK), "random target escaped");
    }

    function testFuzz_AmountsAbovePerEffectAlwaysBlocked(uint128 amount) public {
        vm.assume(amount > 100);
        bytes32 id = keccak256(abi.encode("fuzz-over", amount));
        uint64 dl = uint64(block.timestamp + 1 hours);
        bytes32 h = _submit(id, VENDOR, address(token), amount, dl);
        _verify(id, h, dl);
        (BVAICAuthority.AuthorityResult r,) = auth.evaluate(id);
        _assertEq(uint256(r), uint256(BVAICAuthority.AuthorityResult.BLOCK), "over-budget fuzz escaped");
    }
}
