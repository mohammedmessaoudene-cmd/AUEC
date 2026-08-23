// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity 0.8.24;

/// @notice RESEARCH PROTOTYPE — NOT AUDITED — NO PRODUCTION FUNDS.
library VAEKTypes {
    enum EffectType {
        TRANSFER_ERC20,
        SWAP_EXACT_INPUT,
        BUY_SERVICE_ESCROW
    }

    enum DecisionCode {
        BLOCK,
        ALLOW_EXACT,
        ALLOW_ATTENUATED,
        ESCALATE,
        DEFER
    }

    enum RiskTier {
        LOW,
        MEDIUM,
        HIGH,
        CRITICAL
    }

    enum EffectState {
        NONE,
        REQUESTED,
        AUTHORIZED_EXACT,
        AUTHORIZED_ATTENUATED,
        VERIFIED,
        ESCALATED,
        EXECUTING,
        EXECUTED,
        BLOCKED,
        REVOKED,
        EXPIRED
    }

    enum ResourceKind {
        ASSET,
        COUNTERPARTY,
        VENUE,
        SERVICE,
        EVALUATOR
    }

    struct EffectHeader {
        uint16 schemaVersion;
        bytes32 executionId;
        bytes32 mandateId;
        uint64 nonce;
        uint64 validAfter;
        uint64 deadline;
        bytes32 observationHash;
        bytes32 modelCommitment;
        bytes32 policyCommitment;
        bytes32 contextHash;
    }

    struct TransferRequest {
        bytes32 assetId;
        bytes32 recipientId;
        uint128 requestedAmount;
    }

    struct SwapExactInputRequest {
        bytes32 assetInId;
        bytes32 assetOutId;
        bytes32 venueId;
        bytes32 recipientId;
        uint128 maxInput;
        uint128 minOutput;
        bytes32 quoteCommitment;
        uint64 quoteValidUntil;
    }

    struct ServicePurchaseRequest {
        bytes32 providerId;
        bytes32 serviceId;
        bytes32 paymentAssetId;
        uint128 maxPrice;
        bytes32 deliveryCommitment;
        uint64 serviceDeadline;
        bytes32 evaluatorId;
    }

    struct AttenuationWitness {
        bytes32 requestedHash;
        bytes32 authorizedHash;
        uint256 fieldsChangedBitmap;
        uint128 amountReduction;
        uint64 deadlineReduction;
        uint256 controlsAddedBitmap;
        bytes32 reasonCode;
    }

    struct Receipt {
        bytes32 receiptHash;
        bytes32 executionId;
        bytes32 mandateId;
        EffectType effectType;
        bytes32 requestedHash;
        bytes32 authorizedHash;
        bytes32 executedHash;
        bytes32 attenuationWitnessHash;
        bytes32 policyHash;
        uint64 resourceRegistryVersion;
        address adapterAddress;
        uint64 adapterVersion;
        bytes32 adapterCodeHash;
        RiskTier riskTier;
        bytes32 verificationSetHash;
        uint64 requestedAt;
        uint64 authorizedAt;
        uint64 executedAt;
        uint64 blockNumber;
        uint128 actualInput;
        uint128 actualOutput;
        bytes32 resultId;
    }
}

