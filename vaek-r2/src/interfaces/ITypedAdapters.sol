// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity 0.8.24;

interface IERC20TransferAdapter {
    function executeTransfer(address token, address recipient, uint128 amount)
        external
        returns (uint128 actualSpent, uint128 actualReceived);
}

interface IBoundedSwapAdapter {
    function executeSwap(
        address tokenIn,
        address tokenOut,
        address venue,
        address recipient,
        uint128 maxInput,
        uint128 minOutput
    ) external returns (uint128 actualInput, uint128 actualOutput);
}

interface IServiceEscrowAdapter {
    function createPurchase(
        address paymentToken,
        address provider,
        address evaluator,
        uint128 price,
        bytes32 deliveryCommitment,
        uint64 deadline
    ) external returns (bytes32 jobId, uint128 fundedAmount);
}

interface ITypedSwapVenue {
    function swapExactInput(address tokenIn, address tokenOut, uint128 amountIn, uint128 minOutput, address recipient)
        external
        returns (uint128 actualInput, uint128 actualOutput);
}

