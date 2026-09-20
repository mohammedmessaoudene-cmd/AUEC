// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity 0.8.24;

import {IERC20TransferAdapter} from "../interfaces/ITypedAdapters.sol";
import {TokenOps} from "../libraries/TokenOps.sol";

/// @notice Typed transfer boundary. No generic target, selector or payload is accepted.
contract ERC20TransferAdapter is IERC20TransferAdapter {
    address public immutable kernel;

    error NotKernel();
    error InvalidActual();

    constructor(address kernel_) {
        require(kernel_ != address(0), "zero kernel");
        kernel = kernel_;
    }

    function executeTransfer(address token, address recipient, uint128 amount)
        external
        returns (uint128 actualSpent, uint128 actualReceived)
    {
        if (msg.sender != kernel) revert NotKernel();
        uint256 kernelBefore = TokenOps.balanceOf(token, kernel);
        uint256 recipientBefore = TokenOps.balanceOf(token, recipient);
        TokenOps.safeTransferFrom(token, kernel, recipient, amount);
        uint256 kernelAfter = TokenOps.balanceOf(token, kernel);
        uint256 recipientAfter = TokenOps.balanceOf(token, recipient);
        if (kernelAfter > kernelBefore || recipientAfter < recipientBefore) revert InvalidActual();
        uint256 spent = kernelBefore - kernelAfter;
        uint256 received = recipientAfter - recipientBefore;
        if (
            spent == 0 || spent > amount || received > spent || spent > type(uint128).max
                || received > type(uint128).max
        ) {
            revert InvalidActual();
        }
        // Safe after the explicit type(uint128).max bounds above.
        // forge-lint: disable-next-line(unsafe-typecast)
        actualSpent = uint128(spent);
        // forge-lint: disable-next-line(unsafe-typecast)
        actualReceived = uint128(received);
    }
}
