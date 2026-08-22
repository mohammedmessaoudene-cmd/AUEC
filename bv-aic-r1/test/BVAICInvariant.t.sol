// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "../contracts/BVAICAuthority.sol";
import "../contracts/MockERC20.sol";

contract AuthorityHandler {
    BVAICAuthority public auth;
    MockERC20 public token;
    bytes32 public mandateId;
    uint256 public nonce;

    address public constant VENDOR = address(0xC0FFEE);
    address public constant ATTACKER = address(0xBAD);
    bytes32 constant OBS = keccak256("inv:observation");
    bytes32 constant MODEL = keccak256("inv:model");
    bytes32 constant POLICY = keccak256("inv:policy");
    bytes32 constant EVIDENCE = keccak256("inv:evidence");

    constructor() {
        token = new MockERC20();
        auth = new BVAICAuthority(address(this));
        token.mint(address(auth), 1_000);
        address[] memory targets = new address[](1);
        targets[0] = VENDOR;
        mandateId = auth.createMandate(
            address(this), address(token), 100, 250, 50,
            uint64(block.timestamp), uint64(block.timestamp + 365 days), true, targets
        );
    }

    function step(uint128 amount, bool useAttacker, bool verifyIt, bool approveIt) external {
        // Exercise the meaningful policy space: 0, low-risk, high-risk, and over-limit.
        amount = uint128(uint256(amount) % 151);
        bytes32 id = keccak256(abi.encodePacked("inv", ++nonce));
        address target = useAttacker ? ATTACKER : VENDOR;
        uint64 dl = uint64(block.timestamp + 1 days);
        bytes32 h = auth.submitDecision(id, mandateId, target, address(token), amount, dl, OBS, MODEL, POLICY);
        if (verifyIt) {
            auth.recordVerification(id, h, BVAICAuthority.Verdict.PASS, EVIDENCE, dl);
        }
        if (approveIt) {
            auth.approveHighRisk(id);
        }
        (bool ok,) = address(auth).call(abi.encodeCall(BVAICAuthority.execute, (id)));
        ok; // intentionally ignored: blocked/escalated actions are expected
    }

    function revoke() external {
        auth.revokeMandate(mandateId);
    }
}

contract BVAICInvariantTest {
    AuthorityHandler handler;
    address[] private _targetedContracts;

    function setUp() public {
        handler = new AuthorityHandler();
        _targetedContracts.push(address(handler));
    }

    // Forge reads this configuration hook during invariant setup.
    function targetContracts() public view returns (address[] memory) {
        return _targetedContracts;
    }

    function invariant_AttackerNeverReceivesFunds() public view {
        require(handler.token().balanceOf(handler.ATTACKER()) == 0, "attacker received funds");
    }

    function invariant_SpentNeverExceedsMandateBudget() public view {
        require(handler.auth().spentOf(handler.mandateId()) <= 250, "budget exceeded");
    }

    function invariant_SpentEqualsVendorReceipts() public view {
        require(
            handler.auth().spentOf(handler.mandateId()) == handler.token().balanceOf(handler.VENDOR()),
            "accounting mismatch"
        );
    }

    function invariant_TokenConservation() public view {
        uint256 vault = handler.token().balanceOf(address(handler.auth()));
        uint256 vendor = handler.token().balanceOf(handler.VENDOR());
        uint256 attacker = handler.token().balanceOf(handler.ATTACKER());
        require(vault + vendor + attacker == 1_000, "token conservation broken");
    }
}
