// The web preview authenticates with the portal's HttpOnly cookie. This stores
// only a sign-in marker; Odoo session tokens are never persisted in web storage.
export async function getItemAsync(key: string): Promise<string | null> {
  try { return window.sessionStorage.getItem(key); } catch { return null; }
}
export async function setItemAsync(key: string, _value: string): Promise<void> {
  try { window.sessionStorage.setItem(key, 'cookie'); } catch { /* In-memory login still works. */ }
}
export async function deleteItemAsync(key: string): Promise<void> {
  try { window.sessionStorage.removeItem(key); } catch { /* Storage may be disabled. */ }
}
