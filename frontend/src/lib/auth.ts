const ACCESS_TOKEN_KEY = "mira_access_token";
const LEGACY_API_KEY = "beacon_api_key";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function setAccessToken(token: string) {
  if (typeof window === "undefined") return;
  const value = token.trim();
  if (value) window.localStorage.setItem(ACCESS_TOKEN_KEY, value);
}

export function clearAccessToken() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
}

export function getApiKey(): string | null {
  if (typeof window === "undefined") return null;
  return getAccessToken() || window.localStorage.getItem(LEGACY_API_KEY);
}

export function setApiKey(key: string) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(LEGACY_API_KEY, key.trim());
}

export function clearApiKey() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
  window.localStorage.removeItem(LEGACY_API_KEY);
}

export function clearAuth() {
  clearApiKey();
}

export function isAuthenticated(): boolean {
  return Boolean(getAccessToken() || getApiKey());
}
