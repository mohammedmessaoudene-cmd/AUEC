// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20Observed {
    function transfer(address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

interface IServicePurchaseAdapter {
    function purchase(
        bytes32 executionId,
        address provider,
        bytes32 serviceId,
        address asset,
        uint256 maximumCharge,
        bytes32 contextHash
    ) external returns (uint256 actualCharge, bytes32 outcomeHash);
}

contract RefinementEffectKernel {
    enum EffectType {
        NONE,
        TRANSFER_ERC20,
        PURCHASE_SERVICE
    }
    enum Verdict {
        UNSET,
        PASS,
        FAIL
    }
    enum Decision {
        BLOCK,
        ALLOW_EXACT,
        ALLOW_REFINED,
        ESCALATE
    }
    enum RiskTier {
        LOW,
        MEDIUM,
        HIGH,
        CRITICAL
    }

    struct Mandate {
        address principal;
        address aiExecutor;
        address asset;
        uint128 maxPerEffect;
        uint128 maxTotal;
        uint128 spent;
        uint128 humanGateAbove;
        uint64 validFrom;
        uint64 validUntil;
        uint64 policyVersion;
        bytes32 approvedModelCommitment;
        bytes32 policyCommitment;
        uint8 effectMask;
        bool allowRefinement;
        bool requireTransferVerification;
        bool revoked;
    }

    struct EffectRequest {
        bytes32 mandateId;
        EffectType effectType;
        address target;
        address asset;
        uint128 requestedAmount;
        uint64 deadline;
        bool acceptRefinement;
        bytes32 subjectId;
        bytes32 contextHash;
        bytes32 observationHash;
        bytes32 modelCommitment;
        bytes32 policyCommitment;
        bytes32 requestHash;
        uint64 nonce;
        bool submitted;
        bool consumed;
    }

    struct Verification {
        Verdict verdict;
        bytes32 requestHash;
        bytes32 evidenceHash;
        uint64 validUntil;
        address verifier;
    }

    struct Evaluation {
        Decision decision;
        bytes32 reason;
        uint128 authorizedAmount;
        RiskTier riskTier;
        bool verificationRequired;
        bool humanApprovalRequired;
        address adapter;
        uint64 stateVersion;
        uint64 policyVersion;
        uint64 validUntil;
        bytes32 authorizationHash;
    }
    address public immutable verifier;
    address public immutable purchaseAdapter;
    bytes32 public immutable purchaseAdapterCodeHash;
    uint64 public stateVersion = 1;
    uint64 public mandateNonce;
    bool private _executing;
    mapping(bytes32 => Mandate) public mandates;
    mapping(bytes32 => mapping(address => bool)) public allowedTargets;
    mapping(bytes32 => EffectRequest) public requests;
    mapping(bytes32 => Verification) public verifications;
    mapping(bytes32 => bool) public humanApprovals;
    mapping(bytes32 => bytes32) public receiptHashOf;
    event MandateCreated(
        bytes32 indexed mandateId,
        address indexed principal,
        address indexed aiExecutor,
        uint64 policyVersion,
        uint8 effectMask
    );
    event MandateRevoked(bytes32 indexed mandateId, uint64 stateVersion);
    event EffectRequested(
        bytes32 indexed executionId,
        bytes32 indexed mandateId,
        bytes32 indexed requestHash,
        EffectType effectType,
        address target,
        uint256 requestedAmount,
        bool acceptRefinement
    );
    event VerificationRecorded(
        bytes32 indexed executionId,
        bytes32 indexed requestHash,
        Verdict verdict,
        bytes32 evidenceHash,
        uint64 validUntil
    );
    event HumanApprovalRecorded(bytes32 indexed executionId, address indexed principal);
    event EffectEvaluated(
        bytes32 indexed executionId,
        Decision decision,
        bytes32 reason,
        uint256 requestedAmount,
        uint256 authorizedAmount,
        uint64 stateVersion
    );
    event RefinementReceipt(
        bytes32 indexed executionId,
        bytes32 indexed mandateId,
        bytes32 indexed requestHash,
        bytes32 authorizationHash,
        bytes32 receiptHash,
        EffectType effectType,
        address adapter,
        address target,
        address asset,
        uint256 requestedAmount,
        uint256 authorizedAmount,
        uint256 actualAmount,
        uint256 authorityDelta,
        uint256 executionDelta,
        uint64 stateVersionBefore,
        uint64 stateVersionAfter,
        uint64 policyVersion,
        bytes32 outcomeHash
    );
    error Unauthorized();
    error InvalidMandate();
    error InvalidRequest();
    error InvalidCommitment();
    error InvalidVerification();
    error AlreadyConsumed();
    error EffectNotAuthorized(bytes32 reason);
    error AdapterIntegrityFailure();
    error AdapterExecutionFailure();
    error TransferFailed();
    error PostconditionFailure(bytes32 reason);
    error Reentrancy();

    constructor(address verifier_, address purchaseAdapter_) {
        require(verifier_ != address(0), "verifier=0");
        require(purchaseAdapter_ != address(0) && purchaseAdapter_.code.length > 0, "adapter");
        verifier = verifier_;
        purchaseAdapter = purchaseAdapter_;
        purchaseAdapterCodeHash = purchaseAdapter_.codehash;
    }

    function createMandate(
        address aiExecutor,
        address asset,
        uint128 maxPerEffect,
        uint128 maxTotal,
        uint128 humanGateAbove,
        uint64 validFrom,
        uint64 validUntil,
        uint64 policyVersion,
        bytes32 approvedModelCommitment,
        bytes32 policyCommitment,
        uint8 effectMask,
        bool allowRefinement,
        bool requireTransferVerification,
        address[] calldata targets
    ) external returns (bytes32 mandateId) {
        require(aiExecutor != address(0) && asset != address(0), "zero address");
        require(maxPerEffect > 0 && maxTotal >= maxPerEffect, "budget");
        require(validUntil > validFrom && validUntil > block.timestamp, "validity");
        require(policyVersion > 0, "policy version");
        require(approvedModelCommitment != bytes32(0) && policyCommitment != bytes32(0), "commitments");
        require(
            (effectMask & _effectBit(EffectType.TRANSFER_ERC20)) != 0
                || (effectMask & _effectBit(EffectType.PURCHASE_SERVICE)) != 0,
            "effects"
        );
        require(targets.length > 0, "targets");
        mandateId = keccak256(abi.encode("VAEK/MANDATE/R2", block.chainid, address(this), msg.sender, ++mandateNonce));
        mandates[mandateId] = Mandate({
            principal: msg.sender,
            aiExecutor: aiExecutor,
            asset: asset,
            maxPerEffect: maxPerEffect,
            maxTotal: maxTotal,
            spent: 0,
            humanGateAbove: humanGateAbove,
            validFrom: validFrom,
            validUntil: validUntil,
            policyVersion: policyVersion,
            approvedModelCommitment: approvedModelCommitment,
            policyCommitment: policyCommitment,
            effectMask: effectMask,
            allowRefinement: allowRefinement,
            requireTransferVerification: requireTransferVerification,
            revoked: false
        });
        for (uint256 i = 0; i < targets.length; ++i) {
            require(targets[i] != address(0), "target=0");
            allowedTargets[mandateId][targets[i]] = true;
        }
        _bumpState();
        emit MandateCreated(mandateId, msg.sender, aiExecutor, policyVersion, effectMask);
    }

    function revokeMandate(bytes32 mandateId) external {
        Mandate storage mandate = mandates[mandateId];
        if (mandate.principal != msg.sender) revert Unauthorized();
        mandate.revoked = true;
        _bumpState();
        emit MandateRevoked(mandateId, stateVersion);
    }

    function submitTransfer(
        bytes32 executionId,
        bytes32 mandateId,
        address target,
        address asset,
        uint128 amount,
        uint64 deadline,
        bool acceptRefinement,
        bytes32 contextHash,
        bytes32 observationHash,
        bytes32 modelCommitment,
        bytes32 policyCommitment,
        uint64 nonce
    ) external returns (bytes32 requestHash) {
        return _submit(
            executionId,
            mandateId,
            EffectType.TRANSFER_ERC20,
            target,
            asset,
            amount,
            deadline,
            acceptRefinement,
            bytes32(0),
            contextHash,
            observationHash,
            modelCommitment,
            policyCommitment,
            nonce
        );
    }

    function submitServicePurchase(
        bytes32 executionId,
        bytes32 mandateId,
        address provider,
        address asset,
        uint128 maximumCharge,
        uint64 deadline,
        bool acceptRefinement,
        bytes32 serviceId,
        bytes32 quoteHash,
        bytes32 observationHash,
        bytes32 modelCommitment,
        bytes32 policyCommitment,
        uint64 nonce
    ) external returns (bytes32 requestHash) {
        if (serviceId == bytes32(0)) revert InvalidCommitment();
        return _submit(
            executionId,
            mandateId,
            EffectType.PURCHASE_SERVICE,
            provider,
            asset,
            maximumCharge,
            deadline,
            acceptRefinement,
            serviceId,
            quoteHash,
            observationHash,
            modelCommitment,
            policyCommitment,
            nonce
        );
    }

    function recordVerification(
        bytes32 executionId,
        bytes32 expectedRequestHash,
        Verdict verdict,
        bytes32 evidenceHash,
        uint64 validUntil
    ) external {
        if (msg.sender != verifier) revert Unauthorized();
        EffectRequest storage request = requests[executionId];
        if (!request.submitted || request.requestHash != expectedRequestHash) revert InvalidRequest();
        if (verdict != Verdict.PASS && verdict != Verdict.FAIL) revert InvalidVerification();
        if (evidenceHash == bytes32(0) || validUntil < block.timestamp || validUntil > request.deadline) {
            revert InvalidVerification();
        }
        verifications[executionId] = Verification({
            verdict: verdict,
            requestHash: expectedRequestHash,
            evidenceHash: evidenceHash,
            validUntil: validUntil,
            verifier: msg.sender
        });
        _bumpState();
        emit VerificationRecorded(executionId, expectedRequestHash, verdict, evidenceHash, validUntil);
    }

    function approveHighRisk(bytes32 executionId) external {
        EffectRequest storage request = requests[executionId];
        if (!request.submitted) revert InvalidRequest();
        Mandate storage mandate = mandates[request.mandateId];
        if (mandate.principal != msg.sender) revert Unauthorized();
        humanApprovals[executionId] = true;
        _bumpState();
        emit HumanApprovalRecorded(executionId, msg.sender);
    }

    function evaluate(bytes32 executionId) public view returns (Evaluation memory evaluation) {
        EffectRequest storage request = requests[executionId];
        Mandate storage mandate = mandates[request.mandateId];
        return _evaluate(executionId, request, mandate);
    }

    function execute(bytes32 executionId) external returns (bytes32 receiptHash) {
        if (_executing) revert Reentrancy();
        EffectRequest storage request = requests[executionId];
        if (!request.submitted) revert InvalidRequest();
        if (request.consumed) revert AlreadyConsumed();
        Evaluation memory evaluation = evaluate(executionId);
        emit EffectEvaluated(
            executionId,
            evaluation.decision,
            evaluation.reason,
            request.requestedAmount,
            evaluation.authorizedAmount,
            evaluation.stateVersion
        );
        if (evaluation.decision != Decision.ALLOW_EXACT && evaluation.decision != Decision.ALLOW_REFINED) {
            revert EffectNotAuthorized(evaluation.reason);
        }
        Mandate storage mandate = mandates[request.mandateId];
        uint64 stateBefore = stateVersion;
        uint256 actualAmount;
        bytes32 outcomeHash;
        uint256 balanceBefore = IERC20Observed(request.asset).balanceOf(request.target);
        _executing = true;
        request.consumed = true;
        if (request.effectType == EffectType.TRANSFER_ERC20) {
            actualAmount = evaluation.authorizedAmount;
            outcomeHash = keccak256(
                abi.encode("VAEK/TRANSFER-OUTCOME/R2", executionId, request.target, request.asset, actualAmount)
            );
            mandate.spent += evaluation.authorizedAmount;
            if (!IERC20Observed(request.asset).transfer(request.target, evaluation.authorizedAmount)) {
                revert TransferFailed();
            }
        } else if (request.effectType == EffectType.PURCHASE_SERVICE) {
            if (purchaseAdapter.codehash != purchaseAdapterCodeHash) revert AdapterIntegrityFailure();
            try IServicePurchaseAdapter(purchaseAdapter)
                .purchase(
                    executionId,
                    request.target,
                    request.subjectId,
                    request.asset,
                    evaluation.authorizedAmount,
                    request.contextHash
                ) returns (
                uint256 charged, bytes32 adapterOutcomeHash
            ) {
                actualAmount = charged;
                outcomeHash = adapterOutcomeHash;
            } catch {
                revert AdapterExecutionFailure();
            }
            if (actualAmount == 0 || actualAmount > evaluation.authorizedAmount) {
                revert PostconditionFailure("PURCHASE_CHARGE");
            }
            mandate.spent += uint128(actualAmount);
            if (!IERC20Observed(request.asset).transfer(request.target, actualAmount)) revert TransferFailed();
        } else {
            revert InvalidRequest();
        }
        uint256 balanceAfter = IERC20Observed(request.asset).balanceOf(request.target);
        if (balanceAfter < balanceBefore || balanceAfter - balanceBefore != actualAmount) {
            revert PostconditionFailure("BALANCE_DELTA");
        }
        _executing = false;
        _bumpState();
        uint64 stateAfter = stateVersion;
        uint256 authorityDelta = uint256(request.requestedAmount) - uint256(evaluation.authorizedAmount);
        uint256 executionDelta = uint256(evaluation.authorizedAmount) - actualAmount;
        receiptHash = keccak256(
            abi.encode(
                "VAEK/REFINEMENT-RECEIPT/R2",
                block.chainid,
                address(this),
                executionId,
                request.mandateId,
                request.requestHash,
                evaluation.authorizationHash,
                request.effectType,
                evaluation.adapter,
                request.target,
                request.asset,
                request.requestedAmount,
                evaluation.authorizedAmount,
                actualAmount,
                authorityDelta,
                executionDelta,
                stateBefore,
                stateAfter,
                mandate.policyVersion,
                outcomeHash
            )
        );
        receiptHashOf[executionId] = receiptHash;
        emit RefinementReceipt(
            executionId,
            request.mandateId,
            request.requestHash,
            evaluation.authorizationHash,
            receiptHash,
            request.effectType,
            evaluation.adapter,
            request.target,
            request.asset,
            request.requestedAmount,
            evaluation.authorizedAmount,
            actualAmount,
            authorityDelta,
            executionDelta,
            stateBefore,
            stateAfter,
            mandate.policyVersion,
            outcomeHash
        );
    }

    function isConsumed(bytes32 executionId) external view returns (bool) {
        return requests[executionId].consumed;
    }

    function spentOf(bytes32 mandateId) external view returns (uint128) {
        return mandates[mandateId].spent;
    }

    function requestHashOf(bytes32 executionId) external view returns (bytes32) {
        return requests[executionId].requestHash;
    }

    function effectBit(EffectType effectType) external pure returns (uint8) {
        return _effectBit(effectType);
    }

    function adapterFor(EffectType effectType) public view returns (address) {
        if (effectType == EffectType.TRANSFER_ERC20) return address(this);
        if (effectType == EffectType.PURCHASE_SERVICE) return purchaseAdapter;
        return address(0);
    }

    function _submit(
        bytes32 executionId,
        bytes32 mandateId,
        EffectType effectType,
        address target,
        address asset,
        uint128 amount,
        uint64 deadline,
        bool acceptRefinement,
        bytes32 subjectId,
        bytes32 contextHash,
        bytes32 observationHash,
        bytes32 modelCommitment,
        bytes32 policyCommitment,
        uint64 nonce
    ) internal returns (bytes32 requestHash) {
        Mandate storage mandate = mandates[mandateId];
        if (mandate.principal == address(0) || mandate.aiExecutor != msg.sender) revert Unauthorized();
        if (executionId == bytes32(0) || requests[executionId].submitted) revert InvalidRequest();
        if (target == address(0) || asset == address(0)) revert InvalidRequest();
        if (
            contextHash == bytes32(0) || observationHash == bytes32(0) || modelCommitment == bytes32(0)
                || policyCommitment == bytes32(0)
        ) revert InvalidCommitment();
        requestHash = keccak256(
            abi.encode(
                "VAEK/EFFECT-REQUEST/R2",
                block.chainid,
                address(this),
                executionId,
                mandateId,
                effectType,
                target,
                asset,
                amount,
                deadline,
                acceptRefinement,
                subjectId,
                contextHash,
                observationHash,
                modelCommitment,
                policyCommitment,
                nonce
            )
        );
        requests[executionId] = EffectRequest({
            mandateId: mandateId,
            effectType: effectType,
            target: target,
            asset: asset,
            requestedAmount: amount,
            deadline: deadline,
            acceptRefinement: acceptRefinement,
            subjectId: subjectId,
            contextHash: contextHash,
            observationHash: observationHash,
            modelCommitment: modelCommitment,
            policyCommitment: policyCommitment,
            requestHash: requestHash,
            nonce: nonce,
            submitted: true,
            consumed: false
        });
        _bumpState();
        emit EffectRequested(executionId, mandateId, requestHash, effectType, target, amount, acceptRefinement);
    }

    function _evaluate(bytes32 executionId, EffectRequest storage request, Mandate storage mandate)
        internal
        view
        returns (Evaluation memory evaluation)
    {
        if (!request.submitted) return _block(request, mandate, "NO_REQUEST");
        if (request.consumed) return _block(request, mandate, "CONSUMED");
        if (mandate.principal == address(0)) return _block(request, mandate, "NO_MANDATE");
        if (mandate.revoked) return _block(request, mandate, "REVOKED");
        if (block.timestamp < mandate.validFrom || block.timestamp > mandate.validUntil) {
            return _block(request, mandate, "MANDATE_TIME");
        }
        if (block.timestamp > request.deadline) return _block(request, mandate, "REQUEST_STALE");
        if ((mandate.effectMask & _effectBit(request.effectType)) == 0) return _block(request, mandate, "EFFECT_TYPE");
        if (!allowedTargets[request.mandateId][request.target]) return _block(request, mandate, "TARGET");
        if (request.asset != mandate.asset) return _block(request, mandate, "ASSET");
        if (request.modelCommitment != mandate.approvedModelCommitment) {
            return _block(request, mandate, "MODEL_COMMITMENT");
        }
        if (request.policyCommitment != mandate.policyCommitment) {
            return _block(request, mandate, "POLICY_COMMITMENT");
        }
        if (request.requestedAmount == 0) return _block(request, mandate, "ZERO_AMOUNT");
        uint256 remaining = uint256(mandate.maxTotal) - uint256(mandate.spent);
        uint256 capacity = _min(uint256(mandate.maxPerEffect), remaining);
        if (capacity == 0) return _block(request, mandate, "BUDGET_EXHAUSTED");
        uint128 authorizedAmount = uint128(_min(request.requestedAmount, capacity));
        bool refined = authorizedAmount < request.requestedAmount;
        if (refined && !(mandate.allowRefinement && request.acceptRefinement)) {
            return _block(request, mandate, "REFINEMENT_NOT_AUTHORIZED");
        }
        RiskTier risk = _riskTier(request.effectType, authorizedAmount, mandate.maxPerEffect);
        bool verificationRequired = request.effectType == EffectType.PURCHASE_SERVICE
            || mandate.requireTransferVerification || risk >= RiskTier.MEDIUM;
        bool humanRequired =
            risk >= RiskTier.HIGH || (mandate.humanGateAbove > 0 && authorizedAmount > mandate.humanGateAbove);
        if (verificationRequired) {
            Verification storage verification = verifications[executionId];
            if (
                verification.verdict != Verdict.PASS || verification.requestHash != request.requestHash
                    || verification.evidenceHash == bytes32(0) || verification.validUntil < block.timestamp
                    || verification.validUntil > request.deadline
            ) {
                return _makeEvaluation(Decision.BLOCK, "VERIFICATION", 0, risk, true, humanRequired, request, mandate);
            }
        }
        if (humanRequired && !humanApprovals[executionId]) {
            return _makeEvaluation(
                Decision.ESCALATE,
                "HUMAN_APPROVAL_REQUIRED",
                authorizedAmount,
                risk,
                verificationRequired,
                true,
                request,
                mandate
            );
        }
        return _makeEvaluation(
            refined ? Decision.ALLOW_REFINED : Decision.ALLOW_EXACT,
            refined ? bytes32("OK_REFINED") : bytes32("OK_EXACT"),
            authorizedAmount,
            risk,
            verificationRequired,
            humanRequired,
            request,
            mandate
        );
    }

    function _block(EffectRequest storage request, Mandate storage mandate, bytes32 reason)
        internal
        view
        returns (Evaluation memory)
    {
        return _makeEvaluation(Decision.BLOCK, reason, 0, RiskTier.CRITICAL, false, false, request, mandate);
    }

    function _makeEvaluation(
        Decision decision,
        bytes32 reason,
        uint128 authorizedAmount,
        RiskTier risk,
        bool verificationRequired,
        bool humanRequired,
        EffectRequest storage request,
        Mandate storage mandate
    ) internal view returns (Evaluation memory evaluation) {
        uint64 validUntil = request.deadline;
        if (mandate.validUntil != 0 && mandate.validUntil < validUntil) validUntil = mandate.validUntil;
        address adapter = adapterFor(request.effectType);
        bytes32 authorizationHash = keccak256(
            abi.encode(
                "VAEK/AUTHORIZATION/R2",
                block.chainid,
                address(this),
                request.requestHash,
                decision,
                reason,
                authorizedAmount,
                risk,
                verificationRequired,
                humanRequired,
                adapter,
                stateVersion,
                mandate.policyVersion,
                mandate.spent,
                validUntil
            )
        );
        evaluation = Evaluation({
            decision: decision,
            reason: reason,
            authorizedAmount: authorizedAmount,
            riskTier: risk,
            verificationRequired: verificationRequired,
            humanApprovalRequired: humanRequired,
            adapter: adapter,
            stateVersion: stateVersion,
            policyVersion: mandate.policyVersion,
            validUntil: validUntil,
            authorizationHash: authorizationHash
        });
    }

    function _riskTier(EffectType effectType, uint128 amount, uint128 maxPerEffect) internal pure returns (RiskTier) {
        uint256 bps = uint256(amount) * 10_000 / uint256(maxPerEffect);
        if (effectType == EffectType.PURCHASE_SERVICE) {
            if (bps > 7500) return RiskTier.HIGH;
            if (bps > 2500) return RiskTier.MEDIUM;
            return RiskTier.LOW;
        }
        if (bps > 9000) return RiskTier.HIGH;
        if (bps > 5000) return RiskTier.MEDIUM;
        return RiskTier.LOW;
    }

    function _effectBit(EffectType effectType) internal pure returns (uint8) {
        if (effectType == EffectType.NONE) return 0;
        return uint8(1 << uint8(effectType));
    }

    function _bumpState() internal {
        unchecked {
            ++stateVersion;
        }
    }

    function _min(uint256 a, uint256 b) internal pure returns (uint256) {
        return a < b ? a : b;
    }
}
