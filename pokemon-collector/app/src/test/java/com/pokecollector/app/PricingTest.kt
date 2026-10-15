package com.pokecollector.app

import com.pokecollector.app.data.Pricing
import com.pokecollector.app.data.api.ApiCard
import com.pokecollector.app.data.api.ApiSet
import com.pokecollector.app.data.api.CardMarket
import com.pokecollector.app.data.api.CardMarketPrices
import com.pokecollector.app.data.api.TcgPlayer
import com.pokecollector.app.data.api.TcgPrice
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PricingTest {
    private fun card(prices: Map<String, TcgPrice>, cm: CardMarketPrices? = null) = ApiCard(
        id = "x-1", name = "X", set = ApiSet("x", "X"),
        tcgplayer = TcgPlayer(prices = prices),
        cardmarket = cm?.let { CardMarket(prices = it) },
    )

    @Test fun picksRequestedVariant() {
        val c = card(mapOf("normal" to TcgPrice(market = 0.25), "reverseHolofoil" to TcgPrice(market = 1.10)))
        assertEquals(1.10, Pricing.marketUsd(c, "reverseHolofoil")!!, 0.0)
        assertEquals("normal", Pricing.defaultVariant(c))
    }

    @Test fun fallsBackToMidThenOtherVariant() {
        val c = card(mapOf("holofoil" to TcgPrice(mid = 3.0), "normal" to TcgPrice(market = 1.0)))
        assertEquals(3.0, Pricing.marketUsd(c, "holofoil")!!, 0.0)
        assertEquals(1.0, Pricing.marketUsd(c, "1stEditionHolofoil")!!, 0.0)
    }

    @Test fun noUsdData() {
        assertNull(Pricing.marketUsd(card(emptyMap()), "normal"))
    }

    @Test fun cardmarketTrend() {
        val c = card(emptyMap(), CardMarketPrices(trendPrice = 2.5, reverseHoloTrend = 4.0))
        assertEquals(4.0, Pricing.trendEur(c, "reverseHolofoil")!!, 0.0)
        assertEquals(2.5, Pricing.trendEur(c, "normal")!!, 0.0)
    }
}
