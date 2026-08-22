// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20Minimal {
    function transfer(address to, uint256 amount) external returns (bool);
}

/// @title BV-AIC Authority Kernel R1
/// @notice A compromised AI may propose typed effects, but deterministic on-chain authority decides whether they execute.
/// @dev Research prototype. NOT audited. DO NOT use with production funds.
contract BVAICAuthority {
    enum Verdict {
        UNSET,
        PASS,
        FAIL
    }
    enum AuthorityResult {
        BLOCK,
        ALLOW,
        ESCALATE
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
        bool requireVerification;
        bool revoked;
    }

    struct Decision {
        bytes32 mandateId;
        address target;
        address asset;
        uint128 amount;
        uint64 deadline;
        bytes32 observationHash;
        bytes32 modelCommitment;
        bytes32 policyCommitment;
        bytes32 decisionHash;
        bool submitted;
        bool consumed;
    }

    struct Verification {
        Verdict verdict;
        address verifier;
        bytes32 decisionHash;
        bytes32 evidenceHash;
        uint64 validUntil;
    }

    address public immutable verifier;
    uint256 public mandateNonce;
    bool private _executing;

    mapping(bytes32 => Mandate) public mandates;
    mapping(bytes32 => mapping(address => bool)) public allowedTargets;
    mapping(bytes32 => Decision) public decisions;
    mapping(bytes32 => Verification) public verifications;
    mapping(bytes32 => bool) public humanApprovals;

    event MandateCreated(bytes32 indexed mandateId, address indexed principal, address indexed aiExecutor);
    event MandateRevoked(bytes32 indexed mandateId);
    event DecisionSubmitted(
        bytes32 indexed executionId,
        bytes32 indexed mandateId,
        bytes32 indexed decisionHash,
        address target,
        uint256 amount
    );
    event VerificationRecorded(
        bytes32 indexed executionId,
        Verdict verdict,
        bytes32 indexed decisionHash,
        bytes32 evidenceHash,
        uint64 validUntil
    );
    event HumanApprovalRecorded(bytes32 indexed executionId, address indexed principal);
    event AuthorityEvaluated(bytes32 indexed executionId, AuthorityResult result, bytes32 reasonCode);
    event EffectExecuted(bytes32 indexed executionId, address indexed asset, address indexed target, uint256 amount);
    event AssuranceReceipt(
        bytes32 indexed executionId,
        bytes32 indexed mandateId,
        bytes32 indexed decisionHash,
        bytes32 observationHash,
        bytes32 modelCommitment,
        bytes32 policyCommitment,
        address principal,
        address target,
        address asset,
        uint256 amount
    );

    error Unauthorized();
    error InvalidMandate();
    error InvalidDecision();
    error InvalidCommitment();
    error AlreadyConsumed();
    error TransferFailed();
    error Reentrancy();

    constructor(address verifier_) {
        require(verifier_ != address(0), "verifier=0");
        verifier = verifier_;
    }

    function createMandate(
        address aiExecutor,
        address asset,
        uint128 maxPerEffect,
        uint128 maxTotal,
        uint128 humanGateAbove,
        uint64 validFrom,
        uint64 validUntil,
        bool requireVerification,
        address[] calldata targets
    ) external returns (bytes32 mandateId) {
        require(aiExecutor != address(0) && asset != address(0), "zero addr");
        require(validUntil > validFrom && validUntil > block.timestamp, "bad validity");
        require(maxPerEffect > 0 && maxTotal >= maxPerEffect, "bad budget");
        require(targets.length > 0, "no targets");

        mandateId = keccak256(abi.encode(address(this), block.chainid, msg.sender, ++mandateNonce));
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
            requireVerification: requireVerification,
            revoked: false
        });

        for (uint256 i = 0; i < targets.length; i++) {
            require(targets[i] != address(0), "target=0");
            allowedTargets[mandateId][targets[i]] = true;
        }

        emit MandateCreated(mandateId, msg.sender, aiExecutor);
    }

    function revokeMandate(bytes32 mandateId) external {
        Mandate storage m = mandates[mandateId];
        if (m.principal != msg.sender) revert Unauthorized();
        m.revoked = true;
        emit MandateRevoked(mandateId);
    }

    /// @notice Canonical commitment to every field that may influence this typed transfer proposal.
    function computeDecisionHash(
        bytes32 executionId,
        bytes32 mandateId,
        address target,
        address asset,
        uint128 amount,
        uint64 deadline,
        bytes32 observationHash,
        bytes32 modelCommitment,
        bytes32 policyCommitment
    ) public view returns (bytes32) {
        return keccak256(
            abi.encode(
                "BV-AIC/DECISION/R1",
                block.chainid,
                address(this),
                executionId,
                mandateId,
                target,
                asset,
                amount,
                deadline,
                observationHash,
                modelCommitment,
                policyCommitment
            )
        );
    }

    /// @notice AI proposes only a typed token transfer. It cannot provide executable calldata.
    function submitDecision(
        bytes32 executionId,
        bytes32 mandateId,
        address target,
        address asset,
        uint128 amount,
        uint64 deadline,
        bytes32 observationHash,
        bytes32 modelCommitment,
        bytes32 policyCommitment
    ) external returns (bytes32 decisionHash) {
        Mandate storage m = mandates[mandateId];
        if (m.principal == address(0) || m.aiExecutor != msg.sender) revert Unauthorized();
        if (decisions[executionId].submitted || executionId == bytes32(0)) revert InvalidDecision();
        if (observationHash == bytes32(0) || modelCommitment == bytes32(0) || policyCommitment == bytes32(0)) {
            revert InvalidCommitment();
        }

        decisionHash = computeDecisionHash(
            executionId, mandateId, target, asset, amount, deadline, observationHash, modelCommitment, policyCommitment
        );

        decisions[executionId] = Decision({
            mandateId: mandateId,
            target: target,
            asset: asset,
            amount: amount,
            deadline: deadline,
            observationHash: observationHash,
            modelCommitment: modelCommitment,
            policyCommitment: policyCommitment,
            decisionHash: decisionHash,
            submitted: true,
            consumed: false
        });

        emit DecisionSubmitted(executionId, mandateId, decisionHash, target, amount);
    }

    /// @notice Verifier assertion is cryptographically bound to the immutable decision hash.
    function recordVerification(
        bytes32 executionId,
        bytes32 expectedDecisionHash,
        Verdict verdict,
        bytes32 evidenceHash,
        uint64 validUntil
    ) external {
        if (msg.sender != verifier) revert Unauthorized();
        Decision storage d = decisions[executionId];
        if (!d.submitted || d.decisionHash != expectedDecisionHash) revert InvalidDecision();
        require(verdict == Verdict.PASS || verdict == Verdict.FAIL, "bad verdict");
        require(evidenceHash != bytes32(0), "evidence=0");
        require(validUntil >= block.timestamp && validUntil <= d.deadline, "bad assertion time");
        verifications[executionId] = Verification(verdict, msg.sender, expectedDecisionHash, evidenceHash, validUntil);
        emit VerificationRecorded(executionId, verdict, expectedDecisionHash, evidenceHash, validUntil);
    }

    function approveHighRisk(bytes32 executionId) external {
        Decision storage d = decisions[executionId];
        if (!d.submitted) revert InvalidDecision();
        Mandate storage m = mandates[d.mandateId];
        if (msg.sender != m.principal) revert Unauthorized();
        humanApprovals[executionId] = true;
        emit HumanApprovalRecorded(executionId, msg.sender);
    }

    function evaluate(bytes32 executionId) public view returns (AuthorityResult result, bytes32 reasonCode) {
        Decision storage d = decisions[executionId];
        if (!d.submitted) return (AuthorityResult.BLOCK, "NO_DECISION");
        if (d.consumed) return (AuthorityResult.BLOCK, "CONSUMED");

        Mandate storage m = mandates[d.mandateId];
        if (m.principal == address(0)) return (AuthorityResult.BLOCK, "NO_MANDATE");
        if (m.revoked) return (AuthorityResult.BLOCK, "REVOKED");
        if (block.timestamp < m.validFrom || block.timestamp > m.validUntil) {
            return (AuthorityResult.BLOCK, "MANDATE_TIME");
        }
        if (block.timestamp > d.deadline) return (AuthorityResult.BLOCK, "DECISION_STALE");
        if (!allowedTargets[d.mandateId][d.target]) return (AuthorityResult.BLOCK, "TARGET");
        if (d.asset != m.asset) return (AuthorityResult.BLOCK, "ASSET");
        if (d.amount == 0 || d.amount > m.maxPerEffect) return (AuthorityResult.BLOCK, "PER_EFFECT_BUDGET");
        if (uint256(m.spent) + uint256(d.amount) > uint256(m.maxTotal)) return (AuthorityResult.BLOCK, "TOTAL_BUDGET");

        if (m.requireVerification) {
            Verification storage v = verifications[executionId];
            if (v.verdict != Verdict.PASS || v.decisionHash != d.decisionHash || v.validUntil < block.timestamp) {
                return (AuthorityResult.BLOCK, "VERIFICATION");
            }
        }

        if (m.humanGateAbove > 0 && d.amount > m.humanGateAbove && !humanApprovals[executionId]) {
            return (AuthorityResult.ESCALATE, "HUMAN_GATE");
        }

        return (AuthorityResult.ALLOW, "OK");
    }

    function isConsumed(bytes32 executionId) external view returns (bool) {
        return decisions[executionId].consumed;
    }

    function spentOf(bytes32 mandateId) external view returns (uint128) {
        return mandates[mandateId].spent;
    }

    function execute(bytes32 executionId) external {
        if (_executing) revert Reentrancy();
        Decision storage d = decisions[executionId];
        if (!d.submitted) revert InvalidDecision();
        if (d.consumed) revert AlreadyConsumed();

        (AuthorityResult result, bytes32 reason) = evaluate(executionId);
        emit AuthorityEvaluated(executionId, result, reason);
        if (result != AuthorityResult.ALLOW) revert InvalidDecision();

        Mandate storage m = mandates[d.mandateId];
        _executing = true;
        d.consumed = true;
        m.spent += d.amount;

        bool ok = IERC20Minimal(d.asset).transfer(d.target, d.amount);
        if (!ok) revert TransferFailed();

        _executing = false;
        emit EffectExecuted(executionId, d.asset, d.target, d.amount);
        emit AssuranceReceipt(
            executionId,
            d.mandateId,
            d.decisionHash,
            d.observationHash,
            d.modelCommitment,
            d.policyCommitment,
            m.principal,
            d.target,
            d.asset,
            d.amount
        );
    }
}
