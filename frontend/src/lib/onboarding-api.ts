import { setAccessToken } from "@/lib/auth";

export type CompleteOnboardingPayload = {
  onboarding_token: string;
  email: string;
  first_name: string;
  last_name: string;
  job_title: string;
  organization_name: string;
  trade_name: string;
  cnpj: string;
  website: string;
  institution_type: string;
  student_range: string;
  campuses: string;
  description: string;
  data_sources: string[];
};

export type CompanyEnrichment = {
  cnpj: string;
  legal_name: string | null;
  trade_name: string | null;
  status: string | null;
  primary_activity: string | null;
  address: string | null;
  email: string | null;
  phone: string | null;
};

export type WebsiteEnrichment = {
  url: string;
  title: string | null;
  description: string | null;
  markdown: string;
  truncated: boolean;
  source: string;
};

export type OnboardingEnrichment = {
  company: CompanyEnrichment | null;
  website: WebsiteEnrichment | null;
  warnings: string[];
};

export async function enrichOnboarding(payload: {
  onboarding_token: string;
  email: string;
  cnpj: string;
  website: string;
}): Promise<OnboardingEnrichment> {
  const base =
    process.env.NODE_ENV === "development"
      ? process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
      : "";
  const response = await fetch(`${base}/api/v1/onboarding/enrich`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body.detail;
    const message = Array.isArray(detail)
      ? detail.map((item: { msg?: string }) => item.msg || "Dados inválidos").join(", ")
      : detail || body.message || `Erro ${response.status}`;
    throw new Error(String(message));
  }
  return body as OnboardingEnrichment;
}

export type OnboardingMfaChallenge =
  | { mfa_enrollment_required: true; challenge_token: string }
  | { mfa_required: true; challenge_token: string };

export async function completeOrganizationOnboarding(
  payload: CompleteOnboardingPayload,
): Promise<
  | { access_token: string; token_type: string; expires_in: number; user: { display_name: string; email: string; tenant_name: string } }
  | OnboardingMfaChallenge
> {
  const base =
    process.env.NODE_ENV === "development"
      ? process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
      : "";
  const response = await fetch(`${base}/api/v1/onboarding/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body.detail;
    const message = Array.isArray(detail)
      ? detail.map((item: { msg?: string }) => item.msg || "Dados inválidos").join(", ")
      : detail || body.message || `Erro ${response.status}`;
    throw new Error(String(message));
  }
  if (body.access_token) setAccessToken(body.access_token);
  return body;
}
