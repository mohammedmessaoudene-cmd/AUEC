// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./RefinementEffectTestBase.sol";

contract RefinementEffectAdversarialTest is RefinementEffectTestBase {
    function test_ServicePurchaseOverchargeRollsBack() public {
        bytes32 id = keccak256("purchase-overcharge");
        bytes32 h = _submitPurchase(id, 20, false);
        _verify(kernel, id, h);
        adapter.configure(21, false, address(0), bytes32(0));
        vm.expectRevert(
            abi.encodeWithSelector(
                RefinementEffectKernel.PostconditionFailure.selector,
                bytes32("PURCHASE_CHARGE")
            )
        );
        kernel.execute(id);
        _assertEq(token.balanceOf(API_PROVIDER), 0, "provider rollback");
        _assertEq(kernel.spentOf(mandateId), 0, "spent rollback");
        _assertTrue(!kernel.isConsumed(id), "consumed rollback");
    }

    function test_AdapterFailureRollsBack() public {
        bytes32 id = keccak256("adapter-failure");
        bytes32 h = _submitPurchase(id, 20, false);
        _verify(kernel, id, h);
        adapter.configure(0, true, address(0), bytes32(0));
        vm.expectRevert(RefinementEffectKernel.AdapterExecutionFailure.selector);
        kernel.execute(id);
        _assertTrue(!kernel.isConsumed(id), "consumed rollback");
    }

    function test_AdapterReentryCannotExecuteSecondEffect() public {
        bytes32 purchaseId = keccak256("outer-purchase");
        bytes32 hp = _submitPurchase(purchaseId, 20, false);
        _verify(kernel, purchaseId, hp);
        bytes32 nestedId = keccak256("nested-transfer");
        _submitTransfer(kernel, nestedId, mandateId, VENDOR, address(token), 10, false);
        adapter.configure(20, false, address(kernel), nestedId);
        kernel.execute(purchaseId);
        _assertTrue(!adapter.reentrySucceeded(), "reentry succeeded");
        _assertTrue(!kernel.isConsumed(nestedId), "nested consumed");
        _assertEq(token.balanceOf(VENDOR), 0, "nested moved funds");
    }

    function test_FeeOnTransferTokenViolatesExactPostconditionAndRollsBack() public {
        MockFeeERC20 feeToken = new MockFeeERC20();
        MockPurchaseAdapter adapter2 = new MockPurchaseAdapter();
        RefinementEffectKernel k2 = new RefinementEffectKernel(VERIFIER, address(adapter2));
        feeToken.mint(address(k2), 1_000);
        bytes32 m2 = _createMandate(k2, address(feeToken), true, false, 100, 250, 80);
        bytes32 id = keccak256("fee-token");
        _submitTransfer(k2, id, m2, VENDOR, address(feeToken), 20, false);
        vm.expectRevert(
            abi.encodeWithSelector(
                RefinementEffectKernel.PostconditionFailure.selector,
                bytes32("BALANCE_DELTA")
            )
        );
        k2.execute(id);
        _assertEq(feeToken.balanceOf(VENDOR), 0, "fee transfer rollback");
        _assertEq(k2.spentOf(m2), 0, "spent rollback");
        _assertTrue(!k2.isConsumed(id), "consumed rollback");
    }

    function test_RevocationDominatesPriorVerification() public {
        bytes32 id = keccak256("revocation");
        bytes32 h = _submitPurchase(id, 20, false);
        _verify(kernel, id, h);
        vm.prank(PRINCIPAL);
        kernel.revokeMandate(mandateId);
        _assertEq(kernel.evaluate(id).reason, bytes32("REVOKED"), "revocation");
        vm.expectRevert(
            abi.encodeWithSelector(
                RefinementEffectKernel.EffectNotAuthorized.selector,
                bytes32("REVOKED")
            )
        );
        kernel.execute(id);
    }

    function test_StaleRequestIsBlockedAtEffectTime() public {
        bytes32 id = keccak256("stale");
        vm.prank(AI);
        kernel.submitTransfer(
            id, mandateId, VENDOR, address(token), 20, uint64(block.timestamp + 10), false,
            CONTEXT, OBSERVATION, MODEL, POLICY, 1
        );
        vm.warp(block.timestamp + 11);
        _assertEq(kernel.evaluate(id).reason, bytes32("REQUEST_STALE"), "stale");
    }

    function test_ReplayCannotExecuteTwice() public {
        bytes32 id = keccak256("replay");
        _submitTransfer(kernel, id, mandateId, VENDOR, address(token), 20, false);
        kernel.execute(id);
        vm.expectRevert(RefinementEffectKernel.AlreadyConsumed.selector);
        kernel.execute(id);
        _assertEq(token.balanceOf(VENDOR), 20, "replay funds");
    }

    function test_TotalBudgetRefinesToCurrentRemainingAuthority() public {
        for (uint256 i = 0; i < 2; ++i) {
            bytes32 id = keccak256(abi.encode("budget-seed", i));
            bytes32 h = _submitTransfer(kernel, id, mandateId, VENDOR, address(token), 90, false);
            _verify(kernel, id, h);
            _approve(kernel, id);
            kernel.execute(id);
        }
        bytes32 last = keccak256("budget-refine");
        bytes32 hl = _submitTransfer(kernel, last, mandateId, VENDOR, address(token), 100, true);
        _verify(kernel, last, hl);
        RefinementEffectKernel.Evaluation memory e = kernel.evaluate(last);
        _assertEq(uint256(e.decision), uint256(RefinementEffectKernel.Decision.ALLOW_REFINED), "refine");
        _assertEq(e.authorizedAmount, 70, "remaining");
        kernel.execute(last);
        _assertEq(kernel.spentOf(mandateId), 250, "total");
    }

    function test_BudgetExhaustionBlocks() public {
        bytes32 a = keccak256("exhaust-a");
        bytes32 ha = _submitTransfer(kernel, a, mandateId, VENDOR, address(token), 100, false);
        _verify(kernel, a, ha); _approve(kernel, a); kernel.execute(a);
        bytes32 b = keccak256("exhaust-b");
        bytes32 hb = _submitTransfer(kernel, b, mandateId, VENDOR, address(token), 100, false);
        _verify(kernel, b, hb); _approve(kernel, b); kernel.execute(b);
        bytes32 c = keccak256("exhaust-c");
        _submitTransfer(kernel, c, mandateId, VENDOR, address(token), 50, false);
        kernel.execute(c);
        bytes32 d = keccak256("exhaust-d");
        _submitTransfer(kernel, d, mandateId, VENDOR, address(token), 1, false);
        _assertEq(kernel.evaluate(d).reason, bytes32("BUDGET_EXHAUSTED"), "exhaustion");
    }
}
