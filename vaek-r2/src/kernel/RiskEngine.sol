// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity 0.8.24;

import {VAEKTypes} from "../VAEKTypes.sol";

library RiskEngine {
    function compute(
        VAEKTypes.EffectType effectType,
        uint128 value,
        uint128 mediumThreshold,
        uint128 highThreshold,
        uint128 criticalThreshold,
        VAEKTypes.RiskTier counterpartyTier,
        VAEKTypes.RiskTier stateTier,
        VAEKTypes.RiskTier freshnessTier,
        VAEKTypes.RiskTier modelReportedConcern
    ) internal pure returns (VAEKTypes.RiskTier tier) {
        tier = effectType == VAEKTypes.EffectType.TRANSFER_ERC20 ? VAEKTypes.RiskTier.LOW : VAEKTypes.RiskTier.MEDIUM;
        if (value >= criticalThreshold) tier = _max(tier, VAEKTypes.RiskTier.CRITICAL);
        else if (value >= highThreshold) tier = _max(tier, VAEKTypes.RiskTier.HIGH);
        else if (value >= mediumThreshold) tier = _max(tier, VAEKTypes.RiskTier.MEDIUM);
        tier = _max(tier, counterpartyTier);
        tier = _max(tier, stateTier);
        tier = _max(tier, freshnessTier);
        // INV-026: model signals can only maintain or raise deterministic risk.
        tier = _max(tier, modelReportedConcern);
    }

    function _max(VAEKTypes.RiskTier a, VAEKTypes.RiskTier b) private pure returns (VAEKTypes.RiskTier) {
        return uint8(a) >= uint8(b) ? a : b;
    }
}

