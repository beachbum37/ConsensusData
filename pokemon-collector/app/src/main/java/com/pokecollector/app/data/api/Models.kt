package com.pokecollector.app.data.api

import kotlinx.serialization.Serializable

@Serializable
data class CardListResponse(
    val data: List<ApiCard> = emptyList(),
    val totalCount: Int = 0,
)

@Serializable
data class CardResponse(val data: ApiCard)

@Serializable
data class ApiCard(
    val id: String,
    val name: String,
    val number: String = "",
    val rarity: String? = null,
    val supertype: String? = null,
    val hp: String? = null,
    val set: ApiSet,
    val images: CardImages = CardImages(),
    val tcgplayer: TcgPlayer? = null,
    val cardmarket: CardMarket? = null,
)

@Serializable
data class ApiSet(
    val id: String,
    val name: String,
    val series: String = "",
    val printedTotal: Int = 0,
    val total: Int = 0,
    val releaseDate: String = "",
    val ptcgoCode: String? = null,
)

@Serializable
data class CardImages(val small: String = "", val large: String = "")

@Serializable
data class TcgPlayer(
    val url: String? = null,
    val updatedAt: String? = null,
    /** Keyed by print variant: normal, holofoil, reverseHolofoil, 1stEditionHolofoil, ... */
    val prices: Map<String, TcgPrice> = emptyMap(),
)

@Serializable
data class TcgPrice(
    val low: Double? = null,
    val mid: Double? = null,
    val high: Double? = null,
    val market: Double? = null,
    val directLow: Double? = null,
)

@Serializable
data class CardMarket(
    val url: String? = null,
    val updatedAt: String? = null,
    val prices: CardMarketPrices? = null,
)

@Serializable
data class CardMarketPrices(
    val averageSellPrice: Double? = null,
    val lowPrice: Double? = null,
    val trendPrice: Double? = null,
    val reverseHoloTrend: Double? = null,
    val avg7: Double? = null,
    val avg30: Double? = null,
)
