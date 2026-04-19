/** Types matching the FastAPI backend models */

export type UserRole = "student" | "teacher" | "admin";

export interface UserResponse {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  faculty: string | null;
  group: string | null;
  year: number | null;
  department: string | null;
  position: string | null;
  is_approved: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string | null;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface AccessTokenResponse {
  access_token: string;
  token_type: string;
}

export interface RegisterData {
  email: string;
  password: string;
  full_name: string;
  role: UserRole;
  faculty: string;
  group?: string;
  year?: number;
  department?: string;
  position?: string;
}

export interface LoginData {
  email: string;
  password: string;
}

export interface ApiError {
  detail: string;
}

// --- Password management types ---

export interface ChangePasswordData {
  current_password: string;
  new_password: string;
}

export interface ForgotPasswordData {
  email: string;
}

export interface ResetPasswordData {
  token: string;
  new_password: string;
}

export interface ProfileUpdateData {
  full_name?: string;
  faculty?: string;
  group?: string;
  year?: number;
  department?: string;
  position?: string;
}

export interface MessageResponse {
  message: string;
}

// --- Feedback types ---

export interface FeedbackData {
  session_id: string;
  message_index: number;
  feedback_type: "thumbs_up" | "thumbs_down";
  comment?: string;
}

export interface FeedbackResponse {
  id: string;
  session_id: string;
  message_index: number;
  feedback_type: "thumbs_up" | "thumbs_down";
  comment: string | null;
  created_at: string;
}

export interface FeedbackStats {
  total_feedback: number;
  thumbs_up: number;
  thumbs_down: number;
  satisfaction_rate: number;
}

// --- Chat types ---

export interface ChatSource {
  source_file: string;
  file_type: string;
  chunk_index: number;
  total_chunks: number;
  text: string;
  score?: number;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources: ChatSource[];
  timestamp: string;
}

export interface ChatSession {
  _id: string;
  user_id: string;
  session_id: string;
  title: string | null;
  messages: ChatMessage[];
  created_at: string;
  updated_at: string;
}

export interface ChatSessionPreview {
  _id: string;
  user_id: string;
  session_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface AskRequest {
  question: string;
  session_id?: string;
}

// --- Admin types ---

export interface UsersListResponse {
  users: UserResponse[];
  total: number;
}

export interface BlockRequest {
  is_active: boolean;
}

export interface RoleChangeRequest {
  role: UserRole;
}

export interface AdminActionResponse {
  message: string;
  user_id: string;
}

// --- Document types ---

export interface DocumentInfo {
  id: string;
  filename: string;
  file_type: string;
  uploaded_at: string;
  total_chunks: number;
}

export interface DocumentsListResponse {
  documents: DocumentInfo[];
  total: number;
}

export interface DocumentDeleteResponse {
  message: string;
  filename: string;
  chunks_deleted: number;
}

export interface DocumentUploadResponse {
  id: string;
  filename: string;
  file_type: string;
  uploaded_at: string;
  total_chunks: number;
  message: string;
}

export interface VectorStoreStats {
  total_chunks: number;
  unique_documents: number;
  embedding_model: string;
  embedding_dimension: number;
  chunk_size: number;
  chunk_overlap: number;
}

export interface DocumentStats {
  documents: {
    total: number;
    by_type: Record<string, number>;
  };
  vector_store: VectorStoreStats;
}

// --- System health ---

export interface HealthComponents {
  database: "connected" | string;
  vector_store: "initialized" | string;
  llm: "configured" | "unhealthy" | string;
}

export interface HealthStatistics {
  documents_count: number;
  total_chunks: number;
  unique_documents: number;
  embedding_model: string;
  embedding_dimension: number;
  chunk_size: number;
  chunk_overlap: number;
}

export interface HealthConfiguration {
  embedding_model: string;
  llm_model: string;
  chunk_size: number;
  chunk_overlap: number;
  top_k_results: number;
}

export interface SystemHealth {
  status: "healthy" | "unhealthy";
  components: HealthComponents;
  statistics: HealthStatistics;
  configuration: HealthConfiguration;
  /** Present only when status is "unhealthy" */
  error?: string;
}
