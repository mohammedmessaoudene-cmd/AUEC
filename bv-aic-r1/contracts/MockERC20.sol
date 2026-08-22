// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

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

    function transfer(address to, uint256 amount) external returns (bool) {
        require(balanceOf[msg.sender] >= amount, "balance");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        emit Transfer(msg.sender, to, amount);
        return true;
    }
}

contract MockFalseERC20 {
    mapping(address => uint256) public balanceOf;
    function mint(address to, uint256 amount) external { balanceOf[to] += amount; }
    function transfer(address, uint256) external pure returns (bool) { return false; }
}

interface IAuthorityExecute { function execute(bytes32 executionId) external; }

contract MockReentrantERC20 {
    mapping(address => uint256) public balanceOf;
    address public authority;
    bytes32 public reentryId;
    bool public attackEnabled;
    bool public reentrySucceeded;

    function configureAttack(address authority_, bytes32 reentryId_) external {
        authority = authority_;
        reentryId = reentryId_;
        attackEnabled = true;
    }

    function mint(address to, uint256 amount) external { balanceOf[to] += amount; }

    function transfer(address to, uint256 amount) external returns (bool) {
        require(balanceOf[msg.sender] >= amount, "balance");
        if (attackEnabled) {
            (reentrySucceeded,) = authority.call(abi.encodeCall(IAuthorityExecute.execute, (reentryId)));
        }
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}
