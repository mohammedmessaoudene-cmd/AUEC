// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity 0.8.24;

import {VAEKTypes} from "../VAEKTypes.sol";

/// @notice Kernel-controlled adapter catalog with explicit version and runtime-code binding.
contract AdapterRegistry {
    struct Entry {
        address adapter;
        uint64 version;
        bytes32 codeHash;
        bool active;
    }

    struct PendingEntry {
        address adapter;
        uint64 activateAfter;
    }

    address public immutable owner;
    mapping(VAEKTypes.EffectType => Entry) private _entries;
    mapping(VAEKTypes.EffectType => PendingEntry) public pending;

    error NotOwner();
    error InvalidAdapter();
    error TimelockPending();

    event AdapterSet(
        VAEKTypes.EffectType indexed effectType, address indexed adapter, uint64 version, bytes32 codeHash
    );
    event AdapterScheduled(VAEKTypes.EffectType indexed effectType, address indexed adapter, uint64 activateAfter);

    constructor(address owner_) {
        require(owner_ != address(0), "zero owner");
        owner = owner_;
    }

    function setAdapter(VAEKTypes.EffectType effectType, address adapter) external {
        if (msg.sender != owner) revert NotOwner();
        if (adapter == address(0) || adapter.code.length == 0) revert InvalidAdapter();
        if (_entries[effectType].version != 0) revert TimelockPending();
        bytes32 codeHash = adapter.codehash;
        _entries[effectType] = Entry(adapter, 1, codeHash, true);
        emit AdapterSet(effectType, adapter, 1, codeHash);
    }

    function scheduleAdapter(VAEKTypes.EffectType effectType, address adapter) external {
        if (msg.sender != owner) revert NotOwner();
        if (adapter == address(0) || adapter.code.length == 0 || _entries[effectType].version == 0) {
            revert InvalidAdapter();
        }
        uint64 activateAfter = uint64(block.timestamp + 1 hours);
        pending[effectType] = PendingEntry(adapter, activateAfter);
        emit AdapterScheduled(effectType, adapter, activateAfter);
    }

    function activateAdapter(VAEKTypes.EffectType effectType) external {
        if (msg.sender != owner) revert NotOwner();
        PendingEntry memory candidate = pending[effectType];
        if (candidate.adapter == address(0) || block.timestamp < candidate.activateAfter) revert TimelockPending();
        Entry memory old = _entries[effectType];
        bytes32 codeHash = candidate.adapter.codehash;
        _entries[effectType] = Entry(candidate.adapter, old.version + 1, codeHash, true);
        delete pending[effectType];
        emit AdapterSet(effectType, candidate.adapter, old.version + 1, codeHash);
    }

    function disable(VAEKTypes.EffectType effectType) external {
        if (msg.sender != owner) revert NotOwner();
        Entry storage entry = _entries[effectType];
        entry.active = false;
        unchecked {
            ++entry.version;
        }
    }

    function get(VAEKTypes.EffectType effectType) external view returns (Entry memory entry) {
        entry = _entries[effectType];
        if (!entry.active || entry.adapter == address(0) || entry.adapter.codehash != entry.codeHash) {
            revert InvalidAdapter();
        }
    }
}
