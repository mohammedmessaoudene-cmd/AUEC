// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity 0.8.24;

import {IBoundedSwapAdapter, ITypedSwapVenue} from "../interfaces/ITypedAdapters.sol";
import {TokenOps} from "../libraries/TokenOps.sol";

/// @notice Two-asset exact-input adapter. No route bytes or multicall exists.
contract BoundedSwapAdapter is IBoundedSwapAdapter {
    address public immutable kernel;

    error NotKernel();
    error BoundsViolated();

    constructor(address kernel_) {
        require(kernel_ != address(0), "zero kernel");
        kernel = kernel_;
    }

    function executeSwap(
        address tokenIn,
        address tokenOut,
        address venue,
        address recipient,
        uint128 maxInput,
        uint128 minOutput
    ) external returns (uint128 actualInput, uint128 actualOutput) {
        if (msg.sender != kernel) revert NotKernel();
        uint256 kernelBefore = TokenOps.balanceOf(tokenIn, kernel);
        uint256 recipientBefore = TokenOps.balanceOf(tokenOut, recipient);
        TokenOps.safeTransferFrom(tokenIn, kernel, address(this), maxInput);
        TokenOps.safeApprove(tokenIn, venue, 0);
        TokenOps.safeApprove(tokenIn, venue, maxInput);
        (uint128 venueInput, uint128 venueOutput) =
            ITypedSwapVenue(venue).swapExactInput(tokenIn, tokenOut, maxInput, minOutput, recipient);
        TokenOps.safeApprove(tokenIn, venue, 0);
        uint256 kernelAfter = TokenOps.balanceOf(tokenIn, kernel);
        uint256 recipientAfter = TokenOps.balanceOf(tokenOut, recipient);
        if (kernelAfter > kernelBefore || recipientAfter < recipientBefore) revert BoundsViolated();
        uint256 measuredInput = kernelBefore - kernelAfter;
        uint256 measuredOutput = recipientAfter - recipientBefore;
        if (
            measuredInput == 0 || measuredInput > maxInput || measuredOutput < minOutput
                || measuredOutput > type(uint128).max || venueInput != measuredInput || venueOutput != measuredOutput
        ) revert BoundsViolated();
        // Safe: measuredInput <= uint128 maxInput and measuredOutput was explicitly bounded above.
        // forge-lint: disable-next-line(unsafe-typecast)
        actualInput = uint128(measuredInput);
        // forge-lint: disable-next-line(unsafe-typecast)
        actualOutput = uint128(measuredOutput);
    }
}
