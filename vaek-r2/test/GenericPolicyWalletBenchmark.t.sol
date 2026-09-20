// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity 0.8.24;

import {GenericPolicyWallet, MockNestedTarget, MockMutableSemanticTarget} from "../benchmark/GenericPolicyWallet.sol";
import {MockERC20} from "../src/mocks/MockERC20.sol";

interface VmBenchmark {
    function prank(address) external;
    function expectRevert() external;
}

contract GenericPolicyWalletBenchmarkTest {
    VmBenchmark private constant vm = VmBenchmark(address(uint160(uint256(keccak256("hevm cheat code")))));
    address private constant AGENT = address(0xA11CE);
    address private constant RECIPIENT = address(0xCAFE);
    address private constant ATTACKER = address(0xBAD);

    GenericPolicyWallet private wallet;
    MockERC20 private token;

    function setUp() public {
        wallet = new GenericPolicyWallet(AGENT, 1_000, uint64(block.timestamp + 30 days));
        token = new MockERC20("PolicyToken", 6);
        token.mint(address(wallet), 1_000);
        wallet.setRule(address(token), token.transfer.selector, true, RECIPIENT, 100);
    }

    function test_FairBaselineAllowsParsedERC20Transfer() public {
        vm.prank(AGENT);
        wallet.execute(keccak256("valid"), address(token), 0, abi.encodeCall(token.transfer, (RECIPIENT, 50)));
        assert(token.balanceOf(RECIPIENT) == 50);
        assert(wallet.spent() == 50);
    }

    function test_FairBaselineBlocksRecipientSubstitution() public {
        vm.prank(AGENT);
        vm.expectRevert();
        wallet.execute(keccak256("substitute"), address(token), 0, abi.encodeCall(token.transfer, (ATTACKER, 50)));
    }

    function test_FairBaselineBlocksSemanticAmountAboveCap() public {
        vm.prank(AGENT);
        vm.expectRevert();
        wallet.execute(keccak256("over"), address(token), 0, abi.encodeCall(token.transfer, (RECIPIENT, 101)));
    }

    function test_AllowedMulticallLeavesNestedSelectorUninspected() public {
        MockNestedTarget nested = new MockNestedTarget();
        wallet.setRule(address(nested), nested.multicall.selector, false, address(0), 0);
        bytes memory forbiddenNested = abi.encodeWithSignature("drain(address,uint256)", ATTACKER, 100);
        vm.prank(AGENT);
        wallet.execute(
            keccak256("nested"), address(nested), 0, abi.encodeCall(nested.multicall, (address(token), forbiddenNested))
        );
        assert(nested.lastTarget() == address(token));
        assert(nested.lastSelector() == bytes4(keccak256("drain(address,uint256)")));
    }

    function test_SameAllowedTargetAndSelectorCanChangeSemantics() public {
        MockMutableSemanticTarget target = new MockMutableSemanticTarget();
        wallet.setRule(address(target), target.act.selector, false, address(0), 0);
        vm.prank(AGENT);
        wallet.execute(keccak256("before"), address(target), 0, abi.encodeCall(target.act, ()));
        target.setMaliciousMode(true);
        vm.prank(AGENT);
        wallet.execute(keccak256("after"), address(target), 0, abi.encodeCall(target.act, ()));
        assert(target.benignCalls() == 1 && target.maliciousCalls() == 1);
    }

    function test_ReplayProtectionIsPresent() public {
        bytes32 executionId = keccak256("replay");
        vm.prank(AGENT);
        wallet.execute(executionId, address(token), 0, abi.encodeCall(token.transfer, (RECIPIENT, 10)));
        vm.prank(AGENT);
        vm.expectRevert();
        wallet.execute(executionId, address(token), 0, abi.encodeCall(token.transfer, (RECIPIENT, 10)));
    }
}

