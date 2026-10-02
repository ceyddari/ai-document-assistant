import type { AskResponse, AuthSession, Conversation, ConversationDetail, DocumentItem } from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

function getErrorMessage(body: unknown): string {
  if (
    typeof body === "object" &&
    body !== null &&
    "detail" in body &&
    typeof body.detail === "string"
  ) return body.detail;
  return "İstek tamamlanamadı.";
}

async function request<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    throw new ApiError(getErrorMessage(body), response.status);
  }
  return response.json() as Promise<T>;
}

export const api = {
  login: (email: string, password: string) =>
    request<AuthSession>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  register: (data: { email: string; password: string; organization_name: string; organization_slug: string }) =>
    request<AuthSession>("/auth/register", { method: "POST", body: JSON.stringify(data) }),
  documents: (organizationId: string, token: string) =>
    request<{ items: DocumentItem[] }>(`/organizations/${organizationId}/documents`, {}, token),
  upload: (organizationId: string, file: File, token: string) => {
    const body = new FormData();
    body.append("file", file);
    return request<DocumentItem>(`/organizations/${organizationId}/documents`, { method: "POST", body }, token);
  },
  retryDocument: (organizationId: string, documentId: string, token: string) =>
    request<DocumentItem>(
      `/organizations/${organizationId}/documents/${documentId}/retry`,
      { method: "POST" },
      token,
    ),
  conversations: (organizationId: string, token: string) =>
    request<{ items: Conversation[] }>(`/organizations/${organizationId}/conversations`, {}, token),
  conversation: (organizationId: string, conversationId: string, token: string) =>
    request<ConversationDetail>(`/organizations/${organizationId}/conversations/${conversationId}`, {}, token),
  ask: (organizationId: string, question: string, conversationId: string | null, token: string) =>
    request<AskResponse>(`/organizations/${organizationId}/ask`, {
      method: "POST",
      body: JSON.stringify({ question, limit: 5, conversation_id: conversationId }),
    }, token),
};
