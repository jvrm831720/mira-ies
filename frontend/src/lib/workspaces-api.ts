import { setAccessToken } from "./auth";

export type WorkspaceItem = {
  membership_id?: string | null;
  tenant_id: string;
  tenant_name: string;
  tenant_slug?: string;
  role: string;
  custom_role_id?: string | null;
  status: string;
  is_current: boolean;
  origin?: string;
};

export type WorkspacesResponse = {
  current_tenant_id: string;
  current_membership_id?: string | null;
  workspaces: WorkspaceItem[];
};

export type SwitchWorkspaceResponse = {
  switched: boolean;
  message?: string;
  access_token?: string;
  token_type?: string;
  expires_in?: number;
  tenant_id: string;
  tenant_name: string;
  tenant_slug?: string;
  membership_id?: string | null;
  role?: string;
  user?: { display_name?: string; email?: string; tenant_name?: string };
};

function baseUrl(): string {
  return process.env.NODE_ENV === "development"
    ? process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
    : "";
}

async function authHeaders(json = false): Promise<Headers> {
  const { getAccessToken, getApiKey } = await import("./auth");
  const headers = new Headers();
  if (json) headers.set("Content-Type", "application/json");
  const token = getAccessToken();
  const key = getApiKey();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  else if (key) headers.set("X-API-Key", key);
  return headers;
}

/** List memberships/workspaces for the signed-in user. */
export async function listWorkspaces(): Promise<WorkspacesResponse> {
  const headers = await authHeaders();
  const res = await fetch(`${baseUrl()}/api/v1/org/workspaces`, { headers });
  if (!res.ok) {
    let detail = `Erro ${res.status}`;
    try {
      const j = await res.json();
      detail = j.detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(String(detail));
  }
  return res.json();
}

/** Switch active workspace; stores new access_token when returned. */
export async function switchWorkspace(body: {
  membership_id?: string;
  tenant_id?: string;
}): Promise<SwitchWorkspaceResponse> {
  const headers = await authHeaders(true);
  const res = await fetch(`${baseUrl()}/api/v1/org/workspaces/switch`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `Erro ${res.status}`;
    try {
      const j = await res.json();
      detail = j.detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(String(detail));
  }
  const data = (await res.json()) as SwitchWorkspaceResponse;
  if (data.access_token) setAccessToken(data.access_token);
  return data;
}
