import MaterialIcons from '@expo/vector-icons/MaterialIcons';
import { Tabs } from 'expo-router';
import { colors } from '../../lib/theme';

export default function TabLayout() {
  return (
    <Tabs screenOptions={{ tabBarActiveTintColor: colors.primary }}>
      <Tabs.Screen
        name="index"
        options={{ title: 'Collection', tabBarIcon: ({ color }) => <MaterialIcons name="collections-bookmark" size={26} color={color as string} /> }}
      />
      <Tabs.Screen
        name="scan"
        options={{ title: 'Scan', tabBarIcon: ({ color }) => <MaterialIcons name="photo-camera" size={26} color={color as string} /> }}
      />
      <Tabs.Screen
        name="search"
        options={{ title: 'Search', tabBarIcon: ({ color }) => <MaterialIcons name="search" size={26} color={color as string} /> }}
      />
    </Tabs>
  );
}
