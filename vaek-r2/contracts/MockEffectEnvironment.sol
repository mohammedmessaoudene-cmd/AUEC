// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IKernelReentry {
    function execute(bytes32 executionId) external returns (bytes32);
}

contract MockERC20 {
    string public name = "Mock USD";
    string public symbol = "mUSD";
    uint8 public decimals = 6;
    mapping(address => uint256) public balanceOf;
    event Transfer(address indexed from, address indexed to, uint256 value);

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
        emit Transfer(address(0), to, amount);
    }

    function transfer(address to, uint256 amount) external virtual returns (bool) {
        require(balanceOf[msg.sender] >= amount, "balance");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        emit Transfer(msg.sender, to, amount);
        return true;
    }
}

contract MockFeeERC20 is MockERC20 {
    function transfer(address to, uint256 amount) external override returns (bool) {
        require(balanceOf[msg.sender] >= amount, "balance");
        uint256 delivered = amount == 0 ? 0 : amount - 1;
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += delivered;
        emit Transfer(msg.sender, to, delivered);
        return true;
    }
}

contract MockPurchaseAdapter {
    uint256 public configuredCharge;
    bool public shouldRevert;
    address public reentryKernel;
    bytes32 public reentryExecutionId;
    bool public reentrySucceeded;

    function configure(uint256 charge, bool revert_, address kernel, bytes32 executionId) external {
        configuredCharge = charge;
        shouldRevert = revert_;
        reentryKernel = kernel;
        reentryExecutionId = executionId;
        reentrySucceeded = false;
    }

    function purchase(
        bytes32 executionId,
        address provider,
        bytes32 serviceId,
        address asset,
        uint256 maximumCharge,
        bytes32 contextHash
    ) external returns (uint256 actualCharge, bytes32 outcomeHash) {
        if (shouldRevert) revert("adapter failure");
        if (reentryKernel != address(0)) {
            (reentrySucceeded,) = reentryKernel.call(abi.encodeCall(IKernelReentry.execute, (reentryExecutionId)));
        }
        actualCharge = configuredCharge == 0 ? maximumCharge : configuredCharge;
        outcomeHash = keccak256(
            abi.encode(
                "VAEK/MOCK-PURCHASE-OUTCOME/R2", executionId, provider, serviceId, asset, actualCharge, contextHash
            )
        );
    }
}
