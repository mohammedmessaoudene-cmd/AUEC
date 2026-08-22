// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./RefinementEffectTestBase.sol";

contract RefinementEffectCoreTest is RefinementEffectTestBase {
    function test_ExactTypedTransferExecutesAndReceipts() public {
        bytes32 id = keccak256("exact-transfer");
        _submitTransfer(kernel, id, mandateId, VENDOR, address(token), 20, false);
        RefinementEffectKernel.Evaluation memory e = kernel.evaluate(id);
        _assertEq(uint256(e.decision), uint256(RefinementEffectKernel.Decision.ALLOW_EXACT), "decision");
        _assertEq(e.authorizedAmount, 20, "authorized");
        bytes32 receipt = kernel.execute(id);
        _assertEq(token.balanceOf(VENDOR), 20, "vendor");
        _assertEq(kernel.spentOf(mandateId), 20, "spent");
        _assertTrue(kernel.isConsumed(id), "consumed");
        _assertEq(kernel.receiptHashOf(id), receipt, "receipt");
    }

    function test_ExplicitRefinementProducesAttenuatedExecution() public {
        bytes32 id = keccak256("refined-transfer");
        bytes32 h = _submitTransfer(kernel, id, mandateId, VENDOR, address(token), 120, true);
        _verify(kernel, id, h);
        _approve(kernel, id);
        RefinementEffectKernel.Evaluation memory e = kernel.evaluate(id);
        _assertEq(uint256(e.decision), uint256(RefinementEffectKernel.Decision.ALLOW_REFINED), "not refined");
        _assertEq(e.authorizedAmount, 100, "refined amount");
        kernel.execute(id);
        _assertEq(token.balanceOf(VENDOR), 100, "actual");
        _assertEq(kernel.spentOf(mandateId), 100, "spent");
    }

    function test_RefinementRequiresMandateAndRequestConsent() public {
        bytes32 id = keccak256("no-request-consent");
        _submitTransfer(kernel, id, mandateId, VENDOR, address(token), 120, false);
        RefinementEffectKernel.Evaluation memory e = kernel.evaluate(id);
        _assertEq(e.reason, bytes32("REFINEMENT_NOT_AUTHORIZED"), "request consent");

        MockPurchaseAdapter adapter2 = new MockPurchaseAdapter();
        RefinementEffectKernel k2 = new RefinementEffectKernel(VERIFIER, address(adapter2));
        token.mint(address(k2), 1_000);
        bytes32 m2 = _createMandate(k2, address(token), false, false, 100, 250, 80);
        bytes32 id2 = keccak256("no-mandate-consent");
        _submitTransfer(k2, id2, m2, VENDOR, address(token), 120, true);
        RefinementEffectKernel.Evaluation memory e2 = k2.evaluate(id2);
        _assertEq(e2.reason, bytes32("REFINEMENT_NOT_AUTHORIZED"), "mandate consent");
    }

    function test_TargetAssetModelAndPolicyAreFailClosed() public {
        bytes32 targetId = keccak256("bad-target");
        _submitTransfer(kernel, targetId, mandateId, ATTACKER, address(token), 20, false);
        _assertEq(kernel.evaluate(targetId).reason, bytes32("TARGET"), "target");

        MockERC20 other = new MockERC20();
        bytes32 assetId = keccak256("bad-asset");
        _submitTransfer(kernel, assetId, mandateId, VENDOR, address(other), 20, false);
        _assertEq(kernel.evaluate(assetId).reason, bytes32("ASSET"), "asset");

        bytes32 modelId = keccak256("bad-model");
        vm.prank(AI);
        kernel.submitTransfer(
            modelId, mandateId, VENDOR, address(token), 20, uint64(block.timestamp + 1 hours), false,
            CONTEXT, OBSERVATION, keccak256("wrong model"), POLICY, 3
        );
        _assertEq(kernel.evaluate(modelId).reason, bytes32("MODEL_COMMITMENT"), "model");

        bytes32 policyId = keccak256("bad-policy");
        vm.prank(AI);
        kernel.submitTransfer(
            policyId, mandateId, VENDOR, address(token), 20, uint64(block.timestamp + 1 hours), false,
            CONTEXT, OBSERVATION, MODEL, keccak256("wrong policy"), 4
        );
        _assertEq(kernel.evaluate(policyId).reason, bytes32("POLICY_COMMITMENT"), "policy");
    }

    function test_UnauthorizedAgentCannotSubmit() public {
        vm.prank(ATTACKER);
        vm.expectRevert(RefinementEffectKernel.Unauthorized.selector);
        kernel.submitTransfer(
            keccak256("unauthorized"), mandateId, VENDOR, address(token), 1,
            uint64(block.timestamp + 1 hours), false, CONTEXT, OBSERVATION, MODEL, POLICY, 1
        );
    }

    function test_MediumAndHighRiskRequireProportionateControls() public {
        bytes32 medium = keccak256("medium");
        bytes32 hm = _submitTransfer(kernel, medium, mandateId, VENDOR, address(token), 60, false);
        _assertEq(kernel.evaluate(medium).reason, bytes32("VERIFICATION"), "medium verification");
        _verify(kernel, medium, hm);
        _assertEq(uint256(kernel.evaluate(medium).decision), uint256(RefinementEffectKernel.Decision.ALLOW_EXACT), "medium allow");

        bytes32 high = keccak256("high");
        bytes32 hh = _submitTransfer(kernel, high, mandateId, VENDOR, address(token), 95, false);
        _verify(kernel, high, hh);
        _assertEq(uint256(kernel.evaluate(high).decision), uint256(RefinementEffectKernel.Decision.ESCALATE), "high escalate");
        _approve(kernel, high);
        _assertEq(uint256(kernel.evaluate(high).decision), uint256(RefinementEffectKernel.Decision.ALLOW_EXACT), "high allow");
    }

    function test_VerificationIsBoundToExactRequestHash() public {
        bytes32 id = keccak256("verification-binding");
        _submitPurchase(id, 20, false);
        vm.prank(VERIFIER);
        vm.expectRevert(RefinementEffectKernel.InvalidRequest.selector);
        kernel.recordVerification(
            id, keccak256("wrong"), RefinementEffectKernel.Verdict.PASS, EVIDENCE,
            uint64(block.timestamp + 1 hours)
        );
    }

    function test_ServicePurchaseUnderchargeIsValidRefinementOfAuthorization() public {
        bytes32 id = keccak256("purchase-undercharge");
        bytes32 h = _submitPurchase(id, 20, false);
        _verify(kernel, id, h);
        adapter.configure(17, false, address(0), bytes32(0));
        kernel.execute(id);
        _assertEq(token.balanceOf(API_PROVIDER), 17, "provider charge");
        _assertEq(kernel.spentOf(mandateId), 17, "spent actual");
    }
}
