// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "../contracts/RefinementEffectKernel.sol";
import "../contracts/MockEffectEnvironment.sol";

interface Vm {
    function prank(address) external;
    function warp(uint256) external;
    function expectRevert(bytes4) external;
    function expectRevert(bytes calldata) external;
}

abstract contract RefinementEffectTestBase {
    Vm constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    address constant PRINCIPAL = address(0xA11CE);
    address constant AI = address(0xA10001);
    address constant VERIFIER = address(0xBEEF);
    address constant VENDOR = address(0xC0FFEE);
    address constant API_PROVIDER = address(0xCAFE);
    address constant ATTACKER = address(0xBAD);

    bytes32 constant CONTEXT = keccak256("context:r2");
    bytes32 constant OBSERVATION = keccak256("observation:r2");
    bytes32 constant MODEL = keccak256("model:r2");
    bytes32 constant POLICY = keccak256("policy:r2");
    bytes32 constant EVIDENCE = keccak256("evidence:r2");
    bytes32 constant SERVICE = keccak256("translation-api:v1");

    MockERC20 token;
    MockPurchaseAdapter adapter;
    RefinementEffectKernel kernel;
    bytes32 mandateId;

    function setUp() public {
        token = new MockERC20();
        adapter = new MockPurchaseAdapter();
        kernel = new RefinementEffectKernel(VERIFIER, address(adapter));
        token.mint(address(kernel), 1_000_000);
        mandateId = _createMandate(kernel, address(token), true, false, 100, 250, 80);
    }

    function _createMandate(
        RefinementEffectKernel k,
        address asset,
        bool allowRefinement,
        bool requireTransferVerification,
        uint128 maxPer,
        uint128 maxTotal,
        uint128 humanGate
    ) internal returns (bytes32 id) {
        address[] memory targets = new address[](2);
        targets[0] = VENDOR;
        targets[1] = API_PROVIDER;
        uint8 mask = k.effectBit(RefinementEffectKernel.EffectType.TRANSFER_ERC20)
            | k.effectBit(RefinementEffectKernel.EffectType.PURCHASE_SERVICE);
        vm.prank(PRINCIPAL);
        id = k.createMandate(
            AI,
            asset,
            maxPer,
            maxTotal,
            humanGate,
            uint64(block.timestamp),
            uint64(block.timestamp + 30 days),
            7,
            MODEL,
            POLICY,
            mask,
            allowRefinement,
            requireTransferVerification,
            targets
        );
    }

    function _submitTransfer(
        RefinementEffectKernel k,
        bytes32 id,
        bytes32 m,
        address target,
        address asset,
        uint128 amount,
        bool acceptRefinement
    ) internal returns (bytes32 requestHash) {
        vm.prank(AI);
        requestHash = k.submitTransfer(
            id,
            m,
            target,
            asset,
            amount,
            uint64(block.timestamp + 1 hours),
            acceptRefinement,
            CONTEXT,
            OBSERVATION,
            MODEL,
            POLICY,
            1
        );
    }

    function _submitPurchase(bytes32 id, uint128 amount, bool acceptRefinement) internal returns (bytes32 requestHash) {
        vm.prank(AI);
        requestHash = kernel.submitServicePurchase(
            id,
            mandateId,
            API_PROVIDER,
            address(token),
            amount,
            uint64(block.timestamp + 1 hours),
            acceptRefinement,
            SERVICE,
            CONTEXT,
            OBSERVATION,
            MODEL,
            POLICY,
            2
        );
    }

    function _verify(RefinementEffectKernel k, bytes32 id, bytes32 requestHash) internal {
        vm.prank(VERIFIER);
        k.recordVerification(
            id, requestHash, RefinementEffectKernel.Verdict.PASS, EVIDENCE, uint64(block.timestamp + 1 hours)
        );
    }

    function _approve(RefinementEffectKernel k, bytes32 id) internal {
        vm.prank(PRINCIPAL);
        k.approveHighRisk(id);
    }

    function _assertEq(uint256 a, uint256 b, string memory what) internal pure {
        require(a == b, what);
    }

    function _assertEq(bytes32 a, bytes32 b, string memory what) internal pure {
        require(a == b, what);
    }

    function _assertTrue(bool value, string memory what) internal pure {
        require(value, what);
    }
}
