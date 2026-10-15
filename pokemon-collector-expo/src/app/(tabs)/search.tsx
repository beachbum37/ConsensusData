import MaterialIcons from '@expo/vector-icons/MaterialIcons';
import { router } from 'expo-router';
import { useRef, useState } from 'react';
import { ActivityIndicator, FlatList, StyleSheet, Text, TextInput, View } from 'react-native';
import { CardRow, rowStyles } from '../../components/CardRow';
import { searchCards } from '../../lib/api';
import { colors } from '../../lib/theme';
import type { ApiCard } from '../../lib/types';

const HINT = 'Search by name ("Charizard ex"), number ("4/102"), or both.';

export default function SearchScreen() {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<ApiCard[]>([]);
  const [message, setMessage] = useState<string | null>(HINT);
  const latest = useRef(0);

  async function run() {
    const id = ++latest.current;
    setLoading(true);
    setMessage(null);
    try {
      const r = await searchCards(query);
      if (id !== latest.current) return;
      setResults(r);
      setMessage(r.length === 0 ? 'No cards found.' : null);
    } catch {
      if (id !== latest.current) return;
      setResults([]);
      setMessage("Couldn't reach the card database. Check your connection.");
    } finally {
      if (id === latest.current) setLoading(false);
    }
  }

  return (
    <View style={{ flex: 1 }}>
      <View style={styles.box}>
        <MaterialIcons name="search" size={22} color={colors.muted} />
        <TextInput
          value={query}
          onChangeText={setQuery}
          onSubmitEditing={run}
          placeholder="Card name or number"
          returnKeyType="search"
          autoCorrect={false}
          style={styles.input}
        />
      </View>
      {loading ? (
        <ActivityIndicator style={{ marginTop: 32 }} color={colors.primary} />
      ) : message ? (
        <Text style={styles.message}>{message}</Text>
      ) : (
        <FlatList
          data={results}
          keyExtractor={(c) => c.id}
          keyboardShouldPersistTaps="handled"
          ItemSeparatorComponent={() => <View style={rowStyles.separator} />}
          renderItem={({ item }) => <CardRow card={item} onPress={() => router.push(`/card/${item.id}`)} />}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  box: {
    flexDirection: 'row', alignItems: 'center', gap: 8, margin: 16, paddingHorizontal: 12,
    borderWidth: 1, borderColor: colors.border, borderRadius: 12,
  },
  input: { flex: 1, paddingVertical: 12, fontSize: 16, color: colors.text },
  message: { textAlign: 'center', color: colors.muted, padding: 32 },
});
