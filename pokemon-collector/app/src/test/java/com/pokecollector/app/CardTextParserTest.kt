package com.pokecollector.app

import com.pokecollector.app.scan.CardTextParser
import com.pokecollector.app.scan.NameMatch
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class CardTextParserTest {

    @Test fun modernCard() {
        val c = CardTextParser.parse(
            listOf(
                "BASIC", "Pikachu", "HP 60", "Gnaw 20",
                "Weakness", "Retreat", "Illus. Naoki Saito", "SVI EN 063/198 ●",
            )
        )
        assertEquals("63", c.number)
        assertEquals(198, c.setTotal)
        assertEquals(60, c.hp)
        assertEquals("Pikachu", c.names.first())
    }

    @Test fun nameAndHpOnOneLine() {
        val c = CardTextParser.parse(listOf("STAGE 2", "Charizard ex 330 HP", "Evolves from Charmeleon", "125/197"))
        assertEquals("Charizard ex", c.names.first())
        assertEquals(330, c.hp)
        assertEquals("125", c.number)
        assertEquals(197, c.setTotal)
    }

    @Test fun vintageCardWithOcrSlips() {
        val c = CardTextParser.parse(listOf("Charizard", "120 HP", "4/IO2"))
        assertEquals("4", c.number)
        assertEquals(102, c.setTotal)
    }

    @Test fun secretRareAboveTotal() {
        val c = CardTextParser.parse(listOf("Mew ex", "232/091"))
        assertEquals("232", c.number)
        assertEquals(91, c.setTotal)
    }

    @Test fun trainerGallerySubset() {
        val c = CardTextParser.parse(listOf("Zekrom", "TG05/TG30"))
        assertEquals("TG05", c.number)
        assertNull(c.setTotal)
    }

    @Test fun blackStarPromo() {
        val c = CardTextParser.parse(listOf("Pikachu V", "SWSH061"))
        assertEquals("SWSH061", c.number)
    }

    @Test fun rulesTextIsNotAName() {
        val c = CardTextParser.parse(
            listOf("Search your deck for a card and put it into your hand.", "Professor's Research", "Trainer")
        )
        assertEquals(listOf("Professor's Research"), c.names)
    }

    @Test fun nothingReadable() {
        assertTrue(CardTextParser.parse(listOf("12", "@@")).isEmpty)
    }

    @Test fun fuzzyNames() {
        assertEquals(1.0, NameMatch.score("Pikachu", "pikachu"), 0.0)
        assertTrue(NameMatch.score("Pikachv", "Pikachu") > 0.8)
        assertTrue(NameMatch.score("Charizard", "Charizard ex") >= 0.9)
        assertTrue(NameMatch.score("Bulbasaur", "Mewtwo") < 0.3)
    }
}
