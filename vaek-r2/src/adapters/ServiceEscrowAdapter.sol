// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity 0.8.24;

import {IServiceEscrowAdapter} from "../interfaces/ITypedAdapters.sol";
import {TokenOps} from "../libraries/TokenOps.sol";

/// @notice Minimal typed escrow. It never invokes a provider callback.
contract ServiceEscrowAdapter is IServiceEscrowAdapter {
    enum JobState {
        NONE,
        FUNDED,
        SUBMITTED,
        COMPLETED,
        REJECTED,
        REFUNDED
    }

    struct Job {
        address token;
        address provider;
        address evaluator;
        uint128 amount;
        uint64 deadline;
        bytes32 deliveryCommitment;
        JobState state;
    }

    address public immutable kernel;
    uint64 public nextJobNonce;
    mapping(bytes32 => Job) public jobs;

    error NotKernel();
    error NotEvaluator();
    error InvalidTransition();

    event JobFunded(bytes32 indexed jobId, address indexed provider, uint128 amount);
    event JobSettled(bytes32 indexed jobId, JobState state);

    constructor(address kernel_) {
        require(kernel_ != address(0), "zero kernel");
        kernel = kernel_;
    }

    function createPurchase(
        address paymentToken,
        address provider,
        address evaluator,
        uint128 price,
        bytes32 deliveryCommitment,
        uint64 deadline
    ) external returns (bytes32 jobId, uint128 fundedAmount) {
        if (msg.sender != kernel) revert NotKernel();
        require(provider != evaluator && price > 0 && deadline > block.timestamp, "bad job");
        jobId = keccak256(abi.encode("VAEK/SERVICE_JOB/R2", block.chainid, address(this), ++nextJobNonce));
        uint256 beforeBalance = TokenOps.balanceOf(paymentToken, address(this));
        TokenOps.safeTransferFrom(paymentToken, kernel, address(this), price);
        uint256 afterBalance = TokenOps.balanceOf(paymentToken, address(this));
        require(afterBalance >= beforeBalance && afterBalance - beforeBalance == price, "unsupported token");
        jobs[jobId] = Job(paymentToken, provider, evaluator, price, deadline, deliveryCommitment, JobState.FUNDED);
        emit JobFunded(jobId, provider, price);
        return (jobId, price);
    }

    function submitDelivery(bytes32 jobId, bytes32 observedCommitment) external {
        Job storage job = jobs[jobId];
        if (msg.sender != job.provider || job.state != JobState.FUNDED || observedCommitment != job.deliveryCommitment)
        {
            revert InvalidTransition();
        }
        job.state = JobState.SUBMITTED;
    }

    function evaluate(bytes32 jobId, bool accept) external {
        Job storage job = jobs[jobId];
        if (msg.sender != job.evaluator) revert NotEvaluator();
        if (job.state != JobState.SUBMITTED) revert InvalidTransition();
        job.state = accept ? JobState.COMPLETED : JobState.REJECTED;
        TokenOps.safeTransfer(job.token, accept ? job.provider : kernel, job.amount);
        emit JobSettled(jobId, job.state);
    }

    function refundExpired(bytes32 jobId) external {
        Job storage job = jobs[jobId];
        if ((job.state != JobState.FUNDED && job.state != JobState.SUBMITTED) || block.timestamp <= job.deadline) {
            revert InvalidTransition();
        }
        job.state = JobState.REFUNDED;
        TokenOps.safeTransfer(job.token, kernel, job.amount);
        emit JobSettled(jobId, job.state);
    }
}

