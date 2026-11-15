/** Only a CSRF value and mapped identity reach JS. Entra tokens stay server-side. */
export interface SessionIdentity { actor_id: string; role: 'Student' | 'Instructor' }
export type AuthStatus = { mode: 'demo'; authenticated: false } | {
  mode: 'bff'; authenticated: boolean; actor_id?: string; role?: 'Student' | 'Instructor'; csrf_token?: string;
};
export const apiBase = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
let csrf = '';
export function csrfHeaders(): Record<string, string> { return csrf ? { 'X-CSRF-Token': csrf } : {}; }
export function acceptAuthStatus(value: AuthStatus) {
  csrf = value.mode === 'bff' && value.authenticated ? value.csrf_token ?? '' : '';
}
export function authenticationLost() {
  csrf = '';
  window.dispatchEvent(new Event('harness:authentication-lost'));
}
export async function authStatus(): Promise<AuthStatus> {
  const response = await fetch(`${apiBase}/auth/status`, { credentials: 'include', cache: 'no-store' });
  if (!response.ok) throw new Error('Cannot check sign-in status. Please retry.');
  const value = await response.json() as AuthStatus;
  if (value.mode !== 'demo' && value.mode !== 'bff') throw new Error('Unsupported authentication configuration.');
  if (value.mode === 'bff' && value.authenticated && (!value.actor_id || !['Student', 'Instructor'].includes(value.role ?? '') || !value.csrf_token)) {
    throw new Error('Incomplete sign-in response.');
  }
  return value;
}
export async function logout() {
  const response = await fetch(`${apiBase}/auth/logout`, {
    method: 'POST', credentials: 'include', headers: csrfHeaders(),
  });
  if (!response.ok && response.status !== 401) throw new Error('Could not sign out. Please retry.');
  authenticationLost();
}
