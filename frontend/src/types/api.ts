/** Types matching the FastAPI backend models */

export type UserRole = "student" | "teacher" | "admin";

export type StudyLevel = "bachelor" | "master" | "phd";

export interface FacultyResponse {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
}

export interface GroupResponse {
  id: string;
  name: string;
  faculty_id: string;
  faculty_name: string | null;
  level: StudyLevel;
  created_at: string;
  updated_at: string;
}

export interface FacultyCreateData {
  name: string;
}

export interface GroupCreateData {
  name: string;
  faculty_id: string;
  level: StudyLevel;
}

export interface GroupUpdateData {
  name?: string;
  faculty_id?: string;
  level?: StudyLevel;
}

export interface UserResponse {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  faculty_id: string | null;
  faculty_name: string | null;
  group_id: string | null;
  group_name: string | null;
  year: number | null;
  level: StudyLevel | null;
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
  role: "student" | "teacher";
  faculty_id: string;
  /** Mandatory when role === "student". */
  group_id?: string;
  year?: number;
  level?: StudyLevel;
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
  department?: string;
  position?: string;
}

/** Admin-only profile edit — adds dictionary fields the user cannot
 * change themselves. */
export interface AdminUserUpdateData {
  full_name?: string;
  faculty_id?: string;
  group_id?: string;
  year?: number;
  level?: StudyLevel;
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
  /** ID of the parent document — lets the UI fetch the full preview. */
  document_id?: string;
  /** PDF page number recovered from the chunk's position in the source. */
  page?: number;
}

/** A single LLM-extracted record. Shape depends on the source document
 * (class slot, exam, credit, …) — see app/services/llm_extractor.py
 * for conventional keys. We keep it loose on purpose so unfamiliar
 * fields still render. */
export type StructuredRecord = Record<string, string | number | null>;

export interface DocumentPreviewResponse {
  id: string;
  filename: string;
  file_type: string;
  total_chunks: number;
  /** Original parser output — what pdfplumber / docx / pandas saw. */
  text: string;
  /**
   * One-line-per-record rendering produced by the LLM extractor when
   * the admin uploaded with the "complex schedule" flag. Null when
   * the document was indexed as raw text.
   */
  structured_text: string | null;
  /** Same data as structured_text but as JSON — the preview UI renders
   * these as cards instead of forcing the user to read flat key:value
   * lines. */
  structured_records: StructuredRecord[];
  extraction_method: "raw" | "llm";
  structured_records_count: number;
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
  access_level: string;
  faculty_id: string | null;
  target_group_ids: string[];
  target_years: number[];
  target_level: StudyLevel | null;
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
  access_level: string;
  faculty_id: string;
  faculty_name: string | null;
  target_group_ids: string[];
  target_group_names: string[];
  target_years: number[];
  target_level: StudyLevel | null;
  uploaded_at: string;
  total_chunks: number;
  message: string;
}

/** Audience targeting payload that the upload form must supply.
 * The backend classifier picks the right extractor automatically —
 * the upload form no longer asks the admin to label complex tables
 * by hand. */
export interface DocumentUploadOptions {
  facultyId: string;
  targetGroupIds: string[];
  targetYears: number[];
  targetLevel: StudyLevel | null;
  accessLevel: "public" | "faculty" | "restricted";
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
