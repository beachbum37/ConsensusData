import { NativeModule, requireOptionalNativeModule } from 'expo';

export type TextLine = { text: string; top: number; left: number };

declare class CardTextModule extends NativeModule<{}> {
  recognize(uri: string): Promise<TextLine[]>;
}

// Optional so the JS still loads where the native part isn't compiled in (e.g. Expo Go).
export default requireOptionalNativeModule<CardTextModule>('CardText');
