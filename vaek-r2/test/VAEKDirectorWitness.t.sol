// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity 0.8.24;

import {VAEKTypes} from "../src/VAEKTypes.sol";
import {VAEKKernel} from "../src/kernel/VAEKKernel.sol";
import {ResourceRegistry} from "../src/registries/ResourceRegistry.sol";
import {AdapterRegistry} from "../src/registries/AdapterRegistry.sol";
import {ERC20TransferAdapter} from "../src/adapters/ERC20TransferAdapter.sol";
import {BoundedSwapAdapter} from "../src/adapters/BoundedSwapAdapter.sol";
import {ServiceEscrowAdapter} from "../src/adapters/ServiceEscrowAdapter.sol";
import {ITypedSwapVenue} from "../src/interfaces/ITypedAdapters.sol";
import {TokenOps} from "../src/libraries/TokenOps.sol";
import {MockERC20} from "../src/mocks/MockERC20.sol";
import {MockSwapVenue} from "../src/mocks/MockSwapVenue.sol";

interface VmDirector {
    function prank(address) external;
}

interface IKernelCrossEffect {
    function executeSwapExactInput(bytes32 executionId) external;
}

/// @notice Venue consumes only half of the input, but reports the full amount.
/// The current adapter measures kernel outflow, not venue consumption, so the
/// unconsumed half remains trapped in the adapter while the receipt says full input.
contract UnderConsumeVenue is ITypedSwapVenue {
    function swapExactInput(address tokenIn, address tokenOut, uint128 amountIn, uint128 minOutput, address recipient)
        external
        returns (uint128 actualInput, uint128 actualOutput)
    {
        uint128 consumed = amountIn / 2;
        TokenOps.safeTransferFrom(tokenIn, msg.sender, address(this), consumed);
        TokenOps.safeTransfer(tokenOut, recipient, minOutput);
        return (amountIn, minOutput);
    }
}

/// @notice Token that attempts to enter a different effect path while the
/// outer transfer is executing. This is a positive witness for the global lock.
contract CrossEffectReentrantToken is MockERC20 {
    IKernelCrossEffect public kernel;
    bytes32 public nestedExecutionId;
    bool public armed;
    bool public nestedSucceeded;

    constructor() MockERC20("CrossEffect", 6) {}

    function arm(IKernelCrossEffect kernel_, bytes32 executionId_) external {
        kernel = kernel_;
        nestedExecutionId = executionId_;
        armed = true;
    }

    function transferFrom(address from, address to, uint256 amount) external override returns (bool) {
        if (armed) {
            armed = false;
            (nestedSucceeded,) =
                address(kernel).call(abi.encodeCall(IKernelCrossEffect.executeSwapExactInput, (nestedExecutionId)));
        }
        uint256 allowed = allowance[from][msg.sender];
        require(allowed >= amount, "allowance");
        allowance[from][msg.sender] = allowed - amount;
        _transfer(from, to, amount);
        return true;
    }
}

/// @notice Independent review witnesses. These tests intentionally PASS when
/// the described behavior exists. They are not proposed production tests.
contract VAEKDirectorWitnessTest {
    VmDirector private constant vm = VmDirector(address(uint160(uint256(keccak256("hevm cheat code")))));

    address private constant AGENT = address(0xA11CE);
    address private constant VERIFIER = address(0xBEEF);
    address private constant RECIPIENT = address(0xCAFE);
    address private constant ATTACKER = address(0xBAD);
    address private constant PROVIDER = address(0xD00D);
    address private constant EVALUATOR = address(0xE0A1);

    bytes32 private constant MANDATE = keccak256("director-mandate");
    bytes32 private constant POLICY = keccak256("director-policy");
    bytes32 private constant ASSET_IN = keccak256("director-asset-in");
    bytes32 private constant ASSET_OUT = keccak256("director-asset-out");
    bytes32 private constant RECIPIENT_ID = keccak256("director-recipient");
    bytes32 private constant PROVIDER_ID = keccak256("director-provider");
    bytes32 private constant EVALUATOR_ID = keccak256("director-evaluator");
    bytes32 private constant SERVICE_ID = keccak256("director-service");
    bytes32 private constant VENUE_ID = keccak256("director-venue");

    ResourceRegistry private resources;
    AdapterRegistry private adapters;
    VAEKKernel private kernel;
    ERC20TransferAdapter private transferAdapter;
    BoundedSwapAdapter private swapAdapter;
    ServiceEscrowAdapter private escrowAdapter;
    MockERC20 private tokenIn;
    MockERC20 private tokenOut;
    MockSwapVenue private venue;
    uint64 private nonce;

    function setUp() public {
        resources = new ResourceRegistry(address(this));
        adapters = new AdapterRegistry(address(this));
        kernel = new VAEKKernel(resources, adapters, VERIFIER);
        transferAdapter = new ERC20TransferAdapter(address(kernel));
        swapAdapter = new BoundedSwapAdapter(address(kernel));
        escrowAdapter = new ServiceEscrowAdapter(address(kernel));
        tokenIn = new MockERC20("DirectorIn", 6);
        tokenOut = new MockERC20("DirectorOut", 6);
        venue = new MockSwapVenue();

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

    /// CRITICAL WITNESS: terminal EXECUTED can be reset to VERIFIED by the
    /// verifier, allowing the same executionId to execute a second time.
    function test_WITNESS_ReverificationReopensExecutedEffect() public {
        bytes32 executionId = _submitTransfer(50);
        bytes32 authorizationHash = _authorization(executionId);
        _verify(executionId, authorizationHash);
        kernel.executeTransfer(executionId);

        _verify(executionId, authorizationHash);
        kernel.executeTransfer(executionId);

        assert(tokenIn.balanceOf(RECIPIENT) == 100);
        assert(kernel.spentOf(MANDATE) == 100);
    }

    /// HIGH WITNESS: an escalated swap can be rebound to the current global
    /// resource version after an ID remap without re-resolving identities or risk.
    function test_WITNESS_SwapApprovalRefreshesAfterRecipientRemap() public {
        bytes32 executionId = _submitSwap(700, 190, uint64(block.timestamp + 1 hours));

        resources.setResource(
            RECIPIENT_ID, ATTACKER, VAEKTypes.ResourceKind.COUNTERPARTY, VAEKTypes.RiskTier.CRITICAL, true
        );

        kernel.approveSwapAttenuation(executionId, 500, 190);
        bytes32 authorizationHash = _authorization(executionId);
        _verify(executionId, authorizationHash);
        kernel.executeSwapExactInput(executionId);

        assert(tokenOut.balanceOf(RECIPIENT) == 0);
        assert(tokenOut.balanceOf(ATTACKER) == 1_000);
    }

    /// HIGH/MEDIUM WITNESS: actualInput is kernel outflow, not venue
    /// consumption. A venue can leave residual input trapped in the adapter.
    function test_WITNESS_SwapReceiptCanHideResidualInputInAdapter() public {
        UnderConsumeVenue underConsume = new UnderConsumeVenue();
        tokenOut.mint(address(underConsume), 1_000);
        resources.setResource(
            VENUE_ID, address(underConsume), VAEKTypes.ResourceKind.VENUE, VAEKTypes.RiskTier.LOW, true
        );

        bytes32 executionId = _submitSwap(100, 100, uint64(block.timestamp + 1 hours));
        _verify(executionId, _authorization(executionId));
        kernel.executeSwapExactInput(executionId);

        VAEKTypes.Receipt memory receipt = kernel.getReceipt(executionId);
        assert(receipt.actualInput == 100);
        assert(tokenIn.balanceOf(address(swapAdapter)) == 50);
        assert(tokenIn.balanceOf(address(underConsume)) == 50);
        assert(tokenOut.balanceOf(RECIPIENT) == 100);
    }

    /// GOVERNANCE WITNESS: disabling the adapter prevents new kernel dispatch,
    /// but does not freeze an already-funded escrow's terminal payout.
    function test_WITNESS_RegistryDisableDoesNotPauseFundedEscrowSettlement() public {
        bytes32 executionId = _submitService(50);
        _verify(executionId, _authorization(executionId));
        kernel.executeServicePurchase(executionId);
        bytes32 jobId = kernel.getReceipt(executionId).resultId;

        adapters.disable(VAEKTypes.EffectType.BUY_SERVICE_ESCROW);
        vm.prank(PROVIDER);
        escrowAdapter.submitDelivery(jobId, keccak256("director-delivery"));
        vm.prank(EVALUATOR);
        escrowAdapter.evaluate(jobId, true);

        assert(tokenIn.balanceOf(PROVIDER) == 50);
    }

    /// POSITIVE WITNESS: the global lock blocks transfer -> swap nesting even
    /// though the existing candidate regression covers transfer -> transfer.
    function test_WITNESS_GlobalLockBlocksCrossEffectReentrancy() public {
        CrossEffectReentrantToken crossToken = new CrossEffectReentrantToken();
        resources.setResource(
            ASSET_IN, address(crossToken), VAEKTypes.ResourceKind.ASSET, VAEKTypes.RiskTier.LOW, true
        );
        crossToken.mint(address(kernel), 1_000);

        bytes32 nestedSwap = _submitSwap(100, 190, uint64(block.timestamp + 1 hours));
        _verify(nestedSwap, _authorization(nestedSwap));
        bytes32 outerTransfer = _submitTransfer(50);
        crossToken.arm(IKernelCrossEffect(address(kernel)), nestedSwap);

        kernel.executeTransfer(outerTransfer);

        assert(!crossToken.nestedSucceeded());
        assert(kernel.getReceipt(nestedSwap).receiptHash == bytes32(0));
        assert(crossToken.balanceOf(RECIPIENT) == 50);
    }

    function _submitTransfer(uint128 amount) private returns (bytes32 executionId) {
        VAEKTypes.EffectHeader memory h = _header();
        executionId = h.executionId;
        vm.prank(AGENT);
        kernel.submitTransfer(h, VAEKTypes.TransferRequest(ASSET_IN, RECIPIENT_ID, amount));
    }

    function _submitSwap(uint128 maxInput, uint128 minOutput, uint64 quoteValidUntil)
        private
        returns (bytes32 executionId)
    {
        VAEKTypes.EffectHeader memory h = _header();
        executionId = h.executionId;
        VAEKTypes.SwapExactInputRequest memory request = VAEKTypes.SwapExactInputRequest({
            assetInId: ASSET_IN,
            assetOutId: ASSET_OUT,
            venueId: VENUE_ID,
            recipientId: RECIPIENT_ID,
            maxInput: maxInput,
            minOutput: minOutput,
            quoteCommitment: keccak256("director-quote"),
            quoteValidUntil: quoteValidUntil
        });
        vm.prank(AGENT);
        kernel.submitSwapExactInput(h, request);
    }

    function _submitService(uint128 price) private returns (bytes32 executionId) {
        VAEKTypes.EffectHeader memory h = _header();
        executionId = h.executionId;
        VAEKTypes.ServicePurchaseRequest memory request = VAEKTypes.ServicePurchaseRequest({
            providerId: PROVIDER_ID,
            serviceId: SERVICE_ID,
            paymentAssetId: ASSET_IN,
            maxPrice: price,
            deliveryCommitment: keccak256("director-delivery"),
            serviceDeadline: uint64(block.timestamp + 1 days),
            evaluatorId: EVALUATOR_ID
        });
        vm.prank(AGENT);
        kernel.submitServicePurchase(h, request);
    }

    function _header() private returns (VAEKTypes.EffectHeader memory) {
        uint64 next = ++nonce;
        return VAEKTypes.EffectHeader({
            schemaVersion: 2,
            executionId: keccak256(abi.encode(address(this), next)),
            mandateId: MANDATE,
            nonce: next,
            validAfter: uint64(block.timestamp),
            deadline: uint64(block.timestamp + 2 days),
            observationHash: keccak256(abi.encode("director-observation", next)),
            modelCommitment: keccak256("director-model"),
            policyCommitment: POLICY,
            contextHash: keccak256("director-context")
        });
    }

    function _authorization(bytes32 executionId) private view returns (bytes32 authorizationHash) {
        (, authorizationHash,,,,,) = kernel.getAuthorization(executionId);
    }

    function _verify(bytes32 executionId, bytes32 authorizationHash) private {
        vm.prank(VERIFIER);
        kernel.recordVerification(
            executionId, authorizationHash, uint64(block.timestamp + 1 days), keccak256("director-method")
        );
    }
}
