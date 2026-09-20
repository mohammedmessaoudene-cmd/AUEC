// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity 0.8.24;

import {VAEKTypes} from "../src/VAEKTypes.sol";
import {VAEKKernel} from "../src/kernel/VAEKKernel.sol";
import {ResourceRegistry} from "../src/registries/ResourceRegistry.sol";
import {AdapterRegistry} from "../src/registries/AdapterRegistry.sol";
import {ERC20TransferAdapter} from "../src/adapters/ERC20TransferAdapter.sol";
import {MockERC20} from "../src/mocks/MockERC20.sol";

contract TransferHandler {
    VAEKKernel public immutable kernel;
    bytes32 public immutable mandateId;
    bytes32 public immutable assetId;
    bytes32 public immutable recipientId;
    bytes32 public immutable policyHash;
    uint64 public nonce;

    constructor(VAEKKernel kernel_, bytes32 mandateId_, bytes32 assetId_, bytes32 recipientId_, bytes32 policyHash_) {
        kernel = kernel_;
        mandateId = mandateId_;
        assetId = assetId_;
        recipientId = recipientId_;
        policyHash = policyHash_;
    }

    function step(uint128 rawAmount) external {
        uint128 amount = uint128((uint256(rawAmount) % 10) + 1);
        uint64 next = ++nonce;
        bytes32 executionId = keccak256(abi.encode(address(this), next));
        VAEKTypes.EffectHeader memory h = VAEKTypes.EffectHeader({
            schemaVersion: 2,
            executionId: executionId,
            mandateId: mandateId,
            nonce: next,
            validAfter: uint64(block.timestamp),
            deadline: uint64(block.timestamp + 1 days),
            observationHash: bytes32(uint256(next)),
            modelCommitment: keccak256("model"),
            policyCommitment: policyHash,
            contextHash: keccak256("context")
        });
        try kernel.submitTransfer(h, VAEKTypes.TransferRequest(assetId, recipientId, amount)) {
            try kernel.executeTransfer(executionId) {} catch {}
        } catch {}
    }
}

contract VAEKInvariantTest {
    bytes32 private constant MANDATE = keccak256("invariant-mandate");
    bytes32 private constant POLICY = keccak256("invariant-policy");
    bytes32 private constant ASSET = keccak256("asset");
    bytes32 private constant RECIPIENT_ID = keccak256("recipient");
    address private constant RECIPIENT = address(0xCAFE);

    VAEKKernel private kernel;
    MockERC20 private token;
    TransferHandler private handler;
    address[] private _targetedContracts;

    function setUp() public {
        ResourceRegistry resources = new ResourceRegistry(address(this));
        AdapterRegistry adapters = new AdapterRegistry(address(this));
        kernel = new VAEKKernel(resources, adapters, address(0xBEEF));
        ERC20TransferAdapter adapter = new ERC20TransferAdapter(address(kernel));
        adapters.setAdapter(VAEKTypes.EffectType.TRANSFER_ERC20, address(adapter));
        token = new MockERC20("Invariant", 6);
        resources.setResource(ASSET, address(token), VAEKTypes.ResourceKind.ASSET, VAEKTypes.RiskTier.LOW, true);
        resources.setResource(
            RECIPIENT_ID, RECIPIENT, VAEKTypes.ResourceKind.COUNTERPARTY, VAEKTypes.RiskTier.LOW, true
        );
        handler = new TransferHandler(kernel, MANDATE, ASSET, RECIPIENT_ID, POLICY);
        kernel.createMandate(
            MANDATE,
            address(handler),
            POLICY,
            1,
            10,
            0,
            0,
            1_000,
            100,
            500,
            900,
            uint64(block.timestamp),
            uint64(block.timestamp + 30 days),
            VAEKTypes.RiskTier.LOW
        );
        token.mint(address(kernel), 1_000);
        _targetedContracts.push(address(handler));
    }

    function targetContracts() public view returns (address[] memory) {
        return _targetedContracts;
    }

    function invariant_INV022_SpentNeverExceedsAggregateBudget() public view {
        assert(kernel.spentOf(MANDATE) <= 1_000);
    }

    function invariant_INV036_DeclaredTokenConservation() public view {
        assert(token.balanceOf(address(kernel)) + token.balanceOf(RECIPIENT) == 1_000);
    }

    function invariant_INV044_SpentEqualsMeasuredRecipientBalance() public view {
        assert(kernel.spentOf(MANDATE) == token.balanceOf(RECIPIENT));
    }
}
