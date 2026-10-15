import { CameraView, useCameraPermissions } from 'expo-camera';
import { File } from 'expo-file-system';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, FlatList, Pressable, StyleSheet, Text, View } from 'react-native';
import { isAvailable as ocrAvailable, recognizeText } from '../../../modules/card-text';
import { CardRow } from '../../components/CardRow';
import { identify } from '../../lib/api';
import { useCollection } from '../../lib/collection';
import { cluesKey, describe, isEmpty, parseCardText, type ScanClues } from '../../lib/parser';
import { defaultVariant, variantLabel } from '../../lib/pricing';
import { colors } from '../../lib/theme';
import type { ApiCard } from '../../lib/types';

const IDLE_HINT = 'Fill the frame with one card, flat and well lit';

type Phase =
  | { kind: 'looking'; hint: string }
  | { kind: 'searching'; clues: ScanClues }
  | { kind: 'found'; cards: ApiCard[]; added?: string }
  | { kind: 'failed'; message: string };

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export default function ScanScreen() {
  const [permission, requestPermission] = useCameraPermissions();
  const [focused, setFocused] = useState(false);
  const [ready, setReady] = useState(false);
  const [phase, setPhase] = useState<Phase>({ kind: 'looking', hint: IDLE_HINT });
  const camera = useRef<CameraView>(null);
  const { add } = useCollection();

  // Only one camera preview may be active; unmount it when the tab isn't showing.
  useFocusEffect(useCallback(() => {
    setFocused(true);
    return () => { setFocused(false); setReady(false); };
  }, []));

  useEffect(() => {
    if (permission && !permission.granted && permission.canAskAgain) requestPermission();
  }, [permission, requestPermission]);

  const looking = phase.kind === 'looking';

  // Snap a photo, read its text, repeat; look the card up once the same reading
  // shows up in consecutive photos.
  useEffect(() => {
    if (!focused || !ready || !looking || !ocrAvailable) return;
    let cancelled = false;
    (async () => {
      let lastKey: string | null = null;
      let streak = 0;
      while (!cancelled) {
        let clues: ScanClues;
        try {
          const photo = await camera.current?.takePictureAsync({ quality: 0.5, shutterSound: false });
          if (!photo || cancelled) break;
          const lines = await recognizeText(photo.uri);
          try { new File(photo.uri).delete(); } catch { /* cache file; fine to leave */ }
          clues = parseCardText(lines.map((l) => l.text));
        } catch {
          await sleep(500);
          continue;
        }
        if (cancelled) break;
        if (isEmpty(clues)) {
          streak = 0;
          lastKey = null;
          setPhase({ kind: 'looking', hint: IDLE_HINT });
          continue;
        }
        const key = cluesKey(clues);
        streak = key === lastKey ? streak + 1 : 1;
        lastKey = key;
        setPhase({ kind: 'looking', hint: `Reading… ${describe(clues)}` });
        // Numbers are reliable after two matching reads; names flicker more.
        if (streak >= (clues.number != null ? 2 : 3)) {
          setPhase({ kind: 'searching', clues });
          try {
            const cards = await identify(clues);
            if (!cancelled) setPhase({ kind: 'found', cards: cards.slice(0, 10) });
          } catch {
            if (!cancelled) setPhase({ kind: 'failed', message: "Couldn't reach the card database. Check your connection." });
          }
          break;
        }
      }
    })();
    return () => { cancelled = true; };
  }, [focused, ready, looking]);

  const rescan = () => setPhase({ kind: 'looking', hint: IDLE_HINT });

  function quickAdd(card: ApiCard) {
    const variant = defaultVariant(card);
    add(card, variant);
    setPhase((p) => (p.kind === 'found' ? { ...p, added: `Added ${card.name} (${variantLabel(variant)})` } : p));
  }

  if (!ocrAvailable) {
    return (
      <Centered>
        <Text style={styles.centerText}>
          {"Card scanning needs the installed PokéCollector app (it doesn't run inside Expo Go)."}
        </Text>
        <LinkButton label="Search by name instead" onPress={() => router.navigate('/search')} />
      </Centered>
    );
  }
  if (!permission) return <Centered><ActivityIndicator color={colors.primary} /></Centered>;
  if (!permission.granted) {
    return (
      <Centered>
        <Text style={styles.centerText}>Camera access is needed to scan cards.</Text>
        <Pressable style={styles.button} onPress={requestPermission}>
          <Text style={styles.buttonText}>Allow camera</Text>
        </Pressable>
        <LinkButton label="Search by name instead" onPress={() => router.navigate('/search')} />
      </Centered>
    );
  }

  const hint =
    phase.kind === 'looking' ? phase.hint
      : phase.kind === 'searching' ? `Looking up ${describe(phase.clues)}`
        : 'Scan paused';

  return (
    <View style={{ flex: 1, backgroundColor: '#000' }}>
      <View style={{ flex: 1 }}>
        {focused && (
          <CameraView
            ref={camera}
            style={StyleSheet.absoluteFill}
            facing="back"
            animateShutter={false}
            onCameraReady={() => setReady(true)}
          />
        )}
        <View pointerEvents="none" style={styles.guideWrap}>
          <View style={styles.guide} />
        </View>
        <View pointerEvents="none" style={styles.hintWrap}>
          <Text style={styles.hint}>{hint}</Text>
        </View>
      </View>

      <View style={styles.panel}>
        {phase.kind === 'looking' && (
          <LinkButton label={"Can't scan it? Search by name"} onPress={() => router.navigate('/search')} />
        )}
        {phase.kind === 'searching' && <ActivityIndicator style={{ margin: 24 }} color={colors.primary} />}
        {phase.kind === 'failed' && (
          <View style={{ padding: 16, alignItems: 'center', gap: 8 }}>
            <Text>{phase.message}</Text>
            <Pressable style={styles.button} onPress={rescan}><Text style={styles.buttonText}>Try again</Text></Pressable>
          </View>
        )}
        {phase.kind === 'found' && (
          <>
            <View style={styles.panelHead}>
              <Text style={styles.panelTitle}>
                {phase.added ?? (phase.cards.length === 0 ? 'No match found' : 'Is it one of these?')}
              </Text>
              <Pressable style={styles.outline} onPress={rescan}><Text style={styles.outlineText}>Scan next</Text></Pressable>
            </View>
            {phase.cards.length === 0 && (
              <LinkButton label="Search by name instead" onPress={() => router.navigate('/search')} />
            )}
            <FlatList
              data={phase.cards}
              keyExtractor={(c) => c.id}
              renderItem={({ item }) => (
                <CardRow
                  card={item}
                  onPress={() => router.push(`/card/${item.id}`)}
                  right={
                    <Pressable style={styles.addBtn} onPress={() => quickAdd(item)}>
                      <Text style={styles.addText}>Add</Text>
                    </Pressable>
                  }
                />
              )}
            />
          </>
        )}
      </View>
    </View>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return <View style={styles.centered}>{children}</View>;
}

function LinkButton({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={{ padding: 12, alignSelf: 'center' }}>
      <Text style={{ color: colors.primary, fontWeight: '600' }}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  centered: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32, gap: 12, backgroundColor: colors.bg },
  centerText: { textAlign: 'center', color: colors.text, fontSize: 16 },
  guideWrap: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, alignItems: 'center', justifyContent: 'center' },
  // Card-shaped guide (63×88 mm).
  guide: { width: '72%', aspectRatio: 63 / 88, borderWidth: 3, borderColor: 'rgba(255,255,255,0.85)', borderRadius: 12 },
  hintWrap: { position: 'absolute', bottom: 12, left: 0, right: 0, alignItems: 'center' },
  hint: {
    color: '#fff', backgroundColor: 'rgba(0,0,0,0.6)', paddingHorizontal: 16, paddingVertical: 8,
    borderRadius: 20, overflow: 'hidden', fontSize: 14,
  },
  panel: { backgroundColor: colors.bg, maxHeight: '45%' },
  panelHead: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingTop: 10, paddingBottom: 4 },
  panelTitle: { flex: 1, fontWeight: '600', fontSize: 15, color: colors.text },
  button: { backgroundColor: colors.primary, paddingHorizontal: 20, paddingVertical: 10, borderRadius: 20 },
  buttonText: { color: '#fff', fontWeight: '600' },
  outline: { borderWidth: 1, borderColor: colors.border, paddingHorizontal: 14, paddingVertical: 6, borderRadius: 16 },
  outlineText: { color: colors.primary, fontWeight: '600' },
  addBtn: { backgroundColor: colors.primarySoft, paddingHorizontal: 14, paddingVertical: 6, borderRadius: 14 },
  addText: { color: colors.primary, fontWeight: '700' },
});
