import type { AskResponse, AuthSession, Conversation, ConversationDetail, DocumentItem, Feedback, Folder, Message } from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

function getErrorMessage(body: unknown): string {
  if (typeof body !== "object" || body === null || !("detail" in body)) return "İstek tamamlanamadı.";
  if (typeof body.detail === "string") return body.detail;
  // FastAPI validation errors (422) come as a list; show the first message without pydantic's prefix.
  if (Array.isArray(body.detail)) {
    const first: unknown = body.detail[0];
    if (typeof first === "object" && first !== null && "msg" in first && typeof first.msg === "string") {
      return first.msg.replace(/^Value error, /, "");
    }
  }
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
  return (response.status === 204 ? undefined : response.json()) as Promise<T>;
}

export const api = {
  login: (email: string, password: string) =>
    request<AuthSession>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  register: (data: { email: string; password: string; organization_name: string; organization_slug: string }) =>
    request<AuthSession>("/auth/register", { method: "POST", body: JSON.stringify(data) }),
  logout: (token: string) => request<void>("/auth/logout", { method: "POST" }, token),
  documents: (organizationId: string, token: string) =>
    request<{ items: DocumentItem[] }>(`/organizations/${organizationId}/documents`, {}, token),
  upload: (organizationId: string, file: File, token: string, folderId?: string | null) => {
    const body = new FormData();
    body.append("file", file);
    if (folderId) body.append("folder_id", folderId);
    return request<DocumentItem>(`/organizations/${organizationId}/documents`, { method: "POST", body }, token);
  },
  retryDocument: (organizationId: string, documentId: string, token: string) =>
    request<DocumentItem>(
      `/organizations/${organizationId}/documents/${documentId}/retry`,
      { method: "POST" },
      token,
    ),
  folders: (organizationId: string, token: string) =>
    request<{ items: Folder[] }>(`/organizations/${organizationId}/folders`, {}, token),
  createFolder: (organizationId: string, name: string, token: string) =>
    request<Folder>(`/organizations/${organizationId}/folders`, { method: "POST", body: JSON.stringify({ name }) }, token),
  deleteFolder: async (organizationId: string, folderId: string, token: string) => {
    await request<void>(`/organizations/${organizationId}/folders/${folderId}`, { method: "DELETE" }, token);
  },
  moveDocument: (organizationId: string, documentId: string, folderId: string | null, token: string) =>
    request<DocumentItem>(`/organizations/${organizationId}/documents/${documentId}`, { method: "PATCH", body: JSON.stringify({ folder_id: folderId }) }, token),
  deleteDocument: async (organizationId: string, documentId: string, token: string) => {
    await request<void>(`/organizations/${organizationId}/documents/${documentId}`, { method: "DELETE" }, token);
  },
  // Fetched with the Authorization header and opened as a blob URL, so the token never lands in a URL.
  documentFile: async (organizationId: string, documentId: string, token: string) => {
    const response = await fetch(`${API_URL}/organizations/${organizationId}/documents/${documentId}/file`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
      const body: unknown = await response.json().catch(() => null);
      throw new ApiError(getErrorMessage(body), response.status);
    }
    return response.blob();
  },
  conversations: (organizationId: string, token: string) =>
    request<{ items: Conversation[] }>(`/organizations/${organizationId}/conversations`, {}, token),
  conversation: (organizationId: string, conversationId: string, token: string) =>
    request<ConversationDetail>(`/organizations/${organizationId}/conversations/${conversationId}`, {}, token),
  renameConversation: (organizationId: string, conversationId: string, title: string, token: string) =>
    request<Conversation>(`/organizations/${organizationId}/conversations/${conversationId}`, { method: "PATCH", body: JSON.stringify({ title }) }, token),
  setConversationDocuments: (organizationId: string, conversationId: string, documentIds: string[], token: string) =>
    request<string[]>(`/organizations/${organizationId}/conversations/${conversationId}/documents`, { method: "PUT", body: JSON.stringify({ document_ids: documentIds }) }, token),
  deleteConversation: async (organizationId: string, conversationId: string, token: string) => {
    await request<void>(`/organizations/${organizationId}/conversations/${conversationId}`, { method: "DELETE" }, token);
  },
  setFeedback: (organizationId: string, conversationId: string, messageId: string, value: Feedback, token: string) =>
    request<Message>(
      `/organizations/${organizationId}/conversations/${conversationId}/messages/${messageId}/feedback`,
      { method: "PUT", body: JSON.stringify({ value }) },
      token,
    ),
  askStream,
};

type AskStreamEvent =
  | { type: "token"; text: string }
  | ({ type: "done" } & AskResponse)
  | { type: "error"; detail: string };

/** POSTs the question and reads server-sent events; resolves with the saved answer.
 *  `onToken` gets raw model text (its own citation numbers); the result replaces it. */
async function askStream(
  organizationId: string,
  body: { question: string; conversation_id: string | null; document_ids: string[] | null },
  token: string,
  onToken: (text: string) => void,
  signal: AbortSignal,
): Promise<AskResponse> {
  const response = await fetch(`${API_URL}/organizations/${organizationId}/ask/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ ...body, limit: 5 }),
    signal,
  });
  if (!response.ok || !response.body) {
    const errorBody: unknown = await response.json().catch(() => null);
    throw new ApiError(getErrorMessage(errorBody), response.status);
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value;
      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf("\n\n");
        if (!block.startsWith("data: ")) continue;
        const event = JSON.parse(block.slice(6)) as AskStreamEvent;
        if (event.type === "token") onToken(event.text);
        else if (event.type === "done") return event;
        else throw new ApiError(event.detail, 503);
      }
    }
  } finally {
    void reader.cancel().catch(() => undefined);
  }
  throw new ApiError("Cevap tamamlanmadan bağlantı kesildi.", 503);
}
