// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity 0.8.24;

/// @notice Restricted ERC-20 operations. Targets are registry-resolved by the kernel, never AI-provided call targets.
library TokenOps {
    error TokenCallFailed();
    error BalanceQueryFailed();

    function safeTransfer(address token, address to, uint256 amount) internal {
        _call(token, abi.encodeWithSelector(bytes4(keccak256("transfer(address,uint256)")), to, amount));
    }

    function safeTransferFrom(address token, address from, address to, uint256 amount) internal {
        _call(
            token, abi.encodeWithSelector(bytes4(keccak256("transferFrom(address,address,uint256)")), from, to, amount)
        );
    }

    function safeApprove(address token, address spender, uint256 amount) internal {
        _call(token, abi.encodeWithSelector(bytes4(keccak256("approve(address,uint256)")), spender, amount));
    }

    function balanceOf(address token, address account) internal view returns (uint256 result) {
        (bool ok, bytes memory ret) =
            token.staticcall(abi.encodeWithSelector(bytes4(keccak256("balanceOf(address)")), account));
        if (!ok || ret.length < 32) revert BalanceQueryFailed();
        result = abi.decode(ret, (uint256));
    }

    function _call(address token, bytes memory encodedTypedCall) private {
        (bool ok, bytes memory ret) = token.call(encodedTypedCall);
        if (!ok || (ret.length != 0 && (ret.length < 32 || !abi.decode(ret, (bool))))) revert TokenCallFailed();
    }
}

