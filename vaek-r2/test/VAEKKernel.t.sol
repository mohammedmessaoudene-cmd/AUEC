// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity 0.8.24;

import {VAEKTypes} from "../src/VAEKTypes.sol";
import {VAEKKernel} from "../src/kernel/VAEKKernel.sol";
import {ResourceRegistry} from "../src/registries/ResourceRegistry.sol";
import {AdapterRegistry} from "../src/registries/AdapterRegistry.sol";
import {ERC20TransferAdapter} from "../src/adapters/ERC20TransferAdapter.sol";
import {BoundedSwapAdapter} from "../src/adapters/BoundedSwapAdapter.sol";
import {ServiceEscrowAdapter} from "../src/adapters/ServiceEscrowAdapter.sol";
import {
    MockERC20,
    MockFeeToken,
    MockFalseToken,
    MockNoReturnToken,
    MockReentrantToken,
    IKernelExecute
} from "../src/mocks/MockERC20.sol";
import {MockSwapVenue} from "../src/mocks/MockSwapVenue.sol";
import {ReferenceModel} from "../reference/ReferenceModel.sol";

interface Vm {
    function prank(address) external;
    function warp(uint256) external;
    function expectRevert() external;
}

contract VAEKKernelTest {
    Vm private constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    address private constant AGENT = address(0xA11CE);
    address private constant VERIFIER = address(0xBEEF);
    address private constant RECIPIENT = address(0xCAFE);
    address private constant PROVIDER = address(0xD00D);
    address private constant EVALUATOR = address(0xE0A1);

    bytes32 private constant MANDATE = keccak256("mandate");
    bytes32 private constant POLICY = keccak256("policy-v1");
    bytes32 private constant ASSET_IN = keccak256("asset-in");
    bytes32 private constant ASSET_OUT = keccak256("asset-out");
    bytes32 private constant RECIPIENT_ID = keccak256("recipient");
    bytes32 private constant PROVIDER_ID = keccak256("provider");
    bytes32 private constant EVALUATOR_ID = keccak256("evaluator");
    bytes32 private constant SERVICE_ID = keccak256("service");
    bytes32 private constant VENUE_ID = keccak256("venue");

    ResourceRegistry private resources;
    AdapterRegistry private adapters;
    VAEKKernel private kernel;
    ERC20TransferAdapter private transferAdapter;
    BoundedSwapAdapter private swapAdapter;
    ServiceEscrowAdapter private escrowAdapter;
    MockERC20 private tokenIn;
    MockERC20 private tokenOut;
    MockSwapVenue private venue;
    ReferenceModel private referenceModel;
    uint64 private nonce;

    function setUp() public {
        resources = new ResourceRegistry(address(this));
        adapters = new AdapterRegistry(address(this));
        kernel = new VAEKKernel(resources, adapters, VERIFIER);
        transferAdapter = new ERC20TransferAdapter(address(kernel));
        swapAdapter = new BoundedSwapAdapter(address(kernel));
        escrowAdapter = new ServiceEscrowAdapter(address(kernel));
        tokenIn = new MockERC20("Input", 6);
        tokenOut = new MockERC20("Output", 6);
        venue = new MockSwapVenue();
        referenceModel = new ReferenceModel();

        adapters.setAdapter(VAEKTypes.EffectType.TRANSFER_ERC20, address(transferAdapter));
        adapters.setAdapter(VAEKTypes.EffectType.SWAP_EXACT_INPUT, address(swapAdapter));
        adapters.setAdapter(VAEKTypes.EffectType.BUY_SERVICE_ESCROW, address(escrowAdapter));

        resources.setResource(ASSET_IN, address(tokenIn), VAEKTypes.ResourceKind.ASSET, VAEKTypes.RiskTier.LOW, true);
        resources.setResource(ASSET_OUT, address(tokenOut), VAEKTypes.ResourceKind.ASSET, VAEKTypes.RiskTier.LOW, true);
        resources.setResource(
            RECIPIENT_ID, RECIPIENT, VAEKTypes.ResourceKind.COUNTERPARTY, VAEKTypes.RiskTier.LOW, true
        );
        resources.setResource(PROVIDER_ID, PROVIDER, VAEKTypes.ResourceKind.COUNTERPARTY, VAEKTypes.RiskTier.LOW, true);
        resources.setResource(EVALUATOR_ID, EVALUATOR, VAEKTypes.ResourceKind.EVALUATOR, VAEKTypes.RiskTier.LOW, true);
        resources.setResource(SERVICE_ID, address(0x5151), VAEKTypes.ResourceKind.SERVICE, VAEKTypes.RiskTier.LOW, true);
        resources.setResource(VENUE_ID, address(venue), VAEKTypes.ResourceKind.VENUE, VAEKTypes.RiskTier.LOW, true);

        kernel.createMandate(
            MANDATE,
            AGENT,
            POLICY,
            7,
            500,
            500,
            500,
            5_000,
            100,
            1_000,
            5_000,
            uint64(block.timestamp),
            uint64(block.timestamp + 30 days),
            VAEKTypes.RiskTier.MEDIUM
        );
        tokenIn.mint(address(kernel), 100_000);
        tokenOut.mint(address(venue), 100_000);
    }

    function test_INV001_NormalLowRiskTransferCreatesBoundReceipt() public {
        bytes32 executionId = _submitTransfer(MANDATE, 50, ASSET_IN, RECIPIENT_ID);
        kernel.executeTransfer(executionId);
        assert(tokenIn.balanceOf(RECIPIENT) == 50);
        assert(tokenIn.allowance(address(kernel), address(transferAdapter)) == 0);
        VAEKTypes.Receipt memory receipt = kernel.getReceipt(executionId);
        assert(receipt.receiptHash != bytes32(0));
        assert(receipt.requestedHash == receipt.authorizedHash == false);
        assert(receipt.actualInput == 50 && receipt.actualOutput == 50);
    }

    function test_INV010_TransferAttenuationNeverWidens() public {
        bytes32 executionId = _submitTransfer(MANDATE, 700, ASSET_IN, RECIPIENT_ID);
        (bytes32 requestedHash, bytes32 authHash, bytes32 witnessHash,, VAEKTypes.EffectState state, uint128 limit,) =
            kernel.getAuthorization(executionId);
        assert(requestedHash != authHash);
        assert(witnessHash != bytes32(0));
        assert(limit == 500);
        assert(state == VAEKTypes.EffectState.AUTHORIZED_ATTENUATED);
        _verify(executionId, authHash);
        kernel.executeTransfer(executionId);
        assert(tokenIn.balanceOf(RECIPIENT) == 500);
    }

    function test_INV020_RevocationAfterVerificationBlocksAndRollsBackBudget() public {
        bytes32 executionId = _submitTransfer(MANDATE, 200, ASSET_IN, RECIPIENT_ID);
        _verify(executionId, _auth(executionId));
        kernel.revokeMandate(MANDATE);
        vm.expectRevert();
        kernel.executeTransfer(executionId);
        assert(kernel.spentOf(MANDATE) == 0);
        assert(kernel.getReceipt(executionId).receiptHash == bytes32(0));
    }

    function test_INV030_ReplayCannotExecuteTwice() public {
        bytes32 executionId = _submitTransfer(MANDATE, 50, ASSET_IN, RECIPIENT_ID);
        kernel.executeTransfer(executionId);
        vm.expectRevert();
        kernel.executeTransfer(executionId);
        assert(kernel.spentOf(MANDATE) == 50);
    }

    function test_INV032_FalseReturnTokenRollsBackBudgetAndReceipt() public {
        MockFalseToken falseToken = new MockFalseToken();
        resources.setResource(ASSET_IN, address(falseToken), VAEKTypes.ResourceKind.ASSET, VAEKTypes.RiskTier.LOW, true);
        falseToken.mint(address(kernel), 100);
        bytes32 executionId = _submitTransfer(MANDATE, 50, ASSET_IN, RECIPIENT_ID);
        vm.expectRevert();
        kernel.executeTransfer(executionId);
        assert(kernel.spentOf(MANDATE) == 0);
        assert(kernel.getReceipt(executionId).receiptHash == bytes32(0));
    }

    function test_NoReturnTokenIsSupportedAndMeasured() public {
        MockNoReturnToken noReturnToken = new MockNoReturnToken();
        resources.setResource(
            ASSET_IN, address(noReturnToken), VAEKTypes.ResourceKind.ASSET, VAEKTypes.RiskTier.LOW, true
        );
        noReturnToken.mint(address(kernel), 100);
        bytes32 executionId = _submitTransfer(MANDATE, 50, ASSET_IN, RECIPIENT_ID);
        kernel.executeTransfer(executionId);
        assert(noReturnToken.balanceOf(RECIPIENT) == 50);
        assert(kernel.getReceipt(executionId).actualOutput == 50);
    }

    function test_INV031_ReentrantTokenCannotExecuteNestedEffect() public {
        MockReentrantToken reentrant = new MockReentrantToken();
        resources.setResource(ASSET_IN, address(reentrant), VAEKTypes.ResourceKind.ASSET, VAEKTypes.RiskTier.LOW, true);
        reentrant.mint(address(kernel), 1_000);
        bytes32 nested = _submitTransfer(MANDATE, 40, ASSET_IN, RECIPIENT_ID);
        bytes32 outer = _submitTransfer(MANDATE, 50, ASSET_IN, RECIPIENT_ID);
        reentrant.arm(IKernelExecute(address(kernel)), nested);
        kernel.executeTransfer(outer);
        assert(!reentrant.nestedSucceeded());
        assert(reentrant.balanceOf(RECIPIENT) == 50);
        assert(kernel.spentOf(MANDATE) == 50);
        kernel.executeTransfer(nested);
        assert(reentrant.balanceOf(RECIPIENT) == 90);
    }

    function test_INV044_FeeTokenReceiptUsesMeasuredActual() public {
        MockFeeToken feeToken = new MockFeeToken(100);
        resources.setResource(ASSET_IN, address(feeToken), VAEKTypes.ResourceKind.ASSET, VAEKTypes.RiskTier.LOW, true);
        feeToken.mint(address(kernel), 1_000);
        bytes32 executionId = _submitTransfer(MANDATE, 100, ASSET_IN, RECIPIENT_ID);
        _verify(executionId, _auth(executionId));
        kernel.executeTransfer(executionId);
        VAEKTypes.Receipt memory receipt = kernel.getReceipt(executionId);
        assert(receipt.actualInput == 100);
        assert(receipt.actualOutput == 99);
        assert(feeToken.balanceOf(RECIPIENT) == 99);
    }

    function test_INV052_ResourceVersionChangeInvalidatesPendingAuthorization() public {
        bytes32 executionId = _submitTransfer(MANDATE, 50, ASSET_IN, RECIPIENT_ID);
        resources.setResource(SERVICE_ID, address(0x6161), VAEKTypes.ResourceKind.SERVICE, VAEKTypes.RiskTier.LOW, true);
        vm.expectRevert();
        kernel.executeTransfer(executionId);
    }

    function test_INV034_AdapterVersionChangeInvalidatesPendingAuthorization() public {
        bytes32 executionId = _submitTransfer(MANDATE, 50, ASSET_IN, RECIPIENT_ID);
        ERC20TransferAdapter replacement = new ERC20TransferAdapter(address(kernel));
        adapters.scheduleAdapter(VAEKTypes.EffectType.TRANSFER_ERC20, address(replacement));
        vm.warp(block.timestamp + 1 hours);
        adapters.activateAdapter(VAEKTypes.EffectType.TRANSFER_ERC20);
        vm.expectRevert();
        kernel.executeTransfer(executionId);
    }

    function test_AdapterReplacementCannotActivateBeforeTimelock() public {
        ERC20TransferAdapter replacement = new ERC20TransferAdapter(address(kernel));
        adapters.scheduleAdapter(VAEKTypes.EffectType.TRANSFER_ERC20, address(replacement));
        vm.expectRevert();
        adapters.activateAdapter(VAEKTypes.EffectType.TRANSFER_ERC20);
    }

    function test_SwapExactInputMeasuresBoundsAndClearsApproval() public {
        bytes32 executionId = _submitSwap(100, 190, uint64(block.timestamp + 1 hours));
        _verify(executionId, _auth(executionId));
        kernel.executeSwapExactInput(executionId);
        assert(tokenIn.balanceOf(address(kernel)) == 99_900);
        assert(tokenOut.balanceOf(RECIPIENT) == 200);
        assert(tokenIn.allowance(address(kernel), address(swapAdapter)) == 0);
        VAEKTypes.Receipt memory receipt = kernel.getReceipt(executionId);
        assert(receipt.actualInput == 100 && receipt.actualOutput == 200);
    }

    function test_MaliciousVenueFalseActualRevertsAtomically() public {
        venue.setLieAboutOutput(true);
        bytes32 executionId = _submitSwap(100, 190, uint64(block.timestamp + 1 hours));
        _verify(executionId, _auth(executionId));
        vm.expectRevert();
        kernel.executeSwapExactInput(executionId);
        assert(kernel.spentOf(MANDATE) == 0);
        assert(tokenOut.balanceOf(RECIPIENT) == 0);
    }

    function test_StaleQuoteBlocksAtExecution() public {
        bytes32 executionId = _submitSwap(100, 190, uint64(block.timestamp + 10));
        _verify(executionId, _auth(executionId));
        vm.warp(block.timestamp + 11);
        vm.expectRevert();
        kernel.executeSwapExactInput(executionId);
    }

    function test_SwapAttenuationRequiresPrincipalAndStricterMinimum() public {
        bytes32 executionId = _submitSwap(700, 190, uint64(block.timestamp + 1 hours));
        (,,,, VAEKTypes.EffectState state,,) = kernel.getAuthorization(executionId);
        assert(state == VAEKTypes.EffectState.ESCALATED);
        vm.prank(AGENT);
        vm.expectRevert();
        kernel.approveSwapAttenuation(executionId, 500, 190);
        vm.expectRevert();
        kernel.approveSwapAttenuation(executionId, 500, 189);
        kernel.approveSwapAttenuation(executionId, 500, 190);
        _verify(executionId, _auth(executionId));
        kernel.executeSwapExactInput(executionId);
        assert(tokenOut.balanceOf(RECIPIENT) == 1_000);
    }

    function test_ServicePurchaseFundsTypedEscrowWithoutProviderCallback() public {
        bytes32 executionId = _submitService(50);
        _verify(executionId, _auth(executionId));
        kernel.executeServicePurchase(executionId);
        VAEKTypes.Receipt memory receipt = kernel.getReceipt(executionId);
        assert(receipt.resultId != bytes32(0));
        assert(tokenIn.balanceOf(address(escrowAdapter)) == 50);
        vm.prank(PROVIDER);
        escrowAdapter.submitDelivery(receipt.resultId, keccak256("delivery"));
        vm.prank(EVALUATOR);
        escrowAdapter.evaluate(receipt.resultId, true);
        assert(tokenIn.balanceOf(PROVIDER) == 50);
    }

    function test_ServiceRejectsUnknownProvider() public {
        VAEKTypes.EffectHeader memory h = _header(MANDATE);
        VAEKTypes.ServicePurchaseRequest memory request = VAEKTypes.ServicePurchaseRequest({
            providerId: keccak256("unknown"),
            serviceId: SERVICE_ID,
            paymentAssetId: ASSET_IN,
            maxPrice: 50,
            deliveryCommitment: keccak256("delivery"),
            serviceDeadline: uint64(block.timestamp + 1 days),
            evaluatorId: EVALUATOR_ID
        });
        vm.prank(AGENT);
        vm.expectRevert();
        kernel.submitServicePurchase(h, request);
    }

    function test_INV026_ModelConcernCanRaiseButNeverLowerRisk() public view {
        VAEKTypes.RiskTier baseline = kernel.previewRisk(
            MANDATE,
            VAEKTypes.EffectType.TRANSFER_ERC20,
            50,
            VAEKTypes.RiskTier.LOW,
            VAEKTypes.RiskTier.LOW,
            VAEKTypes.RiskTier.LOW,
            VAEKTypes.RiskTier.LOW
        );
        VAEKTypes.RiskTier raised = kernel.previewRisk(
            MANDATE,
            VAEKTypes.EffectType.TRANSFER_ERC20,
            50,
            VAEKTypes.RiskTier.LOW,
            VAEKTypes.RiskTier.LOW,
            VAEKTypes.RiskTier.LOW,
            VAEKTypes.RiskTier.CRITICAL
        );
        assert(baseline == VAEKTypes.RiskTier.LOW);
        assert(raised == VAEKTypes.RiskTier.CRITICAL);
    }

    function test_HighRiskNeedsExactHumanApproval() public {
        bytes32 highMandate = keccak256("high-mandate");
        _createWideMandate(highMandate);
        bytes32 executionId = _submitTransfer(highMandate, 2_000, ASSET_IN, RECIPIENT_ID);
        bytes32 authHash = _auth(executionId);
        _verify(executionId, authHash);
        vm.expectRevert();
        kernel.executeTransfer(executionId);
        kernel.approveHighRisk(executionId, authHash);
        kernel.executeTransfer(executionId);
        assert(tokenIn.balanceOf(RECIPIENT) == 2_000);
    }

    function test_CriticalHumanApprovalRequiresDelay() public {
        bytes32 highMandate = keccak256("critical-mandate");
        _createWideMandate(highMandate);
        bytes32 executionId = _submitTransfer(highMandate, 6_000, ASSET_IN, RECIPIENT_ID);
        bytes32 authHash = _auth(executionId);
        _verify(executionId, authHash);
        kernel.approveHighRisk(executionId, authHash);
        vm.expectRevert();
        kernel.executeTransfer(executionId);
        vm.warp(block.timestamp + 1 hours);
        kernel.executeTransfer(executionId);
    }

    function testFuzz_INV010_AuthorizedTransferNeverExceedsRequest(uint128 rawAmount) public {
        uint128 amount = uint128((uint256(rawAmount) % 1_000) + 1);
        bytes32 executionId = _submitTransfer(MANDATE, amount, ASSET_IN, RECIPIENT_ID);
        (,,,,, uint128 authorized,) = kernel.getAuthorization(executionId);
        uint128 expected = referenceModel.authorizeTransfer(amount, 500, 5_000);
        assert(authorized == expected);
        assert(authorized > 0 && authorized <= amount && authorized <= 500);
    }

    function testFuzz_LowRiskTransferExecutesWithinBudget(uint96 rawAmount) public {
        uint128 amount = uint128((uint256(rawAmount) % 99) + 1);
        bytes32 executionId = _submitTransfer(MANDATE, amount, ASSET_IN, RECIPIENT_ID);
        kernel.executeTransfer(executionId);
        assert(kernel.spentOf(MANDATE) == amount);
        assert(tokenIn.balanceOf(RECIPIENT) == amount);
    }

    function testFuzz_INV026_ConcernMonotonic(uint8 rawConcern) public view {
        VAEKTypes.RiskTier concern = VAEKTypes.RiskTier(rawConcern % 4);
        VAEKTypes.RiskTier risk = kernel.previewRisk(
            MANDATE,
            VAEKTypes.EffectType.SWAP_EXACT_INPUT,
            1,
            VAEKTypes.RiskTier.LOW,
            VAEKTypes.RiskTier.LOW,
            VAEKTypes.RiskTier.LOW,
            concern
        );
        assert(uint8(risk) >= uint8(VAEKTypes.RiskTier.MEDIUM));
        assert(uint8(risk) >= uint8(concern));
    }

    function test_INV045_IndependentReceiptVerifierGoldenVector() public pure {
        VAEKTypes.Receipt memory receipt;
        receipt.executionId = bytes32(uint256(0x1111111111111111111111111111111111111111111111111111111111111111));
        receipt.mandateId = bytes32(uint256(0x2222222222222222222222222222222222222222222222222222222222222222));
        receipt.effectType = VAEKTypes.EffectType.TRANSFER_ERC20;
        receipt.requestedHash = bytes32(uint256(0x3333333333333333333333333333333333333333333333333333333333333333));
        receipt.authorizedHash = bytes32(uint256(0x4444444444444444444444444444444444444444444444444444444444444444));
        receipt.executedHash = bytes32(uint256(0x5555555555555555555555555555555555555555555555555555555555555555));
        receipt.attenuationWitnessHash =
            bytes32(uint256(0x6666666666666666666666666666666666666666666666666666666666666666));
        receipt.policyHash = bytes32(uint256(0x7777777777777777777777777777777777777777777777777777777777777777));
        receipt.resourceRegistryVersion = 8;
        receipt.adapterAddress = address(0x2222222222222222222222222222222222222222);
        receipt.adapterVersion = 1;
        receipt.adapterCodeHash = bytes32(uint256(0x8888888888888888888888888888888888888888888888888888888888888888));
        receipt.riskTier = VAEKTypes.RiskTier.LOW;
        receipt.requestedAt = 1_787_440_000;
        receipt.authorizedAt = 1_787_440_000;
        receipt.executedAt = 1_787_440_060;
        receipt.blockNumber = 77;
        receipt.actualInput = 50;
        receipt.actualOutput = 50;
        bytes32 actual = keccak256(
            abi.encode(
                keccak256("VAEK/RECEIPT/R2"),
                uint256(31337),
                address(0x1111111111111111111111111111111111111111),
                receipt
            )
        );
        assert(actual == 0xc46a24e90343c37e36740d80a1e67b0fa733a207f6b2acd42dce0d1a5cd11340);
    }

    function _submitTransfer(bytes32 mandateId, uint128 amount, bytes32 assetId, bytes32 recipientId)
        private
        returns (bytes32 executionId)
    {
        VAEKTypes.EffectHeader memory h = _header(mandateId);
        executionId = h.executionId;
        vm.prank(AGENT);
        kernel.submitTransfer(h, VAEKTypes.TransferRequest(assetId, recipientId, amount));
    }

    function _submitSwap(uint128 maxInput, uint128 minOutput, uint64 quoteValidUntil)
        private
        returns (bytes32 executionId)
    {
        VAEKTypes.EffectHeader memory h = _header(MANDATE);
        executionId = h.executionId;
        VAEKTypes.SwapExactInputRequest memory request = VAEKTypes.SwapExactInputRequest({
            assetInId: ASSET_IN,
            assetOutId: ASSET_OUT,
            venueId: VENUE_ID,
            recipientId: RECIPIENT_ID,
            maxInput: maxInput,
            minOutput: minOutput,
            quoteCommitment: keccak256("quote"),
            quoteValidUntil: quoteValidUntil
        });
        vm.prank(AGENT);
        kernel.submitSwapExactInput(h, request);
    }

    function _submitService(uint128 maxPrice) private returns (bytes32 executionId) {
        VAEKTypes.EffectHeader memory h = _header(MANDATE);
        executionId = h.executionId;
        VAEKTypes.ServicePurchaseRequest memory request = VAEKTypes.ServicePurchaseRequest({
            providerId: PROVIDER_ID,
            serviceId: SERVICE_ID,
            paymentAssetId: ASSET_IN,
            maxPrice: maxPrice,
            deliveryCommitment: keccak256("delivery"),
            serviceDeadline: uint64(block.timestamp + 1 days),
            evaluatorId: EVALUATOR_ID
        });
        vm.prank(AGENT);
        kernel.submitServicePurchase(h, request);
    }

    function _header(bytes32 mandateId) private returns (VAEKTypes.EffectHeader memory) {
        uint64 next = ++nonce;
        return VAEKTypes.EffectHeader({
            schemaVersion: 2,
            executionId: keccak256(abi.encode(address(this), next)),
            mandateId: mandateId,
            nonce: next,
            validAfter: uint64(block.timestamp),
            deadline: uint64(block.timestamp + 2 days),
            observationHash: keccak256("observation"),
            modelCommitment: keccak256("model"),
            policyCommitment: POLICY,
            contextHash: keccak256("context")
        });
    }

    function _auth(bytes32 executionId) private view returns (bytes32 authHash) {
        (, authHash,,,,,) = kernel.getAuthorization(executionId);
    }

    function _verify(bytes32 executionId, bytes32 authHash) private {
        vm.prank(VERIFIER);
        kernel.recordVerification(executionId, authHash, uint64(block.timestamp + 1 days), keccak256("method-a"));
    }

    function _createWideMandate(bytes32 mandateId) private {
        kernel.createMandate(
            mandateId,
            AGENT,
            POLICY,
            7,
            8_000,
            8_000,
            8_000,
            10_000,
            100,
            1_000,
            5_000,
            uint64(block.timestamp),
            uint64(block.timestamp + 30 days),
            VAEKTypes.RiskTier.MEDIUM
        );
    }
}
