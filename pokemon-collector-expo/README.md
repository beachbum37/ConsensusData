# PokéCollector (Expo)

Scan your Pokémon cards with the phone camera, see what each one typically sells for, and
keep a running value of your collection. This is the Expo / React Native version of
[`../pokemon-collector`](../pokemon-collector) (the native Kotlin app). It has the same
features and is built and installed through your expo.dev account.

| Tab | |
| --- | --- |
| **Scan** | Point the camera at a card. The app snaps a photo about once a second and reads the text on the phone with Google ML Kit: the collector number (`063/198`, `TG05/TG30`, `SWSH061`), the name and the HP. Once two photos agree, it looks the card up and shows likely matches with prices. Tap **Add** to put one in your collection. |
| **Search** | For cards the camera can't read: a name (`charizard ex`), a number (`4/102`), or both. |
| **Collection** | Total market value and card count, sortable. **Refresh** re-prices everything. |
| **Card** | Large image, TCGplayer low / market / high per print variant, Cardmarket EU trend, a link to TCGplayer listings, and +/- for the copies you own. |

Prices come from the [Pokémon TCG API](https://pokemontcg.io): TCGplayer market price (USD,
updated daily) and Cardmarket trend (EUR). The value shown is for raw near-mint copies.

## Install it on your phone with EAS Build

Card scanning uses a small native module (`modules/card-text`, Kotlin wrapping ML Kit), so
the app needs its own build. It can't run inside Expo Go. EAS builds an APK in Expo's cloud
and gives you a link and QR code on expo.dev to install it.

One-time setup, from this folder:

```sh
npm install
npx eas-cli@latest login          # or set EXPO_TOKEN (expo.dev → Account settings → Access tokens)
npx eas-cli@latest init           # creates the project on expo.dev and links it here
```

Build:

```sh
npm run build:apk                 # = eas build --platform android --profile preview
```

When the build finishes (about 10–20 minutes on the free tier, depending on the queue), open
the build page on expo.dev on your phone, or scan its QR code, and tap **Install**. Android
will ask you to allow installs from your browser the first time.

Later builds install over the top and keep your collection.

### Optional: API key

The anonymous Pokémon TCG API tier is rate-limited and often returns 502 errors. The app
retries these, but a free key from <https://dev.pokemontcg.io> makes lookups faster:

```sh
npx eas-cli env:create --name EXPO_PUBLIC_POKEMON_TCG_API_KEY --value <key> \
  --environment preview --visibility plaintext
```

Then rebuild.

## Develop

```sh
npm test            # parser + pricing unit tests (node:test)
npm run typecheck
npx expo lint
npx expo run:android   # local build onto a USB-connected phone (needs the Android SDK)
```

## Layout

```
src/app/                 screens (Expo Router): (tabs)/index, scan, search; card/[id]
src/lib/parser.ts        OCR text -> collector number, set size, name, HP (unit-tested)
src/lib/api.ts           card lookup + search against api.pokemontcg.io, with retries
src/lib/pricing.ts       which price to show for which variant (unit-tested)
src/lib/collection.tsx   your collection, saved on the phone (AsyncStorage)
modules/card-text/       local Expo module: ML Kit text recognition (Android)
```
