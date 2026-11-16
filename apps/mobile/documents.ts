import {File, Paths} from 'expo-file-system';
import * as Sharing from 'expo-sharing';

export async function saveInvoice(name: string, content: string): Promise<void> {
  if (!await Sharing.isAvailableAsync()) throw new Error('File sharing is unavailable on this device.');
  const filename = name.replace(/[^a-zA-Z0-9._-]/g, '_');
  const file = new File(Paths.cache, `${Date.now()}-${filename}`);
  file.create();
  await file.write(content, {encoding: 'base64'});
  await Sharing.shareAsync(file.uri, {mimeType: 'application/pdf', UTI: 'com.adobe.pdf', dialogTitle: 'Save or share invoice'});
}
