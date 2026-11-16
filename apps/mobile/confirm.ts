import {Alert, Platform} from 'react-native';

export async function confirmAction(title: string, message: string, confirmLabel = 'Approve'): Promise<boolean> {
  if (Platform.OS === 'web') return window.confirm(`${title}\n\n${message}`);
  return new Promise(resolve => Alert.alert(title, message, [
    {text: 'Cancel', style: 'cancel', onPress: () => resolve(false)},
    {text: confirmLabel, onPress: () => resolve(true)},
  ], {cancelable: true, onDismiss: () => resolve(false)}));
}
