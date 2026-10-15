import MaterialIcons from '@expo/vector-icons/MaterialIcons';
import { Image } from 'expo-image';
import { router } from 'expo-router';
import { useMemo, useState } from 'react';
import { ActivityIndicator, FlatList, Pressable, StyleSheet, Text, View } from 'react-native';
import { rowStyles } from '../../components/CardRow';
import { useCollection } from '../../lib/collection';
import { usd } from '../../lib/format';
import { variantLabel } from '../../lib/pricing';
import { colors } from '../../lib/theme';
import type { OwnedCard } from '../../lib/types';

const SORTS = { value: 'Value', recent: 'Recent', name: 'Name' } as const;
type Sort = keyof typeof SORTS;

export default function CollectionScreen() {
  const { items, refreshPrices } = useCollection();
  const [sort, setSort] = useState<Sort>('value');
  const [refreshing, setRefreshing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const sorted = useMemo(() => {
    const value = (i: OwnedCard) => (i.priceUsd ?? 0) * i.quantity;
    const copy = [...items];
    if (sort === 'value') copy.sort((a, b) => value(b) - value(a));
    if (sort === 'recent') copy.sort((a, b) => b.addedAt - a.addedAt);
    if (sort === 'name') copy.sort((a, b) => a.name.localeCompare(b.name));
    return copy;
  }, [items, sort]);

  const total = items.reduce((s, i) => s + (i.priceUsd ?? 0) * i.quantity, 0);
  const count = items.reduce((s, i) => s + i.quantity, 0);
  const lastPriced = items.length ? Math.max(...items.map((i) => i.priceUpdatedAt)) : null;

  async function refresh() {
    setRefreshing(true);
    setMessage(null);
    try {
      const n = await refreshPrices();
      setMessage(`Updated prices for ${n} cards`);
    } catch {
      setMessage("Couldn't reach the price service");
    } finally {
      setRefreshing(false);
    }
  }

  const header = (
    <View>
      <View style={styles.hero}>
        <View style={{ flex: 1 }}>
          <Text style={styles.heroLabel}>Collection value</Text>
          <Text style={styles.heroValue}>{usd(total)}</Text>
          <Text style={styles.heroSub}>
            {count} cards · TCGplayer market{lastPriced ? ` · ${new Date(lastPriced).toLocaleDateString()}` : ''}
          </Text>
          {message ? <Text style={styles.heroSub}>{message}</Text> : null}
        </View>
        {refreshing ? (
          <ActivityIndicator color={colors.primary} />
        ) : (
          <Pressable onPress={refresh} disabled={items.length === 0} hitSlop={12} accessibilityLabel="Refresh prices">
            <MaterialIcons name="refresh" size={28} color={items.length ? colors.primary : colors.border} />
          </Pressable>
        )}
      </View>
      {items.length > 0 && (
        <View style={styles.chips}>
          {(Object.keys(SORTS) as Sort[]).map((s) => (
            <Pressable key={s} onPress={() => setSort(s)} style={[styles.chip, sort === s && styles.chipOn]}>
              <Text style={[styles.chipText, sort === s && styles.chipTextOn]}>{SORTS[s]}</Text>
            </Pressable>
          ))}
        </View>
      )}
    </View>
  );

  return (
    <FlatList
      data={sorted}
      keyExtractor={(i) => i.key}
      ListHeaderComponent={header}
      ItemSeparatorComponent={() => <View style={rowStyles.separator} />}
      ListEmptyComponent={
        <Text style={styles.empty}>No cards yet.{'\n'}Tap Scan and point your camera at a card.</Text>
      }
      renderItem={({ item }) => <OwnedRow item={item} />}
      contentContainerStyle={{ paddingBottom: 24 }}
    />
  );
}

function OwnedRow({ item }: { item: OwnedCard }) {
  return (
    <Pressable
      onPress={() => router.push(`/card/${item.cardId}`)}
      style={({ pressed }) => [styles.row, pressed && { opacity: 0.6 }]}
    >
      <Image source={item.imageSmall} style={styles.thumb} contentFit="cover" />
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={styles.name} numberOfLines={1}>{item.name}</Text>
        <Text style={styles.sub} numberOfLines={1}>{item.setName} · {item.number}/{item.setTotal}</Text>
        <Text style={styles.small}>
          {variantLabel(item.variant)} · ×{item.quantity} @ {usd(item.priceUsd)}
        </Text>
      </View>
      <Text style={styles.value}>{usd(item.priceUsd == null ? null : item.priceUsd * item.quantity)}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  hero: {
    margin: 16, padding: 20, borderRadius: 16, backgroundColor: colors.primarySoft,
    flexDirection: 'row', alignItems: 'center',
  },
  heroLabel: { fontSize: 14, fontWeight: '600', color: colors.text },
  heroValue: { fontSize: 36, fontWeight: '800', color: colors.text, marginVertical: 2 },
  heroSub: { fontSize: 12, color: colors.muted },
  chips: { flexDirection: 'row', gap: 8, paddingHorizontal: 16, paddingBottom: 8 },
  chip: { paddingHorizontal: 14, paddingVertical: 6, borderRadius: 16, borderWidth: 1, borderColor: colors.border },
  chipOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { color: colors.text },
  chipTextOn: { color: '#fff', fontWeight: '600' },
  empty: { textAlign: 'center', color: colors.muted, padding: 32, lineHeight: 22 },
  row: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 8, gap: 12 },
  thumb: { width: 52, height: 72, borderRadius: 4, backgroundColor: colors.surface },
  name: { fontSize: 16, fontWeight: '600', color: colors.text },
  sub: { fontSize: 13, color: colors.muted },
  small: { fontSize: 12, color: colors.muted },
  value: { fontSize: 15, fontWeight: '700', color: colors.text },
});
