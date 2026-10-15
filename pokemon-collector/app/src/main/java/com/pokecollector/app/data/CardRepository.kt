package com.pokecollector.app.data

import com.pokecollector.app.data.api.ApiCard
import com.pokecollector.app.data.api.PokemonTcgApi
import com.pokecollector.app.data.db.CollectionDao
import com.pokecollector.app.data.db.OwnedCard
import com.pokecollector.app.scan.CardTextParser
import com.pokecollector.app.scan.NameMatch
import com.pokecollector.app.scan.ScanClues
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

class CardRepository(
    private val api: PokemonTcgApi,
    private val dao: CollectionDao,
) {
    val collection: Flow<List<OwnedCard>> = dao.observeAll()

    fun owned(cardId: String): Flow<List<OwnedCard>> =
        dao.observeAll().map { all -> all.filter { it.cardId == cardId } }

    suspend fun card(id: String): ApiCard = api.card(id).data

    /** Best matches for what the camera read, most likely first. */
    suspend fun identify(clues: ScanClues): List<ApiCard> {
        clues.number?.let { number ->
            val byNumber = buildString {
                append("number:\"").append(number).append('"')
                clues.setTotal?.let { append(" set.printedTotal:").append(it) }
            }
            var hits = api.search(byNumber).data
            // The printed total is the part OCR most often garbles; retry on the number alone.
            if (hits.isEmpty() && clues.setTotal != null) {
                hits = api.search("number:\"$number\"", pageSize = 100).data
            }
            if (hits.isNotEmpty()) return rank(hits, clues)
        }
        for (name in clues.names.take(3)) {
            val hits = api.search("name:\"${escape(name)}\"").data
            if (hits.isNotEmpty()) return rank(hits, clues)
        }
        return emptyList()
    }

    /** Free-text search: a name ("charizard ex"), a number ("4/102"), or both. */
    suspend fun search(text: String): List<ApiCard> {
        val t = text.trim()
        if (t.isEmpty()) return emptyList()
        val clues = CardTextParser.parse(listOf(t))
        if (clues.number != null) {
            val name = t.replace(Regex("""\S*\d+\s*/\s*\S*\d+\S*|(SWSH|SM|XY|BW)\s?\d+"""), "").trim()
            return identify(clues.copy(names = listOfNotNull(name.ifEmpty { null })))
        }
        // One unquoted prefix term per word: "charizard ex" -> name:charizard* name:ex*
        // (the API rejects wildcards inside quoted phrases).
        val terms = t.split(Regex("""\s+"""))
            .map { it.filter { c -> c.isLetterOrDigit() || c == '-' || c == '\'' } }
            .filter { it.isNotEmpty() }
        if (terms.isEmpty()) return emptyList()
        return api.search(terms.joinToString(" ") { "name:$it*" }, pageSize = 60).data
    }

    private fun rank(cards: List<ApiCard>, clues: ScanClues): List<ApiCard> {
        if (clues.names.isEmpty() && clues.hp == null) return cards
        return cards.sortedByDescending { card ->
            val nameScore = clues.names.maxOfOrNull { NameMatch.score(it, card.name) } ?: 0.0
            val hpBonus = if (clues.hp != null && card.hp == clues.hp.toString()) 0.3 else 0.0
            nameScore + hpBonus
        }
    }

    private fun escape(s: String) = s.replace("\\", "").replace("\"", "")

    suspend fun add(card: ApiCard, variant: String, quantity: Int = 1) {
        val now = System.currentTimeMillis()
        val existing = dao.find(card.id, variant)
        if (existing != null) {
            dao.update(existing.copy(quantity = existing.quantity + quantity).withPrices(card, now))
        } else {
            dao.insert(
                OwnedCard(
                    cardId = card.id,
                    name = card.name,
                    number = card.number,
                    setName = card.set.name,
                    setTotal = card.set.printedTotal,
                    rarity = card.rarity,
                    imageSmall = card.images.small,
                    imageLarge = card.images.large,
                    variant = variant,
                    quantity = quantity,
                    priceUsd = null,
                    priceEur = null,
                    tcgplayerUrl = null,
                    priceUpdatedAt = now,
                    addedAt = now,
                ).withPrices(card, now)
            )
        }
    }

    suspend fun setQuantity(item: OwnedCard, quantity: Int) {
        if (quantity <= 0) dao.delete(item) else dao.update(item.copy(quantity = quantity))
    }

    /** Re-fetches market prices for everything in the collection. Returns how many cards updated. */
    suspend fun refreshPrices(): Int {
        val now = System.currentTimeMillis()
        var updated = 0
        dao.all().groupBy { it.cardId }.forEach { (id, rows) ->
            val card = runCatching { card(id) }.getOrNull() ?: return@forEach
            rows.forEach { dao.update(it.withPrices(card, now)) }
            updated++
        }
        return updated
    }

    private fun OwnedCard.withPrices(card: ApiCard, now: Long) = copy(
        priceUsd = Pricing.marketUsd(card, variant),
        priceEur = Pricing.trendEur(card, variant),
        tcgplayerUrl = card.tcgplayer?.url,
        priceUpdatedAt = now,
    )
}
