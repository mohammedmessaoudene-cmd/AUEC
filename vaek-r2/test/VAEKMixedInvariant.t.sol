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

contract MixedHandler {
    bytes32 private constant MANDATE = keccak256("mixed-mandate");
    bytes32 private constant POLICY = keccak256("mixed-policy");
    bytes32 private constant ASSET_IN = keccak256("mixed-in");
    bytes32 private constant ASSET_OUT = keccak256("mixed-out");
    bytes32 private constant RECIPIENT_ID = keccak256("mixed-recipient");
    bytes32 private constant PROVIDER_ID = keccak256("mixed-provider");
    bytes32 private constant EVALUATOR_ID = keccak256("mixed-evaluator");
    bytes32 private constant SERVICE_ID = keccak256("mixed-service");
    bytes32 private constant VENUE_ID = keccak256("mixed-venue");

    address public constant RECIPIENT = address(0xCAFE);
    address public constant PROVIDER = address(0xD00D);
    address public constant EVALUATOR = address(0xE0A1);
    VAEKKernel public immutable kernel;
    MockERC20 public immutable tokenIn;
    MockERC20 public immutable tokenOut;
    MockSwapVenue public immutable venue;
    ServiceEscrowAdapter public immutable escrow;
    uint64 public nonce;

    constructor() {
        ResourceRegistry resources = new ResourceRegistry(address(this));
        AdapterRegistry adapters = new AdapterRegistry(address(this));
        kernel = new VAEKKernel(resources, adapters, address(this));
        ERC20TransferAdapter transfer = new ERC20TransferAdapter(address(kernel));
        BoundedSwapAdapter swap = new BoundedSwapAdapter(address(kernel));
        escrow = new ServiceEscrowAdapter(address(kernel));
        tokenIn = new MockERC20("MixedIn", 6);
        tokenOut = new MockERC20("MixedOut", 6);
        venue = new MockSwapVenue();
        adapters.setAdapter(VAEKTypes.EffectType.TRANSFER_ERC20, address(transfer));
        adapters.setAdapter(VAEKTypes.EffectType.SWAP_EXACT_INPUT, address(swap));
        adapters.setAdapter(VAEKTypes.EffectType.BUY_SERVICE_ESCROW, address(escrow));
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
            address(this),
            POLICY,
            7,
            10,
            10,
            10,
            1_000,
            100,
            500,
            900,
            uint64(block.timestamp),
            uint64(block.timestamp + 30 days),
            VAEKTypes.RiskTier.MEDIUM
        );
        tokenIn.mint(address(kernel), 1_000);
        tokenOut.mint(address(venue), 1_000);
    }

    function step(uint8 rawKind, uint128 rawAmount) external {
        uint8 kind = rawKind % 3;
        uint128 amount = uint128((uint256(rawAmount) % 10) + 1);
        VAEKTypes.EffectHeader memory h = _header();
        if (kind == 0) {
            try kernel.submitTransfer(h, VAEKTypes.TransferRequest(ASSET_IN, RECIPIENT_ID, amount)) {
                try kernel.executeTransfer(h.executionId) {} catch {}
            } catch {}
        } else if (kind == 1) {
            VAEKTypes.SwapExactInputRequest memory request = VAEKTypes.SwapExactInputRequest(
                ASSET_IN,
                ASSET_OUT,
                VENUE_ID,
                RECIPIENT_ID,
                amount,
                amount * 2,
                keccak256("mixed-quote"),
                uint64(block.timestamp + 1 hours)
            );
            try kernel.submitSwapExactInput(h, request) {
                _verifyAndExecute(h.executionId, 1);
            } catch {}
        } else {
            VAEKTypes.ServicePurchaseRequest memory request = VAEKTypes.ServicePurchaseRequest(
                PROVIDER_ID,
                SERVICE_ID,
                ASSET_IN,
                amount,
                keccak256(abi.encode("delivery", h.executionId)),
                uint64(block.timestamp + 1 days),
                EVALUATOR_ID
            );
            try kernel.submitServicePurchase(h, request) {
                _verifyAndExecute(h.executionId, 2);
            } catch {}
        }
    }

    function mandateId() external pure returns (bytes32) {
        return MANDATE;
    }

    function _verifyAndExecute(bytes32 executionId, uint8 kind) private {
        (, bytes32 authHash,,,,,) = kernel.getAuthorization(executionId);
        try kernel.recordVerification(
            executionId, authHash, uint64(block.timestamp + 1 hours), keccak256("mixed-method")
        ) {
            if (kind == 1) {
                try kernel.executeSwapExactInput(executionId) {} catch {}
            } else {
                try kernel.executeServicePurchase(executionId) {} catch {}
            }
        } catch {}
    }

    function _header() private returns (VAEKTypes.EffectHeader memory) {
        uint64 next = ++nonce;
        return VAEKTypes.EffectHeader(
            2,
            keccak256(abi.encode(address(this), next)),
            MANDATE,
            next,
            uint64(block.timestamp),
            uint64(block.timestamp + 2 days),
            bytes32(uint256(next)),
            keccak256("model"),
            POLICY,
            keccak256("context")
        );
    }
}

contract VAEKMixedInvariantTest {
    MixedHandler private handler;
    address[] private _targetedContracts;

    function setUp() public {
        handler = new MixedHandler();
        _targetedContracts.push(address(handler));
    }

    function targetContracts() public view returns (address[] memory) {
        return _targetedContracts;
    }

    function invariant_INV022_MixedSpentMatchesKernelOutflow() public view {
        uint256 spent = handler.kernel().spentOf(handler.mandateId());
        assert(spent <= 1_000);
        assert(spent == 1_000 - handler.tokenIn().balanceOf(address(handler.kernel())));
    }

    function invariant_INV036_MixedInputTokenConservation() public view {
        uint256 total = handler.tokenIn().balanceOf(address(handler.kernel()))
            + handler.tokenIn().balanceOf(handler.RECIPIENT()) + handler.tokenIn().balanceOf(address(handler.venue()))
            + handler.tokenIn().balanceOf(address(handler.escrow())) + handler.tokenIn().balanceOf(handler.PROVIDER());
        assert(total == 1_000);
    }

    function invariant_INV035_MixedSwapOutputConservation() public view {
        uint256 total =
            handler.tokenOut().balanceOf(address(handler.venue())) + handler.tokenOut().balanceOf(handler.RECIPIENT());
        assert(total == 1_000);
    }
}

