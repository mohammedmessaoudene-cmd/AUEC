// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity 0.8.24;

import {VAEKTypes} from "../VAEKTypes.sol";
import {RiskEngine} from "./RiskEngine.sol";
import {ResourceRegistry} from "../registries/ResourceRegistry.sol";
import {AdapterRegistry} from "../registries/AdapterRegistry.sol";
import {TokenOps} from "../libraries/TokenOps.sol";
import {IERC20TransferAdapter, IBoundedSwapAdapter, IServiceEscrowAdapter} from "../interfaces/ITypedAdapters.sol";

/// @notice RESEARCH PROTOTYPE — NOT AUDITED — NO PRODUCTION FUNDS.
/// @dev INV-001/003/004: requests contain no executable bytes or adapter address; adapters are registry selected; no delegatecall.
contract VAEKKernel {
    bytes32 private constant REQUEST_DOMAIN = keccak256("VAEK/EFFECT_REQUEST/R2");
    bytes32 private constant AUTH_DOMAIN = keccak256("VAEK/AUTHORIZATION/R2");
    bytes32 private constant EXEC_DOMAIN = keccak256("VAEK/EXECUTION_RESULT/R2");
    bytes32 private constant RECEIPT_DOMAIN = keccak256("VAEK/RECEIPT/R2");
    uint16 public constant SCHEMA_VERSION = 2;

    struct Mandate {
        address principal;
        address agent;
        bytes32 policyHash;
        uint8 permittedMask;
        uint128 transferCap;
        uint128 swapCap;
        uint128 serviceCap;
        uint128 aggregateCap;
        uint128 spent;
        uint128 mediumThreshold;
        uint128 highThreshold;
        uint128 criticalThreshold;
        uint64 validFrom;
        uint64 validUntil;
        VAEKTypes.RiskTier autoRiskCeiling;
        bool active;
    }

    struct CommonRecord {
        bytes32 requestedHash;
        bytes32 authorizedHash;
        bytes32 witnessHash;
        uint64 resourceVersion;
        uint64 adapterVersion;
        bytes32 adapterCodeHash;
        uint64 requestedAt;
        uint64 authorizedAt;
        VAEKTypes.RiskTier riskTier;
        VAEKTypes.EffectState state;
    }

    struct TransferRecord {
        VAEKTypes.EffectHeader header;
        VAEKTypes.TransferRequest request;
        uint128 authorizedAmount;
        CommonRecord common;
    }

    struct SwapRecord {
        VAEKTypes.EffectHeader header;
        VAEKTypes.SwapExactInputRequest request;
        uint128 authorizedMaxInput;
        uint128 authorizedMinOutput;
        CommonRecord common;
    }

    struct ServiceRecord {
        VAEKTypes.EffectHeader header;
        VAEKTypes.ServicePurchaseRequest request;
        uint128 authorizedPrice;
        CommonRecord common;
    }

    struct Verification {
        bytes32 authorizationHash;
        bytes32 verificationSetHash;
        uint64 validUntil;
    }

    ResourceRegistry public immutable resources;
    AdapterRegistry public immutable adapters;
    address public immutable verifier;

    mapping(bytes32 => Mandate) public mandates;
    mapping(bytes32 => VAEKTypes.EffectType) public effectTypeOf;
    mapping(bytes32 => bool) public executionIdSeen;
    mapping(bytes32 => TransferRecord) private _transfers;
    mapping(bytes32 => SwapRecord) private _swaps;
    mapping(bytes32 => ServiceRecord) private _services;
    mapping(bytes32 => Verification) public verifications;
    mapping(bytes32 => bytes32) public humanApprovalHash;
    mapping(bytes32 => uint64) public humanApprovedAt;
    mapping(bytes32 => VAEKTypes.Receipt) private _receipts;
    bool private _executionLock;

    error Unauthorized();
    error InvalidRequest(bytes32 reason);
    error InvalidState();
    error StaleAuthority();
    error VerificationRequired();
    error HumanApprovalRequired();
    error BoundViolation();

    event MandateCreated(
        bytes32 indexed mandateId, address indexed principal, address indexed agent, bytes32 policyHash
    );
    event MandateRevoked(bytes32 indexed mandateId);
    event EffectRequested(bytes32 indexed executionId, VAEKTypes.EffectType indexed effectType, bytes32 requestedHash);
    event EffectAuthorized(bytes32 indexed executionId, bytes32 authorizedHash, VAEKTypes.DecisionCode decision);
    event VerificationRecorded(
        bytes32 indexed executionId, bytes32 indexed authorizationHash, bytes32 verificationSetHash
    );
    event ReceiptRecorded(bytes32 indexed executionId, bytes32 indexed receiptHash, bytes32 executedHash);

    constructor(ResourceRegistry resources_, AdapterRegistry adapters_, address verifier_) {
        require(
            address(resources_) != address(0) && address(adapters_) != address(0) && verifier_ != address(0), "zero"
        );
        resources = resources_;
        adapters = adapters_;
        verifier = verifier_;
    }

    function createMandate(
        bytes32 mandateId,
        address agent,
        bytes32 policyHash,
        uint8 permittedMask,
        uint128 transferCap,
        uint128 swapCap,
        uint128 serviceCap,
        uint128 aggregateCap,
        uint128 mediumThreshold,
        uint128 highThreshold,
        uint128 criticalThreshold,
        uint64 validFrom,
        uint64 validUntil,
        VAEKTypes.RiskTier autoRiskCeiling
    ) external {
        if (
            mandateId == bytes32(0) || agent == address(0) || policyHash == bytes32(0)
                || mandates[mandateId].principal != address(0) || validUntil <= validFrom
                || validUntil <= block.timestamp || aggregateCap == 0 || mediumThreshold == 0
                || highThreshold <= mediumThreshold || criticalThreshold <= highThreshold
        ) revert InvalidRequest("BAD_MANDATE");
        mandates[mandateId] = Mandate({
            principal: msg.sender,
            agent: agent,
            policyHash: policyHash,
            permittedMask: permittedMask,
            transferCap: transferCap,
            swapCap: swapCap,
            serviceCap: serviceCap,
            aggregateCap: aggregateCap,
            spent: 0,
            mediumThreshold: mediumThreshold,
            highThreshold: highThreshold,
            criticalThreshold: criticalThreshold,
            validFrom: validFrom,
            validUntil: validUntil,
            autoRiskCeiling: autoRiskCeiling,
            active: true
        });
        emit MandateCreated(mandateId, msg.sender, agent, policyHash);
    }

    function revokeMandate(bytes32 mandateId) external {
        Mandate storage mandate = mandates[mandateId];
        if (msg.sender != mandate.principal) revert Unauthorized();
        mandate.active = false;
        emit MandateRevoked(mandateId);
    }

    function submitTransfer(VAEKTypes.EffectHeader calldata h, VAEKTypes.TransferRequest calldata request) external {
        Mandate storage mandate = _validateHeader(h, VAEKTypes.EffectType.TRANSFER_ERC20);
        (, VAEKTypes.RiskTier resourceRisk) = resources.resolve(request.assetId, VAEKTypes.ResourceKind.ASSET);
        (, VAEKTypes.RiskTier recipientRisk) =
            resources.resolve(request.recipientId, VAEKTypes.ResourceKind.COUNTERPARTY);
        if (request.requestedAmount == 0) revert InvalidRequest("ZERO_AMOUNT");
        bytes32 requestedHash = keccak256(abi.encode(REQUEST_DOMAIN, block.chainid, address(this), h, request));
        uint128 allowed = _min3(request.requestedAmount, mandate.transferCap, mandate.aggregateCap - mandate.spent);
        if (allowed == 0) revert BoundViolation();
        VAEKTypes.RiskTier risk =
            _risk(VAEKTypes.EffectType.TRANSFER_ERC20, allowed, mandate, _maxRisk(resourceRisk, recipientRisk));
        AdapterRegistry.Entry memory adapter = adapters.get(VAEKTypes.EffectType.TRANSFER_ERC20);
        bytes32 authHash = _authorizationHash(
            requestedHash,
            abi.encode(request.assetId, request.recipientId, allowed),
            resources.version(),
            adapter,
            risk,
            mandate.policyHash
        );
        bytes32 witness = _witness(requestedHash, authHash, request.requestedAmount, allowed, "TRANSFER_CAP");
        TransferRecord storage record = _transfers[h.executionId];
        record.header = h;
        record.request = request;
        record.authorizedAmount = allowed;
        record.common = _common(requestedHash, authHash, witness, adapter, risk, allowed == request.requestedAmount);
        _register(h.executionId, VAEKTypes.EffectType.TRANSFER_ERC20, requestedHash, authHash, record.common.state);
    }

    function submitSwapExactInput(VAEKTypes.EffectHeader calldata h, VAEKTypes.SwapExactInputRequest calldata request)
        external
    {
        Mandate storage mandate = _validateHeader(h, VAEKTypes.EffectType.SWAP_EXACT_INPUT);
        resources.resolve(request.assetInId, VAEKTypes.ResourceKind.ASSET);
        resources.resolve(request.assetOutId, VAEKTypes.ResourceKind.ASSET);
        (, VAEKTypes.RiskTier venueRisk) = resources.resolve(request.venueId, VAEKTypes.ResourceKind.VENUE);
        (, VAEKTypes.RiskTier recipientRisk) =
            resources.resolve(request.recipientId, VAEKTypes.ResourceKind.COUNTERPARTY);
        if (
            request.maxInput == 0 || request.minOutput == 0 || request.assetInId == request.assetOutId
                || request.quoteCommitment == bytes32(0) || request.quoteValidUntil <= block.timestamp
                || request.quoteValidUntil > h.deadline
        ) revert InvalidRequest("BAD_SWAP");
        bytes32 requestedHash = keccak256(abi.encode(REQUEST_DOMAIN, block.chainid, address(this), h, request));
        AdapterRegistry.Entry memory adapter = adapters.get(VAEKTypes.EffectType.SWAP_EXACT_INPUT);
        uint128 allowed = _min3(request.maxInput, mandate.swapCap, mandate.aggregateCap - mandate.spent);
        if (allowed == 0) revert BoundViolation();
        VAEKTypes.RiskTier risk =
            _risk(VAEKTypes.EffectType.SWAP_EXACT_INPUT, allowed, mandate, _maxRisk(venueRisk, recipientRisk));
        SwapRecord storage record = _swaps[h.executionId];
        record.header = h;
        record.request = request;
        record.authorizedMaxInput = allowed;
        record.authorizedMinOutput = request.minOutput;
        bytes32 authHash = _authorizationHash(
            requestedHash,
            abi.encode(
                request.assetInId, request.assetOutId, request.venueId, request.recipientId, allowed, request.minOutput
            ),
            resources.version(),
            adapter,
            risk,
            mandate.policyHash
        );
        bytes32 witness = _witness(requestedHash, authHash, request.maxInput, allowed, "SWAP_INPUT_CAP");
        record.common = _common(requestedHash, authHash, witness, adapter, risk, allowed == request.maxInput);
        if (allowed != request.maxInput) record.common.state = VAEKTypes.EffectState.ESCALATED;
        _register(h.executionId, VAEKTypes.EffectType.SWAP_EXACT_INPUT, requestedHash, authHash, record.common.state);
    }

    /// @dev ADR-002: principal may accept lower max input only with equal/stricter min output and exact hash binding.
    function approveSwapAttenuation(bytes32 executionId, uint128 maxInput, uint128 minOutput) external {
        SwapRecord storage record = _swaps[executionId];
        Mandate storage mandate = mandates[record.header.mandateId];
        if (msg.sender != mandate.principal) revert Unauthorized();
        if (
            record.common.state != VAEKTypes.EffectState.ESCALATED || maxInput == 0
                || maxInput > record.request.maxInput || maxInput > mandate.swapCap
                || minOutput < record.request.minOutput
        ) revert BoundViolation();
        AdapterRegistry.Entry memory adapter = adapters.get(VAEKTypes.EffectType.SWAP_EXACT_INPUT);
        record.authorizedMaxInput = maxInput;
        record.authorizedMinOutput = minOutput;
        record.common.authorizedHash = _authorizationHash(
            record.common.requestedHash,
            abi.encode(
                record.request.assetInId,
                record.request.assetOutId,
                record.request.venueId,
                record.request.recipientId,
                maxInput,
                minOutput
            ),
            resources.version(),
            adapter,
            record.common.riskTier,
            mandate.policyHash
        );
        record.common.witnessHash = _witness(
            record.common.requestedHash,
            record.common.authorizedHash,
            record.request.maxInput,
            maxInput,
            "PRINCIPAL_SWAP"
        );
        record.common.resourceVersion = resources.version();
        record.common.adapterVersion = adapter.version;
        record.common.adapterCodeHash = adapter.codeHash;
        record.common.authorizedAt = uint64(block.timestamp);
        record.common.state = VAEKTypes.EffectState.AUTHORIZED_ATTENUATED;
        humanApprovalHash[executionId] = record.common.authorizedHash;
        humanApprovedAt[executionId] = uint64(block.timestamp);
        emit EffectAuthorized(executionId, record.common.authorizedHash, VAEKTypes.DecisionCode.ALLOW_ATTENUATED);
    }

    function submitServicePurchase(VAEKTypes.EffectHeader calldata h, VAEKTypes.ServicePurchaseRequest calldata request)
        external
    {
        Mandate storage mandate = _validateHeader(h, VAEKTypes.EffectType.BUY_SERVICE_ESCROW);
        (, VAEKTypes.RiskTier providerRisk) = resources.resolve(request.providerId, VAEKTypes.ResourceKind.COUNTERPARTY);
        resources.resolve(request.serviceId, VAEKTypes.ResourceKind.SERVICE);
        resources.resolve(request.paymentAssetId, VAEKTypes.ResourceKind.ASSET);
        (address provider,) = resources.resolve(request.providerId, VAEKTypes.ResourceKind.COUNTERPARTY);
        (address evaluator, VAEKTypes.RiskTier evaluatorRisk) =
            resources.resolve(request.evaluatorId, VAEKTypes.ResourceKind.EVALUATOR);
        if (
            request.maxPrice == 0 || request.deliveryCommitment == bytes32(0)
                || request.serviceDeadline <= block.timestamp || request.serviceDeadline > mandate.validUntil
                || provider == evaluator
        ) revert InvalidRequest("BAD_SERVICE");
        bytes32 requestedHash = keccak256(abi.encode(REQUEST_DOMAIN, block.chainid, address(this), h, request));
        uint128 allowed = _min3(request.maxPrice, mandate.serviceCap, mandate.aggregateCap - mandate.spent);
        if (allowed == 0) revert BoundViolation();
        VAEKTypes.RiskTier risk =
            _risk(VAEKTypes.EffectType.BUY_SERVICE_ESCROW, allowed, mandate, _maxRisk(providerRisk, evaluatorRisk));
        AdapterRegistry.Entry memory adapter = adapters.get(VAEKTypes.EffectType.BUY_SERVICE_ESCROW);
        bytes32 authHash = _authorizationHash(
            requestedHash,
            abi.encode(
                request.providerId,
                request.serviceId,
                request.paymentAssetId,
                allowed,
                request.deliveryCommitment,
                request.serviceDeadline,
                request.evaluatorId
            ),
            resources.version(),
            adapter,
            risk,
            mandate.policyHash
        );
        bytes32 witness = _witness(requestedHash, authHash, request.maxPrice, allowed, "SERVICE_CAP");
        ServiceRecord storage record = _services[h.executionId];
        record.header = h;
        record.request = request;
        record.authorizedPrice = allowed;
        record.common = _common(requestedHash, authHash, witness, adapter, risk, allowed == request.maxPrice);
        _register(h.executionId, VAEKTypes.EffectType.BUY_SERVICE_ESCROW, requestedHash, authHash, record.common.state);
    }

    function recordVerification(bytes32 executionId, bytes32 authorizationHash, uint64 validUntil, bytes32 methodHash)
        external
    {
        if (msg.sender != verifier) revert Unauthorized();
        (bytes32 currentHash, uint64 requestDeadline, VAEKTypes.EffectState state) = _authorizationState(executionId);
        if (
            authorizationHash != currentHash || methodHash == bytes32(0) || validUntil <= block.timestamp
                || validUntil > requestDeadline || state == VAEKTypes.EffectState.ESCALATED
        ) revert InvalidRequest("BAD_VERIFICATION");
        bytes32 setHash = keccak256(
            abi.encode(
                "VAEK/VERIFICATION_SET/R2",
                block.chainid,
                address(this),
                executionId,
                authorizationHash,
                methodHash,
                validUntil
            )
        );
        verifications[executionId] = Verification(authorizationHash, setHash, validUntil);
        _setState(executionId, VAEKTypes.EffectState.VERIFIED);
        emit VerificationRecorded(executionId, authorizationHash, setHash);
    }

    function approveHighRisk(bytes32 executionId, bytes32 authorizationHash) external {
        (bytes32 currentHash,, VAEKTypes.EffectState state) = _authorizationState(executionId);
        bytes32 mandateId = _mandateId(executionId);
        if (msg.sender != mandates[mandateId].principal) revert Unauthorized();
        if (authorizationHash != currentHash || state == VAEKTypes.EffectState.ESCALATED) revert InvalidState();
        humanApprovalHash[executionId] = authorizationHash;
        humanApprovedAt[executionId] = uint64(block.timestamp);
    }

    function executeTransfer(bytes32 executionId) external {
        TransferRecord storage record = _transfers[executionId];
        address adapter = _preExecute(
            executionId, VAEKTypes.EffectType.TRANSFER_ERC20, record.header, record.common, record.authorizedAmount
        );
        record.common.state = VAEKTypes.EffectState.EXECUTING;
        (address token,) = resources.resolve(record.request.assetId, VAEKTypes.ResourceKind.ASSET);
        (address recipient,) = resources.resolve(record.request.recipientId, VAEKTypes.ResourceKind.COUNTERPARTY);
        TokenOps.safeApprove(token, adapter, 0);
        TokenOps.safeApprove(token, adapter, record.authorizedAmount);
        (uint128 spent, uint128 received) =
            IERC20TransferAdapter(adapter).executeTransfer(token, recipient, record.authorizedAmount);
        TokenOps.safeApprove(token, adapter, 0);
        if (spent > record.authorizedAmount || received > spent) revert BoundViolation();
        bytes32 executedHash = keccak256(abi.encode(EXEC_DOMAIN, record.common.authorizedHash, spent, received));
        _complete(executionId, record.header, record.common, spent, received, bytes32(0), executedHash, adapter);
    }

    function executeSwapExactInput(bytes32 executionId) external {
        SwapRecord storage record = _swaps[executionId];
        address adapter = _preExecute(
            executionId, VAEKTypes.EffectType.SWAP_EXACT_INPUT, record.header, record.common, record.authorizedMaxInput
        );
        if (block.timestamp > record.request.quoteValidUntil) revert StaleAuthority();
        record.common.state = VAEKTypes.EffectState.EXECUTING;
        (address tokenIn,) = resources.resolve(record.request.assetInId, VAEKTypes.ResourceKind.ASSET);
        (address tokenOut,) = resources.resolve(record.request.assetOutId, VAEKTypes.ResourceKind.ASSET);
        (address venue,) = resources.resolve(record.request.venueId, VAEKTypes.ResourceKind.VENUE);
        (address recipient,) = resources.resolve(record.request.recipientId, VAEKTypes.ResourceKind.COUNTERPARTY);
        TokenOps.safeApprove(tokenIn, adapter, 0);
        TokenOps.safeApprove(tokenIn, adapter, record.authorizedMaxInput);
        (uint128 actualInput, uint128 actualOutput) = IBoundedSwapAdapter(adapter)
            .executeSwap(tokenIn, tokenOut, venue, recipient, record.authorizedMaxInput, record.authorizedMinOutput);
        TokenOps.safeApprove(tokenIn, adapter, 0);
        if (actualInput > record.authorizedMaxInput || actualOutput < record.authorizedMinOutput) {
            revert BoundViolation();
        }
        bytes32 executedHash =
            keccak256(abi.encode(EXEC_DOMAIN, record.common.authorizedHash, actualInput, actualOutput));
        _complete(
            executionId, record.header, record.common, actualInput, actualOutput, bytes32(0), executedHash, adapter
        );
    }

    function executeServicePurchase(bytes32 executionId) external {
        ServiceRecord storage record = _services[executionId];
        address adapter = _preExecute(
            executionId, VAEKTypes.EffectType.BUY_SERVICE_ESCROW, record.header, record.common, record.authorizedPrice
        );
        record.common.state = VAEKTypes.EffectState.EXECUTING;
        (address token,) = resources.resolve(record.request.paymentAssetId, VAEKTypes.ResourceKind.ASSET);
        (address provider,) = resources.resolve(record.request.providerId, VAEKTypes.ResourceKind.COUNTERPARTY);
        (address evaluator,) = resources.resolve(record.request.evaluatorId, VAEKTypes.ResourceKind.EVALUATOR);
        TokenOps.safeApprove(token, adapter, 0);
        TokenOps.safeApprove(token, adapter, record.authorizedPrice);
        (bytes32 jobId, uint128 funded) = IServiceEscrowAdapter(adapter)
            .createPurchase(
                token,
                provider,
                evaluator,
                record.authorizedPrice,
                record.request.deliveryCommitment,
                record.request.serviceDeadline
            );
        TokenOps.safeApprove(token, adapter, 0);
        if (funded != record.authorizedPrice || jobId == bytes32(0)) revert BoundViolation();
        bytes32 executedHash = keccak256(abi.encode(EXEC_DOMAIN, record.common.authorizedHash, funded, jobId));
        _complete(executionId, record.header, record.common, funded, funded, jobId, executedHash, adapter);
    }

    function getAuthorization(bytes32 executionId)
        external
        view
        returns (
            bytes32 requestedHash,
            bytes32 authorizedHash,
            bytes32 witnessHash,
            VAEKTypes.RiskTier riskTier,
            VAEKTypes.EffectState state,
            uint128 primaryLimit,
            uint128 secondaryLimit
        )
    {
        VAEKTypes.EffectType effectType = effectTypeOf[executionId];
        if (effectType == VAEKTypes.EffectType.TRANSFER_ERC20) {
            TransferRecord storage transferRecord = _transfers[executionId];
            return (
                transferRecord.common.requestedHash,
                transferRecord.common.authorizedHash,
                transferRecord.common.witnessHash,
                transferRecord.common.riskTier,
                transferRecord.common.state,
                transferRecord.authorizedAmount,
                0
            );
        }
        if (effectType == VAEKTypes.EffectType.SWAP_EXACT_INPUT) {
            SwapRecord storage swapRecord = _swaps[executionId];
            return (
                swapRecord.common.requestedHash,
                swapRecord.common.authorizedHash,
                swapRecord.common.witnessHash,
                swapRecord.common.riskTier,
                swapRecord.common.state,
                swapRecord.authorizedMaxInput,
                swapRecord.authorizedMinOutput
            );
        }
        ServiceRecord storage serviceRecord = _services[executionId];
        return (
            serviceRecord.common.requestedHash,
            serviceRecord.common.authorizedHash,
            serviceRecord.common.witnessHash,
            serviceRecord.common.riskTier,
            serviceRecord.common.state,
            serviceRecord.authorizedPrice,
            0
        );
    }

    function getReceipt(bytes32 executionId) external view returns (VAEKTypes.Receipt memory) {
        return _receipts[executionId];
    }

    function spentOf(bytes32 mandateId) external view returns (uint128) {
        return mandates[mandateId].spent;
    }

    function previewRisk(
        bytes32 mandateId,
        VAEKTypes.EffectType effectType,
        uint128 value,
        VAEKTypes.RiskTier counterpartyTier,
        VAEKTypes.RiskTier stateTier,
        VAEKTypes.RiskTier freshnessTier,
        VAEKTypes.RiskTier modelReportedConcern
    ) external view returns (VAEKTypes.RiskTier) {
        Mandate storage mandate = mandates[mandateId];
        return RiskEngine.compute(
            effectType,
            value,
            mandate.mediumThreshold,
            mandate.highThreshold,
            mandate.criticalThreshold,
            counterpartyTier,
            stateTier,
            freshnessTier,
            modelReportedConcern
        );
    }

    function _validateHeader(VAEKTypes.EffectHeader calldata h, VAEKTypes.EffectType effectType)
        private
        returns (Mandate storage mandate)
    {
        mandate = mandates[h.mandateId];
        if (msg.sender != mandate.agent) revert Unauthorized();
        if (
            h.schemaVersion != SCHEMA_VERSION || h.executionId == bytes32(0) || executionIdSeen[h.executionId]
                || h.validAfter > block.timestamp || h.deadline <= block.timestamp || h.deadline > mandate.validUntil
                || h.policyCommitment != mandate.policyHash || !mandate.active || block.timestamp < mandate.validFrom
                || block.timestamp > mandate.validUntil
                || (mandate.permittedMask & (uint8(1) << uint8(effectType))) == 0
                || mandate.spent >= mandate.aggregateCap
        ) revert InvalidRequest("HEADER_OR_MANDATE");
        executionIdSeen[h.executionId] = true;
        effectTypeOf[h.executionId] = effectType;
    }

    function _preExecute(
        bytes32 executionId,
        VAEKTypes.EffectType effectType,
        VAEKTypes.EffectHeader storage h,
        CommonRecord storage common,
        uint128 amount
    ) private returns (address adapter) {
        if (_executionLock) revert InvalidState();
        if (
            common.state != VAEKTypes.EffectState.AUTHORIZED_EXACT
                && common.state != VAEKTypes.EffectState.AUTHORIZED_ATTENUATED
                && common.state != VAEKTypes.EffectState.VERIFIED
        ) revert InvalidState();
        Mandate storage mandate = mandates[h.mandateId];
        if (
            !mandate.active || block.timestamp < mandate.validFrom || block.timestamp > mandate.validUntil
                || block.timestamp < h.validAfter || block.timestamp > h.deadline
                || resources.version() != common.resourceVersion || mandate.spent + amount > mandate.aggregateCap
        ) revert StaleAuthority();
        AdapterRegistry.Entry memory entry = adapters.get(effectType);
        if (entry.version != common.adapterVersion || entry.codeHash != common.adapterCodeHash) {
            revert StaleAuthority();
        }
        if (uint8(common.riskTier) >= uint8(VAEKTypes.RiskTier.MEDIUM)) {
            Verification memory verification = verifications[executionId];
            if (
                verification.authorizationHash != common.authorizedHash || verification.validUntil < block.timestamp
                    || verification.verificationSetHash == bytes32(0)
            ) revert VerificationRequired();
        }
        if (uint8(common.riskTier) > uint8(mandate.autoRiskCeiling)) {
            if (humanApprovalHash[executionId] != common.authorizedHash) revert HumanApprovalRequired();
            if (
                common.riskTier == VAEKTypes.RiskTier.CRITICAL
                    && block.timestamp < uint256(humanApprovedAt[executionId]) + 1 hours
            ) revert HumanApprovalRequired();
        }
        mandate.spent += amount;
        _executionLock = true;
        return entry.adapter;
    }

    function _complete(
        bytes32 executionId,
        VAEKTypes.EffectHeader storage h,
        CommonRecord storage common,
        uint128 actualInput,
        uint128 actualOutput,
        bytes32 resultId,
        bytes32 executedHash,
        address adapter
    ) private {
        common.state = VAEKTypes.EffectState.EXECUTED;
        _executionLock = false;
        Verification memory verification = verifications[executionId];
        VAEKTypes.Receipt memory receipt;
        receipt.executionId = executionId;
        receipt.mandateId = h.mandateId;
        receipt.effectType = effectTypeOf[executionId];
        receipt.requestedHash = common.requestedHash;
        receipt.authorizedHash = common.authorizedHash;
        receipt.executedHash = executedHash;
        receipt.attenuationWitnessHash = common.witnessHash;
        receipt.policyHash = mandates[h.mandateId].policyHash;
        receipt.resourceRegistryVersion = common.resourceVersion;
        receipt.adapterAddress = adapter;
        receipt.adapterVersion = common.adapterVersion;
        receipt.adapterCodeHash = common.adapterCodeHash;
        receipt.riskTier = common.riskTier;
        receipt.verificationSetHash = verification.verificationSetHash;
        receipt.requestedAt = common.requestedAt;
        receipt.authorizedAt = common.authorizedAt;
        receipt.executedAt = uint64(block.timestamp);
        receipt.blockNumber = uint64(block.number);
        receipt.actualInput = actualInput;
        receipt.actualOutput = actualOutput;
        receipt.resultId = resultId;
        receipt.receiptHash = keccak256(abi.encode(RECEIPT_DOMAIN, block.chainid, address(this), receipt));
        _receipts[executionId] = receipt;
        emit ReceiptRecorded(executionId, receipt.receiptHash, executedHash);
    }

    function _register(
        bytes32 executionId,
        VAEKTypes.EffectType effectType,
        bytes32 requestedHash,
        bytes32 authorizedHash,
        VAEKTypes.EffectState state
    ) private {
        emit EffectRequested(executionId, effectType, requestedHash);
        VAEKTypes.DecisionCode decision = state == VAEKTypes.EffectState.ESCALATED
            ? VAEKTypes.DecisionCode.ESCALATE
            : (state == VAEKTypes.EffectState.AUTHORIZED_EXACT
                    ? VAEKTypes.DecisionCode.ALLOW_EXACT
                    : VAEKTypes.DecisionCode.ALLOW_ATTENUATED);
        emit EffectAuthorized(executionId, authorizedHash, decision);
    }

    function _common(
        bytes32 requestedHash,
        bytes32 authorizedHash,
        bytes32 witnessHash,
        AdapterRegistry.Entry memory adapter,
        VAEKTypes.RiskTier risk,
        bool exact
    ) private view returns (CommonRecord memory) {
        return CommonRecord({
            requestedHash: requestedHash,
            authorizedHash: authorizedHash,
            witnessHash: witnessHash,
            resourceVersion: resources.version(),
            adapterVersion: adapter.version,
            adapterCodeHash: adapter.codeHash,
            requestedAt: uint64(block.timestamp),
            authorizedAt: uint64(block.timestamp),
            riskTier: risk,
            state: exact ? VAEKTypes.EffectState.AUTHORIZED_EXACT : VAEKTypes.EffectState.AUTHORIZED_ATTENUATED
        });
    }

    function _authorizationHash(
        bytes32 requestedHash,
        bytes memory typedAuthorization,
        uint64 resourceVersion,
        AdapterRegistry.Entry memory adapter,
        VAEKTypes.RiskTier risk,
        bytes32 policyHash
    ) private view returns (bytes32) {
        return keccak256(
            abi.encode(
                AUTH_DOMAIN,
                block.chainid,
                address(this),
                SCHEMA_VERSION,
                requestedHash,
                typedAuthorization,
                resourceVersion,
                adapter.adapter,
                adapter.version,
                adapter.codeHash,
                risk,
                policyHash
            )
        );
    }

    function _witness(
        bytes32 requestedHash,
        bytes32 authorizedHash,
        uint128 requested,
        uint128 authorized,
        bytes32 reason
    ) private pure returns (bytes32) {
        VAEKTypes.AttenuationWitness memory witness = VAEKTypes.AttenuationWitness({
            requestedHash: requestedHash,
            authorizedHash: authorizedHash,
            fieldsChangedBitmap: requested == authorized ? 0 : 1,
            amountReduction: requested - authorized,
            deadlineReduction: 0,
            controlsAddedBitmap: 0,
            reasonCode: requested == authorized ? keccak256("EXACT") : reason
        });
        return keccak256(abi.encode("VAEK/ATTENUATION_WITNESS/R2", witness));
    }

    function _risk(
        VAEKTypes.EffectType effectType,
        uint128 value,
        Mandate storage mandate,
        VAEKTypes.RiskTier counterpartyTier
    ) private view returns (VAEKTypes.RiskTier) {
        return RiskEngine.compute(
            effectType,
            value,
            mandate.mediumThreshold,
            mandate.highThreshold,
            mandate.criticalThreshold,
            counterpartyTier,
            VAEKTypes.RiskTier.LOW,
            VAEKTypes.RiskTier.LOW,
            VAEKTypes.RiskTier.LOW
        );
    }

    function _authorizationState(bytes32 executionId)
        private
        view
        returns (bytes32 authorizationHash, uint64 deadline, VAEKTypes.EffectState state)
    {
        VAEKTypes.EffectType effectType = effectTypeOf[executionId];
        if (effectType == VAEKTypes.EffectType.TRANSFER_ERC20) {
            TransferRecord storage transferRecord = _transfers[executionId];
            return (transferRecord.common.authorizedHash, transferRecord.header.deadline, transferRecord.common.state);
        }
        if (effectType == VAEKTypes.EffectType.SWAP_EXACT_INPUT) {
            SwapRecord storage swapRecord = _swaps[executionId];
            return (swapRecord.common.authorizedHash, swapRecord.header.deadline, swapRecord.common.state);
        }
        ServiceRecord storage serviceRecord = _services[executionId];
        return (serviceRecord.common.authorizedHash, serviceRecord.header.deadline, serviceRecord.common.state);
    }

    function _setState(bytes32 executionId, VAEKTypes.EffectState state) private {
        VAEKTypes.EffectType effectType = effectTypeOf[executionId];
        if (effectType == VAEKTypes.EffectType.TRANSFER_ERC20) _transfers[executionId].common.state = state;
        else if (effectType == VAEKTypes.EffectType.SWAP_EXACT_INPUT) _swaps[executionId].common.state = state;
        else _services[executionId].common.state = state;
    }

    function _mandateId(bytes32 executionId) private view returns (bytes32) {
        VAEKTypes.EffectType effectType = effectTypeOf[executionId];
        if (effectType == VAEKTypes.EffectType.TRANSFER_ERC20) return _transfers[executionId].header.mandateId;
        if (effectType == VAEKTypes.EffectType.SWAP_EXACT_INPUT) return _swaps[executionId].header.mandateId;
        return _services[executionId].header.mandateId;
    }

    function _min3(uint128 a, uint128 b, uint128 c) private pure returns (uint128) {
        uint128 value = a < b ? a : b;
        return value < c ? value : c;
    }

    function _maxRisk(VAEKTypes.RiskTier a, VAEKTypes.RiskTier b) private pure returns (VAEKTypes.RiskTier) {
        return uint8(a) >= uint8(b) ? a : b;
    }
}
