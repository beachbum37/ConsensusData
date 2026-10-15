import { Image } from 'expo-image';
import type { ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { usd } from '../lib/format';
import { defaultVariant, marketUsd } from '../lib/pricing';
import { colors } from '../lib/theme';
import type { ApiCard } from '../lib/types';

/** A search/scan result row: thumbnail, name, set and typical market price. */
export function CardRow({ card, onPress, right }: { card: ApiCard; onPress: () => void; right?: ReactNode }) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.row, pressed && { opacity: 0.6 }]}>
      <Image source={card.images.small} style={styles.thumb} contentFit="cover" transition={150} />
      <View style={styles.body}>
        <Text style={styles.name} numberOfLines={1}>{card.name}</Text>
        <Text style={styles.sub} numberOfLines={1}>
          {card.set.name} · {card.number}/{card.set.printedTotal}
        </Text>
        {card.rarity ? <Text style={styles.small}>{card.rarity}</Text> : null}
      </View>
      <View style={styles.right}>
        <Text style={styles.price}>{usd(marketUsd(card, defaultVariant(card)))}</Text>
        {right}
      </View>
    </Pressable>
  );
}

export const rowStyles = StyleSheet.create({
  separator: { height: StyleSheet.hairlineWidth, backgroundColor: colors.border, marginLeft: 80 },
});

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 8, gap: 12 },
  thumb: { width: 52, height: 72, borderRadius: 4, backgroundColor: colors.surface },
  body: { flex: 1, gap: 2 },
  name: { fontSize: 16, fontWeight: '600', color: colors.text },
  sub: { fontSize: 13, color: colors.muted },
  small: { fontSize: 12, color: colors.muted },
  right: { alignItems: 'flex-end', gap: 4 },
  price: { fontSize: 15, fontWeight: '700', color: colors.text },
});
