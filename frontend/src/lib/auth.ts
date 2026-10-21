const KEY = "beacon_api_key";

export function getApiKey(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(KEY);
}

export function setApiKey(key: string) {
  window.localStorage.setItem(KEY, key.trim());
}

export function clearApiKey() {
  window.localStorage.removeItem(KEY);
}

export function isAuthenticated(): boolean {
  return Boolean(getApiKey());
}
