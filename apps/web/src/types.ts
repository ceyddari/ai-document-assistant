export type User = { id: string; email: string; created_at: string };
export type AuthSession = {
  access_token: string;
  token_type: "bearer";
  expires_at: string;
  user: User;
  organization_id: string | null;
  organization_ids: string[];
};
export type DocumentStatus = "pending" | "processing" | "ready" | "failed";
export type DocumentItem = {
  id: string;
  organization_id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  status: DocumentStatus;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};
export type Source = {
  chunk_id: string;
  document_id: string;
  filename: string;
  page_number: number;
  content: string;
  similarity: number;
};
export type Message = {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  sequence: number;
  created_at: string;
  sources: Source[];
};
export type Conversation = {
  id: string;
  organization_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
};
export type ConversationDetail = Conversation & { messages: Message[] };
export type AskResponse = {
  conversation_id: string;
  user_message_id: string;
  assistant_message_id: string;
  question: string;
  answer: string;
  sources: Source[];
};
