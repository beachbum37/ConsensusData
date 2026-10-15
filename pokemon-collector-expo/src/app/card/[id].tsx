import MaterialIcons from '@expo/vector-icons/MaterialIcons';
import { Image } from 'expo-image';
import { Stack, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Linking, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { getCard } from '../../lib/api';
import { useCollection } from '../../lib/collection';
import { eur, usd } from '../../lib/format';
import { defaultVariant, marketUsd, trendEur, variantLabel, variants } from '../../lib/pricing';
import { colors } from '../../lib/theme';
import type { ApiCard } from '../../lib/types';

export default function CardDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [card, setCard] = useState<ApiCard | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let alive = true;
    getCard(id).then(
      (c) => { if (alive) setCard(c); },
      () => { if (alive) setError(true); },
    );
    return () => { alive = false; };
  }, [id, attempt]);

  function retry() {
    setError(false);
    setCard(null);
    setAttempt((n) => n + 1);
  }

  if (error) {
    return (
      <View style={styles.center}>
        <Text>{"Couldn't load this card."}</Text>
        <Pressable style={styles.button} onPress={retry}><Text style={styles.buttonText}>Retry</Text></Pressable>
      </View>
    );
  }
  if (!card) return <View style={styles.center}><ActivityIndicator color={colors.primary} /></View>;
  return <Detail card={card} />;
}

function Detail({ card }: { card: ApiCard }) {
  const { items, add, setQuantity } = useCollection();
  const vs = variants(card);
  const [variant, setVariant] = useState(defaultVariant(card));
  const owned = items.filter((i) => i.cardId === card.id);
  const eurTrend = trendEur(card, variant);
  const options = vs.length ? vs.map((v) => v.variant) : ['normal'];

  return (
    <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 40 }}>
      <Stack.Screen options={{ title: card.name }} />
      <Image source={card.images.large} style={styles.image} contentFit="contain" transition={200} />
      <Text style={styles.title}>{card.name}</Text>
      <Text style={styles.muted}>
        {card.set.name} ({card.set.series}) · {card.number}/{card.set.printedTotal}
        {card.rarity ? ` · ${card.rarity}` : ''}
      </Text>

      <View style={styles.box}>
        <Text style={styles.h2}>Market value</Text>
        <Text style={styles.big}>{usd(marketUsd(card, variant))}</Text>
        <Text style={styles.muted}>TCGplayer market · {variantLabel(variant)}</Text>
        {vs.length > 0 ? (
          <View style={{ marginTop: 12 }}>
            <PriceRow cells={['Variant', 'Low', 'Market', 'High']} header />
            {vs.map((v) => <PriceRow key={v.variant} cells={[v.label, usd(v.low), usd(v.market), usd(v.high)]} />)}
          </View>
        ) : (
          <Text style={{ marginTop: 8 }}>No TCGplayer price data for this card.</Text>
        )}
        {eurTrend != null && <Text style={{ marginTop: 12 }}>Cardmarket (EU) trend: {eur(eurTrend)}</Text>}
        {card.tcgplayer?.updatedAt && <Text style={[styles.muted, { marginTop: 8 }]}>Prices as of {card.tcgplayer.updatedAt}</Text>}
        {card.tcgplayer?.url && (
          <Pressable style={[styles.outline, { marginTop: 12 }]} onPress={() => Linking.openURL(card.tcgplayer!.url!)}>
            <Text style={styles.outlineText}>View listings on TCGplayer</Text>
          </Pressable>
        )}
      </View>

      <Text style={styles.h2}>Add to collection</Text>
      <View style={styles.chips}>
        {options.map((v) => (
          <Pressable key={v} onPress={() => setVariant(v)} style={[styles.chip, v === variant && styles.chipOn]}>
            <Text style={v === variant ? styles.chipTextOn : styles.chipText}>{variantLabel(v)}</Text>
          </Pressable>
        ))}
      </View>
      <Pressable style={[styles.button, { alignSelf: 'stretch' }]} onPress={() => add(card, variant)}>
        <Text style={styles.buttonText}>+ Add {variantLabel(variant)}</Text>
      </Pressable>

      {owned.length > 0 && (
        <View style={{ marginTop: 24 }}>
          <Text style={styles.h2}>In your collection</Text>
          {owned.map((item) => (
            <View key={item.key} style={styles.ownedRow}>
              <View style={{ flex: 1 }}>
                <Text>{variantLabel(item.variant)}</Text>
                <Text style={styles.muted}>
                  {usd(item.priceUsd)} each · {usd(item.priceUsd == null ? null : item.priceUsd * item.quantity)} total
                </Text>
              </View>
              <Pressable hitSlop={8} onPress={() => setQuantity(item.key, item.quantity - 1)} accessibilityLabel="Remove one">
                <MaterialIcons name="remove-circle-outline" size={28} color={colors.primary} />
              </Pressable>
              <Text style={styles.qty}>{item.quantity}</Text>
              <Pressable hitSlop={8} onPress={() => setQuantity(item.key, item.quantity + 1)} accessibilityLabel="Add one">
                <MaterialIcons name="add-circle-outline" size={28} color={colors.primary} />
              </Pressable>
            </View>
          ))}
        </View>
      )}
    </ScrollView>
  );
}

function PriceRow({ cells, header }: { cells: string[]; header?: boolean }) {
  return (
    <View style={{ flexDirection: 'row', paddingVertical: 3 }}>
      {cells.map((c, i) => (
        <Text
          key={i}
          style={[
            { flex: i === 0 ? 1.4 : 1, fontSize: header ? 12 : 14, color: header ? colors.muted : colors.text },
            i === 2 && !header && { fontWeight: '700' },
          ]}
        >
          {c}
        </Text>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12 },
  image: { width: '75%', aspectRatio: 0.716, alignSelf: 'center', borderRadius: 12 },
  title: { fontSize: 24, fontWeight: '700', marginTop: 16, color: colors.text },
  muted: { color: colors.muted, fontSize: 13 },
  box: { backgroundColor: colors.surface, borderRadius: 16, padding: 16, marginVertical: 16 },
  h2: { fontSize: 17, fontWeight: '700', color: colors.text },
  big: { fontSize: 34, fontWeight: '800', color: colors.text, marginVertical: 2 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginVertical: 10 },
  chip: { paddingHorizontal: 14, paddingVertical: 6, borderRadius: 16, borderWidth: 1, borderColor: colors.border },
  chipOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { color: colors.text },
  chipTextOn: { color: '#fff', fontWeight: '600' },
  button: { backgroundColor: colors.primary, paddingHorizontal: 20, paddingVertical: 12, borderRadius: 24, alignItems: 'center' },
  buttonText: { color: '#fff', fontWeight: '700', fontSize: 15 },
  outline: { borderWidth: 1, borderColor: colors.border, padding: 10, borderRadius: 20, alignItems: 'center' },
  outlineText: { color: colors.primary, fontWeight: '600' },
  ownedRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8 },
  qty: { fontSize: 17, fontWeight: '700', minWidth: 24, textAlign: 'center' },
});
