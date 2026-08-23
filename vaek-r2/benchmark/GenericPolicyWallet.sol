// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity 0.8.24;

/// @notice Fair generic target+calldata comparator. Intentionally outside the VAEK execution path.
contract GenericPolicyWallet {
    struct Rule {
        bool allowed;
        bool inspectERC20Transfer;
        address allowedRecipient;
        uint128 semanticCap;
    }

    address public immutable owner;
    address public immutable agent;
    uint128 public immutable aggregateCap;
    uint128 public spent;
    uint64 public immutable validUntil;
    mapping(bytes32 => Rule) public rules;
    mapping(bytes32 => bool) public consumed;

    error Unauthorized();
    error PolicyBlocked();

    event GenericExecution(bytes32 indexed executionId, address indexed target, bytes4 selector, bytes32 calldataHash);

    constructor(address agent_, uint128 aggregateCap_, uint64 validUntil_) {
        owner = msg.sender;
        agent = agent_;
        aggregateCap = aggregateCap_;
        validUntil = validUntil_;
    }

    function setRule(
        address target,
        bytes4 selector,
        bool inspectERC20Transfer,
        address allowedRecipient,
        uint128 semanticCap
    ) external {
        if (msg.sender != owner) revert Unauthorized();
        rules[keccak256(abi.encode(target, selector))] =
            Rule(true, inspectERC20Transfer, allowedRecipient, semanticCap);
    }

    function execute(bytes32 executionId, address target, uint256 value, bytes calldata data)
        external
        returns (bytes memory result)
    {
        if (msg.sender != agent) revert Unauthorized();
        if (consumed[executionId] || block.timestamp > validUntil || data.length < 4) revert PolicyBlocked();
        bytes4 selector = bytes4(data[:4]);
        Rule memory rule = rules[keccak256(abi.encode(target, selector))];
        if (!rule.allowed || value > rule.semanticCap) revert PolicyBlocked();
        uint128 semanticAmount = uint128(value);
        if (rule.inspectERC20Transfer) {
            if (data.length != 68) revert PolicyBlocked();
            (address recipient, uint256 amount) = abi.decode(data[4:], (address, uint256));
            if (recipient != rule.allowedRecipient || amount > rule.semanticCap || amount > type(uint128).max) {
                revert PolicyBlocked();
            }
            semanticAmount = uint128(amount);
        }
        if (spent + semanticAmount > aggregateCap) revert PolicyBlocked();
        consumed[executionId] = true;
        spent += semanticAmount;
        (bool ok, bytes memory returned) = target.call{value: value}(data);
        if (!ok) revert PolicyBlocked();
        emit GenericExecution(executionId, target, selector, keccak256(data));
        return returned;
    }

    receive() external payable {}
}

contract MockNestedTarget {
    address public lastTarget;
    bytes4 public lastSelector;

    function multicall(address nestedTarget, bytes calldata nestedData) external {
        lastTarget = nestedTarget;
        lastSelector = bytes4(nestedData[:4]);
    }
}

contract MockMutableSemanticTarget {
    bool public maliciousMode;
    uint256 public benignCalls;
    uint256 public maliciousCalls;

    function setMaliciousMode(bool value) external {
        maliciousMode = value;
    }

    function act() external {
        if (maliciousMode) ++maliciousCalls;
        else ++benignCalls;
    }
}

