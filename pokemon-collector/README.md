# PokéCollector (Android)

Scan your Pokémon cards with the phone camera, see what each one typically sells for, and
keep a running value of your whole collection.

## What it does

| Tab | |
| --- | --- |
| **Scan** | Point the camera at a card. On-device text recognition (ML Kit) reads the collector number (`063/198`, `TG05/TG30`, `SWSH061`), the name and the HP. Once the same reading holds for a couple of frames, the app looks it up and shows the likely matches with prices. Tap **Add** to put it in your collection, or tap a card for details. |
| **Search** | For cards the camera can't read: type a name (`charizard ex`), a number (`4/102`), or both. |
| **Collection** | Total market value and card count, sortable by value, recency or name. **Refresh** re-prices everything. |
| **Card detail** | Large image, TCGplayer low / market / high for every print variant (normal, holo, reverse holo, 1st edition…), the Cardmarket EU trend price, a link to live TCGplayer listings, and +/- controls for the copies you own. |

**Where prices come from:** the [Pokémon TCG API](https://pokemontcg.io), which publishes
TCGplayer market prices (USD, updated daily) and Cardmarket prices (EUR). The "market value"
shown is TCGplayer's *market price*, meaning recent sold listings for near-mint copies. Graded
cards (PSA/BGS/CGC) and damaged cards sell for different amounts, so read the value as typical
raw near-mint.

Your collection is stored on the phone (Room/SQLite). No account needed.

## Build and install

You need Android Studio (Ladybug or newer) or JDK 17+ with the Android SDK (API 35).

1. Open the `pokemon-collector/` folder in Android Studio and let it sync. Or use the command line:
   ```
   cd pokemon-collector
   ./gradlew assembleDebug
   ```
2. Install on your phone: enable *Developer options → USB debugging*, plug in, and press Run.
   Or run `adb install app/build/outputs/apk/debug/app-debug.apk`.

### API key (recommended)

The app works without one, but the anonymous tier of the Pokémon TCG API is rate-limited and
often returns 502 errors. The app retries these, but lookups still go faster with a key. Get a
free key at <https://dev.pokemontcg.io> and add it to `pokemon-collector/local.properties`:

```
POKEMON_TCG_API_KEY=your-key-here
```

## Scanning tips

- One card, flat, filling the white frame, in good light. Glare on holos is the most common
  reason a scan fails. Tilt the card slightly to move the reflection.
- The bottom-left collector number is what identifies the exact printing. If the camera only
  catches the name, you'll get every printing of that Pokémon to choose from.
- Japanese and other non-English cards aren't in the price database.

## Project layout

```
app/src/main/java/com/pokecollector/app/
  scan/CardTextParser.kt   OCR text -> collector number, set size, name, HP (unit-tested)
  scan/CardTextAnalyzer.kt CameraX frames -> ML Kit text recognition
  data/CardRepository.kt   identify / search / add / re-price
  data/Pricing.kt          which price to show for which variant (unit-tested)
  data/api/                Retrofit client + models for api.pokemontcg.io
  data/db/                 Room database for your collection
  ui/                      Jetpack Compose screens
```

Run the tests with `./gradlew testDebugUnitTest`.

## Ideas for next steps

- Image-based matching (compare the artwork) for cards whose text is hard to read
- Condition and graded-card tracking, with price adjustments
- Value history chart, and alerts when a card's price jumps
- CSV export / import
