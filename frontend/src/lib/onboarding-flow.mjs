export function plausiblePublicWebsite(value) {
  const trimmed = (value || "").trim();
  if (!trimmed || /\s/.test(trimmed)) return false;
  try {
    const parsed = new URL(/^https?:\/\//i.test(trimmed) ? trimmed : "https://" + trimmed);
    const host = parsed.hostname.toLowerCase();
    return ["http:", "https:"].includes(parsed.protocol) &&
      !parsed.username && !parsed.password &&
      host.includes(".") && host.length >= 5 &&
      !["localhost", "localhost.localdomain"].includes(host) &&
      !host.endsWith(".local") && !host.endsWith(".internal") &&
      !host.endsWith(".test") &&
      (parsed.port === "" || parsed.port === "80" || parsed.port === "443");
  } catch { return false; }
}

const PERSONAL_DOMAINS = new Set([
  "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "hotmail.com.br",
  "live.com", "live.com.br", "yahoo.com", "yahoo.com.br", "icloud.com",
  "me.com", "aol.com", "proton.me", "protonmail.com", "uol.com.br", "bol.com.br",
  "terra.com.br", "msn.com", "ymail.com", "hey.com",
]);

export function corporateDomain(email) {
  const parts = email.trim().toLowerCase().split("@");
  if (parts.length !== 2) return null;
  const domain = parts[1];
  if (!/^[a-z0-9][a-z0-9.-]+\.[a-z]{2,}$/.test(domain)) return null;
  if (PERSONAL_DOMAINS.has(domain) || domain.endsWith(".test") || domain.endsWith(".local")) return null;
  return domain;
}

export function maskCnpj(value) {
  const digits = value.replace(/\D/g, "").slice(0, 14);
  return digits.replace(/^(\d{2})(\d)/, "$1.$2")
    .replace(/^(\d{2})\.(\d{3})(\d)/, "$1.$2.$3")
    .replace(/\.(\d{3})(\d)/, ".$1/$2")
    .replace(/(\d{4})(\d)/, "$1-$2");
}

export function isValidCnpj(value) {
  const digits = value.replace(/\D/g, "");
  if (!/^\d{14}$/.test(digits) || /^(\d)\1{13}$/.test(digits)) return false;
  function check(base, weights) {
    const sum = [...base].reduce((total, n, i) => total + Number(n) * weights[i], 0);
    return String(sum % 11 < 2 ? 0 : 11 - sum % 11);
  }
  const first = check(digits.slice(0, 12), [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]);
  const second = check(digits.slice(0, 12) + first, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]);
  return digits.slice(-2) === first + second;
}

export function publicCompanyDescription(enrichment) {
  return (enrichment?.website?.description || enrichment?.company?.primary_activity || "").trim();
}
