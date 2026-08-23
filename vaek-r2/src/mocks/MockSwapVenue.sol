// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity 0.8.24;

import {ITypedSwapVenue} from "../interfaces/ITypedAdapters.sol";
import {TokenOps} from "../libraries/TokenOps.sol";

contract MockSwapVenue is ITypedSwapVenue {
    uint128 public numerator = 2;
    uint128 public denominator = 1;
    bool public lieAboutOutput;

    function setRate(uint128 numerator_, uint128 denominator_) external {
        require(numerator_ > 0 && denominator_ > 0, "rate");
        numerator = numerator_;
        denominator = denominator_;
    }

    function setLieAboutOutput(bool value) external {
        lieAboutOutput = value;
    }

    function swapExactInput(address tokenIn, address tokenOut, uint128 amountIn, uint128 minOutput, address recipient)
        external
        returns (uint128 actualInput, uint128 actualOutput)
    {
        uint256 output = uint256(amountIn) * numerator / denominator;
        require(output >= minOutput && output <= type(uint128).max, "slippage");
        TokenOps.safeTransferFrom(tokenIn, msg.sender, address(this), amountIn);
        TokenOps.safeTransfer(tokenOut, recipient, output);
        // Safe after output <= type(uint128).max above.
        // forge-lint: disable-next-line(unsafe-typecast)
        uint128 reportedOutput = uint128(output);
        if (lieAboutOutput) {
            require(reportedOutput < type(uint128).max, "mock overflow");
            ++reportedOutput;
        }
        return (amountIn, reportedOutput);
    }
}
