import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { CollectionProvider } from '../lib/collection';
import { colors } from '../lib/theme';

export default function RootLayout() {
  return (
    <CollectionProvider>
      <StatusBar style="dark" />
      <Stack screenOptions={{ headerTintColor: colors.primary, contentStyle: { backgroundColor: colors.bg } }}>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="card/[id]" options={{ title: 'Card' }} />
      </Stack>
    </CollectionProvider>
  );
}
