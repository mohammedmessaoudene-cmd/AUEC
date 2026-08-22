// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "../contracts/RefinementEffectKernel.sol";
import "../contracts/MockEffectEnvironment.sol";

contract RefinementEffectHandler {
    address public constant VENDOR = address(0xC0FFEE);
    address public constant API_PROVIDER = address(0xCAFE);
    address public constant ATTACKER = address(0xBAD);

    bytes32 constant CONTEXT = keccak256("invariant:context:r2");
    bytes32 constant OBSERVATION = keccak256("invariant:observation:r2");
    bytes32 constant MODEL = keccak256("invariant:model:r2");
    bytes32 constant POLICY = keccak256("invariant:policy:r2");
    bytes32 constant EVIDENCE = keccak256("invariant:evidence:r2");
    bytes32 constant SERVICE = keccak256("invariant:service:r2");

    MockERC20 public token;
    MockPurchaseAdapter public adapter;
    RefinementEffectKernel public kernel;
    bytes32 public mandateId;
    uint256 public nonce;
    uint64 public maximumObservedStateVersion;

    constructor() {
        token = new MockERC20();
        adapter = new MockPurchaseAdapter();
        kernel = new RefinementEffectKernel(address(this), address(adapter));
        token.mint(address(kernel), 1_000);

        address[] memory targets = new address[](2);
        targets[0] = VENDOR;
        targets[1] = API_PROVIDER;
        uint8 mask = kernel.effectBit(RefinementEffectKernel.EffectType.TRANSFER_ERC20)
            | kernel.effectBit(RefinementEffectKernel.EffectType.PURCHASE_SERVICE);
        mandateId = kernel.createMandate(
            address(this),
            address(token),
            100,
            250,
            80,
            uint64(block.timestamp),
            uint64(block.timestamp + 365 days),
            1,
            MODEL,
            POLICY,
            mask,
            true,
            false,
            targets
        );
        maximumObservedStateVersion = kernel.stateVersion();
    }

    function stepTransfer(uint128 rawAmount, bool attackTarget, bool acceptRefinement, bool verifyIt, bool approveIt)
        external
    {
        bytes32 id = keccak256(abi.encode("inv-transfer", ++nonce));
        address target = attackTarget ? ATTACKER : VENDOR;
        uint128 amount = uint128(uint256(rawAmount) % 180);
        bytes32 requestHash = kernel.submitTransfer(
            id,
            mandateId,
            target,
            address(token),
            amount,
            uint64(block.timestamp + 1 days),
            acceptRefinement,
            CONTEXT,
            OBSERVATION,
            MODEL,
            POLICY,
            uint64(nonce)
        );
        if (verifyIt) {
            kernel.recordVerification(
                id,
                requestHash,
                RefinementEffectKernel.Verdict.PASS,
                EVIDENCE,
                uint64(block.timestamp + 1 days)
            );
        }
        if (approveIt) kernel.approveHighRisk(id);
        (bool ok,) = address(kernel).call(abi.encodeCall(RefinementEffectKernel.execute, (id)));
        ok;
        _observeVersion();
    }

    function stepPurchase(
        uint128 rawMaximum,
        uint128 rawCharge,
        bool attackTarget,
        bool acceptRefinement,
        bool verifyIt,
        bool approveIt
    ) external {
        bytes32 id = keccak256(abi.encode("inv-purchase", ++nonce));
        address provider = attackTarget ? ATTACKER : API_PROVIDER;
        uint128 maximum = uint128(uint256(rawMaximum) % 180);
        uint256 charge = uint256(rawCharge) % 180;
        adapter.configure(charge, false, address(0), bytes32(0));
        bytes32 requestHash = kernel.submitServicePurchase(
            id,
            mandateId,
            provider,
            address(token),
            maximum,
            uint64(block.timestamp + 1 days),
            acceptRefinement,
            SERVICE,
            CONTEXT,
            OBSERVATION,
            MODEL,
            POLICY,
            uint64(nonce)
        );
        if (verifyIt) {
            kernel.recordVerification(
                id,
                requestHash,
                RefinementEffectKernel.Verdict.PASS,
                EVIDENCE,
                uint64(block.timestamp + 1 days)
            );
        }
        if (approveIt) kernel.approveHighRisk(id);
        (bool ok,) = address(kernel).call(abi.encodeCall(RefinementEffectKernel.execute, (id)));
        ok;
        _observeVersion();
    }

    function revoke() external {
        kernel.revokeMandate(mandateId);
        _observeVersion();
    }

    function _observeVersion() internal {
        uint64 current = kernel.stateVersion();
        require(current >= maximumObservedStateVersion, "state version regressed");
        maximumObservedStateVersion = current;
    }
}

contract RefinementEffectInvariantTest {
    RefinementEffectHandler public handler;

    function setUp() public {
        handler = new RefinementEffectHandler();
    }

    /// @dev Forge invariant target discovery without depending on forge-std.
    function targetContracts() public view returns (address[] memory targets) {
        targets = new address[](1);
        targets[0] = address(handler);
    }

    function invariant_AttackerNeverReceivesFunds() public view {
        require(handler.token().balanceOf(handler.ATTACKER()) == 0, "attacker received funds");
    }

    function invariant_SpentNeverExceedsMandateBudget() public view {
        require(handler.kernel().spentOf(handler.mandateId()) <= 250, "budget exceeded");
    }

    function invariant_SpentEqualsObservedRecipientDeltas() public view {
        uint256 recipients = handler.token().balanceOf(handler.VENDOR())
            + handler.token().balanceOf(handler.API_PROVIDER());
        require(handler.kernel().spentOf(handler.mandateId()) == recipients, "accounting mismatch");
    }

    function invariant_TokenConservation() public view {
        uint256 vault = handler.token().balanceOf(address(handler.kernel()));
        uint256 vendor = handler.token().balanceOf(handler.VENDOR());
        uint256 provider = handler.token().balanceOf(handler.API_PROVIDER());
        uint256 attacker = handler.token().balanceOf(handler.ATTACKER());
        require(vault + vendor + provider + attacker == 1_000, "token conservation broken");
    }

    function invariant_StateVersionNeverRegresses() public view {
        require(
            handler.kernel().stateVersion() >= handler.maximumObservedStateVersion(),
            "state version regression"
        );
    }
}
