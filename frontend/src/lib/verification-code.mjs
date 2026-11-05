/** Normalize pasted/typed OTPs while keeping the API's six-ASCII-digit contract. */
export function normalizeVerificationCode(value) {
  return value.replace(/[^0-9]/g, "").slice(0, 6);
}
