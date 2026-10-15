package com.pokecollector.app.data

import com.pokecollector.app.data.api.ApiCard

/** A single market price for one print variant of a card. */
data class VariantPrice(
    val variant: String,
    val label: String,
    val market: Double?,
    val low: Double?,
    val mid: Double?,
    val high: Double?,
)

object Pricing {
    /** Display order: most common prints first. */
    private val ORDER = listOf(
        "normal", "holofoil", "reverseHolofoil",
        "1stEditionNormal", "1stEditionHolofoil", "unlimitedHolofoil", "unlimited",
    )

    fun label(variant: String): String = when (variant) {
        "normal" -> "Normal"
        "holofoil" -> "Holofoil"
        "reverseHolofoil" -> "Reverse Holo"
        "1stEditionNormal" -> "1st Edition"
        "1stEditionHolofoil" -> "1st Edition Holo"
        "unlimitedHolofoil" -> "Unlimited Holo"
        "unlimited" -> "Unlimited"
        else -> variant.replace(Regex("([a-z])([A-Z])"), "$1 $2")
            .replaceFirstChar { it.uppercase() }
    }

    /** TCGplayer prices (USD) for every variant the card is printed in. */
    fun variants(card: ApiCard): List<VariantPrice> =
        card.tcgplayer?.prices.orEmpty()
            .map { (k, p) -> VariantPrice(k, label(k), p.market, p.low, p.mid, p.high) }
            .sortedBy { ORDER.indexOf(it.variant).let { i -> if (i < 0) ORDER.size else i } }

    /** Default variant to record when the user adds a card. */
    fun defaultVariant(card: ApiCard): String =
        variants(card).firstOrNull { it.market != null }?.variant
            ?: variants(card).firstOrNull()?.variant
            ?: "normal"

    /**
     * Typical market value in USD for [variant]: TCGplayer market price, falling back to
     * TCGplayer mid, then any other variant's market price. Null when the card has no USD data.
     */
    fun marketUsd(card: ApiCard, variant: String): Double? {
        val prices = card.tcgplayer?.prices.orEmpty()
        prices[variant]?.let { p -> (p.market ?: p.mid)?.let { return it } }
        return variants(card).firstNotNullOfOrNull { it.market ?: it.mid }
    }

    /** Cardmarket (European) trend price in EUR, as a second opinion. */
    fun trendEur(card: ApiCard, variant: String): Double? {
        val p = card.cardmarket?.prices ?: return null
        val v = if (variant == "reverseHolofoil") p.reverseHoloTrend else p.trendPrice
        return (v ?: p.trendPrice ?: p.averageSellPrice)?.takeIf { it > 0.0 }
    }
}
