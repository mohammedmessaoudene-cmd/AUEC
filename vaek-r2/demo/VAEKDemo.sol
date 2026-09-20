// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity 0.8.24;

import {VAEKTypes} from "../src/VAEKTypes.sol";
import {VAEKKernel} from "../src/kernel/VAEKKernel.sol";
import {ResourceRegistry} from "../src/registries/ResourceRegistry.sol";
import {AdapterRegistry} from "../src/registries/AdapterRegistry.sol";
import {ERC20TransferAdapter} from "../src/adapters/ERC20TransferAdapter.sol";
import {BoundedSwapAdapter} from "../src/adapters/BoundedSwapAdapter.sol";
import {ServiceEscrowAdapter} from "../src/adapters/ServiceEscrowAdapter.sol";
import {MockERC20} from "../src/mocks/MockERC20.sol";
import {MockSwapVenue} from "../src/mocks/MockSwapVenue.sol";

/// @notice Local-Anvil-only lifecycle harness. All roles are collapsed for deterministic demonstration.
contract VAEKDemo {
    bytes32 private constant MANDATE = keccak256("demo-mandate");
    bytes32 private constant POLICY = keccak256("demo-policy");
    bytes32 private constant ASSET_IN = keccak256("demo-asset-in");
    bytes32 private constant ASSET_OUT = keccak256("demo-asset-out");
    bytes32 private constant RECIPIENT_ID = keccak256("demo-recipient");
    bytes32 private constant PROVIDER_ID = keccak256("demo-provider");
    bytes32 private constant EVALUATOR_ID = keccak256("demo-evaluator");
    bytes32 private constant SERVICE_ID = keccak256("demo-service");
    bytes32 private constant VENUE_ID = keccak256("demo-venue");

    VAEKKernel public immutable kernel;
    MockERC20 public immutable tokenIn;
    MockERC20 public immutable tokenOut;
    MockSwapVenue public immutable venue;
    ServiceEscrowAdapter public immutable escrow;
    address public immutable recipient = address(0xCAFE);
    address public immutable provider = address(0xD00D);
    address public immutable evaluator = address(0xE0A1);
    bool public completed;
    bool public blockedObserved;
    uint64 private nonce;

    constructor() {
        ResourceRegistry resources = new ResourceRegistry(address(this));
        AdapterRegistry adapters = new AdapterRegistry(address(this));
        kernel = new VAEKKernel(resources, adapters, address(this));
        ERC20TransferAdapter transfer = new ERC20TransferAdapter(address(kernel));
        BoundedSwapAdapter swap = new BoundedSwapAdapter(address(kernel));
        escrow = new ServiceEscrowAdapter(address(kernel));
        tokenIn = new MockERC20("DemoInput", 6);
        tokenOut = new MockERC20("DemoOutput", 6);
        venue = new MockSwapVenue();
        adapters.setAdapter(VAEKTypes.EffectType.TRANSFER_ERC20, address(transfer));
        adapters.setAdapter(VAEKTypes.EffectType.SWAP_EXACT_INPUT, address(swap));
        adapters.setAdapter(VAEKTypes.EffectType.BUY_SERVICE_ESCROW, address(escrow));
        resources.setResource(ASSET_IN, address(tokenIn), VAEKTypes.ResourceKind.ASSET, VAEKTypes.RiskTier.LOW, true);
        resources.setResource(ASSET_OUT, address(tokenOut), VAEKTypes.ResourceKind.ASSET, VAEKTypes.RiskTier.LOW, true);
        resources.setResource(
            RECIPIENT_ID, recipient, VAEKTypes.ResourceKind.COUNTERPARTY, VAEKTypes.RiskTier.LOW, true
        );
        resources.setResource(PROVIDER_ID, provider, VAEKTypes.ResourceKind.COUNTERPARTY, VAEKTypes.RiskTier.LOW, true);
        resources.setResource(EVALUATOR_ID, evaluator, VAEKTypes.ResourceKind.EVALUATOR, VAEKTypes.RiskTier.LOW, true);
        resources.setResource(SERVICE_ID, address(0x5151), VAEKTypes.ResourceKind.SERVICE, VAEKTypes.RiskTier.LOW, true);
        resources.setResource(VENUE_ID, address(venue), VAEKTypes.ResourceKind.VENUE, VAEKTypes.RiskTier.LOW, true);
        kernel.createMandate(
            MANDATE,
            address(this),
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
        tokenIn.mint(address(kernel), 10_000);
        tokenOut.mint(address(venue), 10_000);
    }

    function run() external {
        require(!completed, "already run");
        bytes32 transferId = _transfer();
        bytes32 swapId = _swap();
        bytes32 serviceId = _service();
        _blockedCase();
        require(kernel.getReceipt(transferId).receiptHash != bytes32(0), "transfer receipt");
        require(kernel.getReceipt(swapId).receiptHash != bytes32(0), "swap receipt");
        require(kernel.getReceipt(serviceId).receiptHash != bytes32(0), "service receipt");
        require(tokenIn.balanceOf(recipient) == 50 && tokenOut.balanceOf(recipient) == 200, "actuals");
        require(tokenIn.balanceOf(address(escrow)) == 50 && blockedObserved, "escrow/block");
        completed = true;
    }

    function _transfer() private returns (bytes32 id) {
        VAEKTypes.EffectHeader memory h = _header();
        id = h.executionId;
        kernel.submitTransfer(h, VAEKTypes.TransferRequest(ASSET_IN, RECIPIENT_ID, 50));
        kernel.executeTransfer(id);
    }

    function _swap() private returns (bytes32 id) {
        VAEKTypes.EffectHeader memory h = _header();
        id = h.executionId;
        kernel.submitSwapExactInput(
            h,
            VAEKTypes.SwapExactInputRequest(
                ASSET_IN,
                ASSET_OUT,
                VENUE_ID,
                RECIPIENT_ID,
                100,
                190,
                keccak256("demo-quote"),
                uint64(block.timestamp + 1 hours)
            )
        );
        _verify(id);
        kernel.executeSwapExactInput(id);
    }

    function _service() private returns (bytes32 id) {
        VAEKTypes.EffectHeader memory h = _header();
        id = h.executionId;
        kernel.submitServicePurchase(
            h,
            VAEKTypes.ServicePurchaseRequest(
                PROVIDER_ID,
                SERVICE_ID,
                ASSET_IN,
                50,
                keccak256("demo-delivery"),
                uint64(block.timestamp + 1 days),
                EVALUATOR_ID
            )
        );
        _verify(id);
        kernel.executeServicePurchase(id);
    }

    function _blockedCase() private {
        VAEKTypes.EffectHeader memory h = _header();
        try kernel.submitTransfer(h, VAEKTypes.TransferRequest(ASSET_IN, keccak256("unlisted"), 1)) {
            revert("unexpected allow");
        } catch {
            blockedObserved = true;
        }
    }

    function _verify(bytes32 executionId) private {
        (, bytes32 authorizationHash,,,,,) = kernel.getAuthorization(executionId);
        kernel.recordVerification(
            executionId, authorizationHash, uint64(block.timestamp + 1 hours), keccak256("demo-method")
        );
    }

    function _header() private returns (VAEKTypes.EffectHeader memory) {
        uint64 next = ++nonce;
        return VAEKTypes.EffectHeader(
            2,
            keccak256(abi.encode("demo", next)),
            MANDATE,
            next,
            uint64(block.timestamp),
            uint64(block.timestamp + 2 days),
            keccak256("demo-observation"),
            keccak256("demo-model"),
            POLICY,
            keccak256("demo-context")
        );
    }
}

