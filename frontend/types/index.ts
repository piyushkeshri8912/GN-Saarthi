export type UserRole = "admin" | "student";

export interface User {
  uid: string;
  email: string;
  role: UserRole;
}

export interface SourceChunk {
  doc_id: string;
  source: string;
  page: number;
  text_content: string;
}

export interface Message {
  id: string;
  sender: "user" | "bot";
  text: string;
  timestamp: string; // ISO string
  sources?: SourceChunk[];
}

export interface DocumentMeta {
  doc_id: string;
  filename: string;
  gcs_uri: string;
  size_bytes: number;
  uploaded_at: string; // ISO string
}

export interface Notice {
  id: string;
  title: string;
  body: string;
  category: string;
  source_email: string;
  date: string;
  created_at: string;
}

export interface Event {
  id: string;
  title: string;
  description: string;
  date: string;
  location: string;
  category: string;
  created_at: string;
}

export interface QuickLink {
  id: string;
  service: string;
  link: string;
  purpose: string;
  created_at?: string;
}

