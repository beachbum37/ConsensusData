package com.pokecollector.app.scan

/** What could be read off a card photo. */
data class ScanClues(
    /** Collector number in API form: "25", "TG05", "SWSH050". */
    val number: String? = null,
    /** Printed set size from "025/198", when the number is a plain numeric one. */
    val setTotal: Int? = null,
    val hp: Int? = null,
    /** Possible card names, most likely first. */
    val names: List<String> = emptyList(),
) {
    val isEmpty get() = number == null && names.isEmpty()

    /** Identity used to decide whether two frames saw the same card. */
    val key get() = "${number.orEmpty()}/${setTotal ?: ""}|${names.firstOrNull().orEmpty().lowercase()}"
}

/**
 * Turns raw OCR lines (top-to-bottom) from a Pokémon card into lookup clues.
 * Pure Kotlin so it can be unit-tested without a device.
 */
object CardTextParser {

    // "025/198", "4/102", "TG05/TG30", "GG01/GG70", "SV001/SV122", "201/198".
    // OCR often reads 0 as O and 1 as I or l, so those are accepted inside the digits.
    private val SLASH_NUMBER = Regex(
        """(?<![A-Za-z0-9])([A-Z]{0,3}?)([0-9OIl]{1,3})\s*/\s*([A-Z]{0,3}?)([0-9OIl]{2,3})(?![0-9])"""
    )

    // Black Star promos printed without a slash: "SWSH050", "SM60", "XY124", "BW45".
    private val PROMO_NUMBER = Regex("""(?<![A-Za-z])(SWSH|SM|XY|BW)\s?(\d{2,3})(?!\d)""")

    private val HP = Regex("""(?:HP\s*(\d{2,3}))|(?:(\d{2,3})\s*HP)""", RegexOption.IGNORE_CASE)

    private val NAME_CHARS = Regex("""^[A-Za-zÀ-ÿ'’.\- ♀♂]+$""")

    /** Card furniture that is never a card name. */
    private val STOP_WORDS = setOf(
        "basic", "stage", "stage 1", "stage 2", "evolves from", "trainer", "item", "supporter",
        "stadium", "energy", "pokémon tool", "pokemon tool", "weakness", "resistance",
        "retreat", "retreat cost", "illus", "pokémon", "pokemon", "ability", "poké-power",
        "poké-body", "tera", "rule", "length", "weight", "nintendo", "creatures",
        "game freak", "special energy", "basic energy", "v rule", "vmax rule", "ex rule",
        "put", "attach", "flip", "discard", "search", "draw", "your", "this", "the",
        "damage", "opponent", "opponent's", "active", "bench", "benched", "heads", "tails",
    )

    fun parse(lines: List<String>): ScanClues {
        val text = lines.joinToString("\n")
        val (number, total) = findNumber(text)
        val hp = HP.find(text)?.let { m -> (m.groupValues[1].ifEmpty { m.groupValues[2] }).toIntOrNull() }
        return ScanClues(number = number, setTotal = total, hp = hp, names = findNames(lines))
    }

    private fun findNumber(text: String): Pair<String?, Int?> {
        SLASH_NUMBER.findAll(text).forEach { m ->
            var (prefix, rawNum, totalPrefix, rawTotal) = m.destructured
            // A "prefix" made only of O/I is a misread digit ("IO2" is 102), not a subset code.
            if (prefix.all { it in "OI" }) { rawNum = prefix + rawNum; prefix = "" }
            if (totalPrefix.all { it in "OI" }) { rawTotal = totalPrefix + rawTotal; totalPrefix = "" }
            val num = fixDigits(rawNum)
            val tot = fixDigits(rawTotal)
            if (num.isEmpty() || tot.isEmpty()) return@forEach
            if (prefix.isNotEmpty()) {
                // Subset numbering (TG05/TG30): the API keeps the prefix and padding.
                return "$prefix$num" to null
            }
            val n = num.toInt()
            val t = tot.toInt()
            // Secret rares can run well past the printed total (Paldean Fates: 245/091).
            if (n == 0 || t < 2 || n > 400) return@forEach
            return n.toString() to (if (totalPrefix.isEmpty()) t else null)
        }
        PROMO_NUMBER.find(text)?.let { m -> return (m.groupValues[1] + m.groupValues[2]) to null }
        return null to null
    }

    private fun fixDigits(s: String): String =
        s.map { when (it) { 'O' -> '0'; 'I', 'l' -> '1'; else -> it } }
            .joinToString("")
            .takeIf { it.all(Char::isDigit) }
            .orEmpty()

    private fun findNames(lines: List<String>): List<String> {
        val out = LinkedHashSet<String>()
        for (raw in lines) {
            // "Pikachu HP60" / "Charizard ex 330 HP" -> drop the HP part.
            val line = raw.replace(HP, " ").replace(Regex("""\s+"""), " ").trim()
            if (line.length !in 3..28) continue
            if (!NAME_CHARS.matches(line)) continue
            val lower = line.lowercase()
            if (lower in STOP_WORDS) continue
            if (STOP_WORDS.any { lower.startsWith("$it ") && it.length > 4 }) continue
            if (line.count(Char::isLetter) < 3) continue
            // Rules text is long sentences; names are at most a few words.
            if (line.split(' ').size > 4) continue
            out += line
            if (out.size >= 5) break
        }
        return out.toList()
    }
}

/** Fuzzy name match in [0,1], tolerant of OCR slips and "ex"/"V" suffix noise. */
object NameMatch {
    fun score(a: String, b: String): Double {
        val x = norm(a)
        val y = norm(b)
        if (x.isEmpty() || y.isEmpty()) return 0.0
        if (x == y) return 1.0
        if (x.startsWith(y) || y.startsWith(x)) return 0.9
        val d = levenshtein(x, y)
        return 1.0 - d.toDouble() / maxOf(x.length, y.length)
    }

    private fun norm(s: String) = s.lowercase()
        .replace('é', 'e')
        .filter { it.isLetterOrDigit() }

    private fun levenshtein(a: String, b: String): Int {
        var prev = IntArray(b.length + 1) { it }
        for (i in 1..a.length) {
            val cur = IntArray(b.length + 1)
            cur[0] = i
            for (j in 1..b.length) {
                val cost = if (a[i - 1] == b[j - 1]) 0 else 1
                cur[j] = minOf(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            }
            prev = cur
        }
        return prev[b.length]
    }
}
