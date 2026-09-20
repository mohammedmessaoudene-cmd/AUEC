// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity 0.8.24;

import {VAEKTypes} from "../VAEKTypes.sol";

/// @notice RESEARCH PROTOTYPE — NOT AUDITED — NO PRODUCTION FUNDS.
contract ResourceRegistry {
    struct Resource {
        address account;
        VAEKTypes.ResourceKind kind;
        VAEKTypes.RiskTier riskTier;
        bool active;
    }

    address public immutable owner;
    uint64 public version = 1;
    mapping(bytes32 => Resource) private _resources;

    error NotOwner();
    error InvalidResource();

    event ResourceSet(
        bytes32 indexed id, address indexed account, VAEKTypes.ResourceKind kind, bool active, uint64 version
    );

    constructor(address owner_) {
        require(owner_ != address(0), "zero owner");
        owner = owner_;
    }

    function setResource(
        bytes32 id,
        address account,
        VAEKTypes.ResourceKind kind,
        VAEKTypes.RiskTier riskTier,
        bool active
    ) external {
        if (msg.sender != owner) revert NotOwner();
        if (id == bytes32(0) || account == address(0)) revert InvalidResource();
        unchecked {
            ++version;
        }
        _resources[id] = Resource(account, kind, riskTier, active);
        emit ResourceSet(id, account, kind, active, version);
    }

    function resolve(bytes32 id, VAEKTypes.ResourceKind expectedKind)
        external
        view
        returns (address account, VAEKTypes.RiskTier riskTier)
    {
        Resource memory r = _resources[id];
        if (!r.active || r.account == address(0) || r.kind != expectedKind) revert InvalidResource();
        return (r.account, r.riskTier);
    }
}

