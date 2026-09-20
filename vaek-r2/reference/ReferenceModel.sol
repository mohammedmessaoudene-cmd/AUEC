// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity 0.8.24;

import {VAEKTypes} from "../src/VAEKTypes.sol";

/// @notice Deliberately small independent model for differential tests.
contract ReferenceModel {
    function authorizeTransfer(uint128 requested, uint128 perEffectCap, uint128 aggregateRemaining)
        external
        pure
        returns (uint128 authorized)
    {
        authorized = requested < perEffectCap ? requested : perEffectCap;
        if (aggregateRemaining < authorized) authorized = aggregateRemaining;
    }

    function risk(
        VAEKTypes.EffectType effectType,
        uint128 value,
        uint128 mediumThreshold,
        uint128 highThreshold,
        uint128 criticalThreshold,
        VAEKTypes.RiskTier externalTier,
        VAEKTypes.RiskTier modelConcern
    ) external pure returns (VAEKTypes.RiskTier result) {
        result = effectType == VAEKTypes.EffectType.TRANSFER_ERC20
            ? VAEKTypes.RiskTier.LOW
            : VAEKTypes.RiskTier.MEDIUM;
        if (value >= criticalThreshold) result = VAEKTypes.RiskTier.CRITICAL;
        else if (value >= highThreshold && uint8(result) < uint8(VAEKTypes.RiskTier.HIGH)) result = VAEKTypes.RiskTier.HIGH;
        else if (value >= mediumThreshold && uint8(result) < uint8(VAEKTypes.RiskTier.MEDIUM)) {
            result = VAEKTypes.RiskTier.MEDIUM;
        }
        if (uint8(externalTier) > uint8(result)) result = externalTier;
        if (uint8(modelConcern) > uint8(result)) result = modelConcern;
    }
}

