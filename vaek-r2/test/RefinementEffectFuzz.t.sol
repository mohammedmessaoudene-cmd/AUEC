// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./RefinementEffectTestBase.sol";

contract RefinementEffectFuzzTest is RefinementEffectTestBase {
    function testFuzz_LowRiskExactTransfersStayExact(uint128 raw) public {
        uint128 amount = uint128(uint256(raw) % 50 + 1);
        bytes32 id = keccak256(abi.encode("fuzz-low", raw));
        _submitTransfer(kernel, id, mandateId, VENDOR, address(token), amount, false);
        RefinementEffectKernel.Evaluation memory e = kernel.evaluate(id);
        _assertEq(uint256(e.decision), uint256(RefinementEffectKernel.Decision.ALLOW_EXACT), "low decision");
        _assertEq(e.authorizedAmount, amount, "low amount");
    }

    function testFuzz_HighRiskRequiresEvidenceAndHuman(uint128 raw) public {
        uint128 amount = uint128(uint256(raw) % 10 + 91);
        bytes32 id = keccak256(abi.encode("fuzz-high", raw));
        bytes32 h = _submitTransfer(kernel, id, mandateId, VENDOR, address(token), amount, false);
        _assertEq(kernel.evaluate(id).reason, bytes32("VERIFICATION"), "evidence");
        _verify(kernel, id, h);
        _assertEq(uint256(kernel.evaluate(id).decision), uint256(RefinementEffectKernel.Decision.ESCALATE), "human");
        _approve(kernel, id);
        _assertEq(uint256(kernel.evaluate(id).decision), uint256(RefinementEffectKernel.Decision.ALLOW_EXACT), "allow");
    }

    function testFuzz_OverCapacityRequestsRefineOnlyToCapacity(uint128 raw) public {
        uint128 amount = uint128(uint256(raw) % 10_000 + 101);
        bytes32 id = keccak256(abi.encode("fuzz-refine", raw));
        bytes32 h = _submitTransfer(kernel, id, mandateId, VENDOR, address(token), amount, true);
        _verify(kernel, id, h);
        _approve(kernel, id);
        RefinementEffectKernel.Evaluation memory e = kernel.evaluate(id);
        _assertEq(uint256(e.decision), uint256(RefinementEffectKernel.Decision.ALLOW_REFINED), "refine decision");
        _assertEq(e.authorizedAmount, 100, "capacity");
    }

    function testFuzz_UnlistedTargetsNeverAcquireAuthority(address rawTarget, uint128 rawAmount) public {
        address target = rawTarget;
        if (target == address(0) || target == VENDOR || target == API_PROVIDER) target = ATTACKER;
        uint128 amount = uint128(uint256(rawAmount) % 100 + 1);
        bytes32 id = keccak256(abi.encode("fuzz-target", target, amount));
        _submitTransfer(kernel, id, mandateId, target, address(token), amount, true);
        _assertEq(kernel.evaluate(id).reason, bytes32("TARGET"), "target escaped");
    }
}
