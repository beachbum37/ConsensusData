import CardText, { type TextLine } from './src/CardTextModule';

export type { TextLine };

/** True when the native text reader is in this build. */
export const isAvailable = CardText != null;

/** Reads the text lines (top to bottom) from the photo at [uri]. */
export async function recognizeText(uri: string): Promise<TextLine[]> {
  if (!CardText) throw new Error('Card scanning needs the installed app build, not Expo Go.');
  return CardText.recognize(uri);
}
