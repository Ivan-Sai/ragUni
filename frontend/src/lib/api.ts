import type {
  TokenResponse,
  AccessTokenResponse,
  UserResponse,
  RegisterData,
  LoginData,
  ChangePasswordData,
  ForgotPasswordData,
  ResetPasswordData,
  ProfileUpdateData,
  AdminUserUpdateData,
  MessageResponse,
  FeedbackData,
  FeedbackResponse,
  FeedbackStats,
  ChatSession,
  ChatSessionPreview,
  AskRequest,
  UsersListResponse,
  AdminActionResponse,
  DocumentsListResponse,
  DocumentDeleteResponse,
  DocumentUploadResponse,
  DocumentUploadOptions,
  DocumentPreviewResponse,
  DocumentStats,
  FacultyResponse,
  FacultyCreateData,
  GroupResponse,
  GroupCreateData,
  GroupUpdateData,
  StudyLevel,
  SystemHealth,
  AnalyticsSummary,
  UserRole,
} from "@/types/api";
import { API_BASE_URL, API_PREFIX } from "@/lib/env";

/**
 * Stable error codes thrown by the API layer.
 *
 * The strings are intentionally English / kebab-case rather than
 * localised UI copy — components MUST translate them via
 * `useTranslations()` (CLAUDE.md i18n rule) instead of rendering
 * the code directly. Server-supplied detail strings are only
 * preserved for 4xx client errors where the message is meant for
 * the user (e.g. validation failures); 5xx detail is replaced
 * with `server_error` so internal exceptions never leak.
 */
class ApiError extends Error {
  status: number;
  /** Stable machine code: `network_error`, `timeout`, `server_error`, etc. */
  code: string;

  constructor(code: string, status: number, message?: string) {
    super(message ?? code);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

interface RequestOptions {
  token?: string;
  /** Override the per-request timeout in milliseconds. */
  timeoutMs?: number;
}

const DEFAULT_TIMEOUT_MS = 15_000;

/**
 * Decide whether a fetch failure is worth retrying. Network blips,
 * AbortErrors with a synthetic timeout signal, and TypeErrors raised
 * by the platform when DNS or TCP fails all qualify. Application-level
 * errors (4xx/5xx HTTP responses) are NOT retried here — the call
 * site decides what to do with them.
 */
function isTransientFetchFailure(err: unknown): boolean {
  if (err instanceof DOMException && err.name === "AbortError") return true;
  if (err instanceof TypeError) return true; // browser network errors
  return false;
}

async function fetchWithTimeout(
  url: string,
  init: RequestInit,
  timeoutMs: number,
): Promise<Response> {
  // AbortSignal.timeout() is supported in all modern browsers + Node 20+.
  // It auto-aborts if the request takes longer than `timeoutMs` ms,
  // surfacing a DOMException(name="AbortError") that we map to an
  // ApiError("timeout") below.
  return fetch(url, {
    ...init,
    signal: AbortSignal.timeout(timeoutMs),
  });
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  options?: RequestOptions & { headers?: Record<string, string> }
): Promise<T> {
  const url = `${API_BASE_URL}${API_PREFIX}${path}`;
  const timeoutMs = options?.timeoutMs ?? DEFAULT_TIMEOUT_MS;

  const headers: Record<string, string> = {
    ...(options?.headers || {}),
  };

  if (options?.token) {
    headers["Authorization"] = `Bearer ${options.token}`;
  }

  if (body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const config: RequestInit = {
    method,
    headers,
  };

  if (body) {
    if (headers["Content-Type"] === "application/json") {
      config.body = JSON.stringify(body);
    } else {
      config.body = body as BodyInit;
    }
  }

  // Idempotent GETs get one transparent retry on transient network
  // failures. Non-idempotent verbs (POST/PUT/DELETE) are NOT retried
  // because we can't tell whether the server processed the request
  // before the connection died; double-charging or double-deleting is
  // worse than a visible failure.
  const maxAttempts = method === "GET" ? 2 : 1;
  let lastErr: unknown;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const response = await fetchWithTimeout(url, config, timeoutMs);

      if (!response.ok) {
        // 401 on an authenticated request means the session is dead —
        // sign the user out so the UI doesn't keep stale state.
        if (
          response.status === 401 &&
          Boolean(options?.token) &&
          typeof window !== "undefined"
        ) {
          const { signOut } = await import("next-auth/react");
          await signOut({ callbackUrl: "/login" });
        }

        let code = response.status >= 500 ? "server_error" : "request_failed";
        let serverMessage: string | undefined;
        try {
          const errorData = await response.json();
          if (
            errorData?.detail &&
            typeof errorData.detail === "string" &&
            response.status >= 400 &&
            response.status < 500
          ) {
            serverMessage = errorData.detail;
            code = "request_failed";
          }
        } catch {
          /* response wasn't JSON — keep the generic code */
        }
        throw new ApiError(code, response.status, serverMessage);
      }

      return response.json();
    } catch (err) {
      lastErr = err;
      if (err instanceof ApiError) throw err;
      if (attempt < maxAttempts && isTransientFetchFailure(err)) {
        // Linear backoff is fine here — the user is waiting and we
        // only retry once. A 250 ms gap is enough to clear most
        // transient DNS / TCP hiccups without blocking the UI.
        await new Promise((resolve) => setTimeout(resolve, 250));
        continue;
      }
      if (err instanceof DOMException && err.name === "AbortError") {
        throw new ApiError("timeout", 0, "Request timed out");
      }
      throw new ApiError("network_error", 0, "Network request failed");
    }
  }
  // Unreachable, but TypeScript needs it.
  throw lastErr ?? new ApiError("network_error", 0);
}

export const apiClient = {
  get<T = unknown>(path: string, options?: RequestOptions): Promise<T> {
    return request<T>("GET", path, undefined, options);
  },

  post<T = unknown>(
    path: string,
    body?: unknown,
    options?: RequestOptions & { headers?: Record<string, string> }
  ): Promise<T> {
    return request<T>("POST", path, body, options);
  },

  put<T = unknown>(
    path: string,
    body?: unknown,
    options?: RequestOptions
  ): Promise<T> {
    return request<T>("PUT", path, body, options);
  },

  delete<T = unknown>(path: string, options?: RequestOptions): Promise<T> {
    return request<T>("DELETE", path, undefined, options);
  },
};

export const authApi = {
  async login(data: LoginData): Promise<TokenResponse> {
    const formBody = new URLSearchParams({
      username: data.email,
      password: data.password,
    }).toString();

    return request<TokenResponse>("POST", "/auth/login", formBody, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
  },

  async register(data: RegisterData): Promise<UserResponse> {
    return apiClient.post<UserResponse>("/auth/register", data);
  },

  async refresh(refreshToken: string): Promise<AccessTokenResponse> {
    return apiClient.post<AccessTokenResponse>("/auth/refresh", {
      refresh_token: refreshToken,
    });
  },

  async getMe(token: string): Promise<UserResponse> {
    return apiClient.get<UserResponse>("/auth/me", { token });
  },

  async changePassword(
    data: ChangePasswordData,
    token: string
  ): Promise<MessageResponse> {
    return apiClient.put<MessageResponse>("/auth/password", data, { token });
  },

  async forgotPassword(data: ForgotPasswordData): Promise<MessageResponse> {
    return apiClient.post<MessageResponse>("/auth/forgot-password", data);
  },

  async resetPassword(data: ResetPasswordData): Promise<MessageResponse> {
    return apiClient.post<MessageResponse>("/auth/reset-password", data);
  },

  async updateProfile(
    data: ProfileUpdateData,
    token: string
  ): Promise<UserResponse> {
    return apiClient.put<UserResponse>("/auth/profile", data, { token });
  },
};

export const chatApi = {
  async getHistory(token: string): Promise<ChatSessionPreview[]> {
    return apiClient.get<ChatSessionPreview[]>("/chat/history", { token });
  },

  async getSession(sessionId: string, token: string): Promise<ChatSession> {
    return apiClient.get<ChatSession>(`/chat/history/${sessionId}`, { token });
  },

  async deleteSession(
    sessionId: string,
    token: string
  ): Promise<{ message: string }> {
    return apiClient.delete<{ message: string }>(`/chat/history/${sessionId}`, {
      token,
    });
  },

  async submitFeedback(
    data: FeedbackData,
    token: string
  ): Promise<FeedbackResponse> {
    return apiClient.post<FeedbackResponse>("/chat/feedback", data, { token });
  },

  async askQuestion(data: AskRequest, token: string): Promise<Response> {
    // SSE streaming — caller owns the response body and passes its
    // own AbortSignal for cancellation. We don't apply the shared
    // 15 s timeout here because LLM responses can legitimately stream
    // for 30-60 s; the chat hook handles its own watchdog.
    const url = `${API_BASE_URL}${API_PREFIX}/chat/ask/stream`;
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      let code = response.status >= 500 ? "server_error" : "request_failed";
      let serverMessage: string | undefined;
      try {
        const errorData = await response.json();
        if (
          errorData?.detail &&
          typeof errorData.detail === "string" &&
          response.status >= 400 &&
          response.status < 500
        ) {
          serverMessage = errorData.detail;
          code = "request_failed";
        }
      } catch (parseError) {
        if (process.env.NODE_ENV === "development") {
          console.warn("Failed to parse chat error response as JSON:", parseError);
        }
      }
      throw new ApiError(code, response.status, serverMessage);
    }

    return response;
  },
};

export const adminApi = {
  async getUsers(
    token: string,
    skip = 0,
    limit = 50
  ): Promise<UsersListResponse> {
    return apiClient.get<UsersListResponse>(
      `/admin/users?skip=${skip}&limit=${limit}`,
      { token }
    );
  },

  async getPendingTeachers(token: string): Promise<UserResponse[]> {
    return apiClient.get<UserResponse[]>("/admin/users/pending", { token });
  },

  async approveTeacher(
    userId: string,
    token: string
  ): Promise<AdminActionResponse> {
    return apiClient.put<AdminActionResponse>(
      `/admin/users/${userId}/approve`,
      undefined,
      { token }
    );
  },

  async rejectTeacher(
    userId: string,
    token: string
  ): Promise<AdminActionResponse> {
    return apiClient.put<AdminActionResponse>(
      `/admin/users/${userId}/reject`,
      undefined,
      { token }
    );
  },

  async blockUser(
    userId: string,
    isActive: boolean,
    token: string
  ): Promise<AdminActionResponse> {
    return apiClient.put<AdminActionResponse>(
      `/admin/users/${userId}/block`,
      { is_active: isActive },
      { token }
    );
  },

  async changeRole(
    userId: string,
    role: UserRole,
    token: string
  ): Promise<AdminActionResponse> {
    return apiClient.put<AdminActionResponse>(
      `/admin/users/${userId}/role`,
      { role },
      { token }
    );
  },

  async updateUser(
    userId: string,
    data: AdminUserUpdateData,
    token: string,
  ): Promise<UserResponse> {
    return apiClient.put<UserResponse>(`/admin/users/${userId}`, data, { token });
  },

  async getFeedbackStats(token: string): Promise<FeedbackStats> {
    return apiClient.get<FeedbackStats>("/chat/feedback/stats", { token });
  },

  async getAnalytics(token: string, days = 30): Promise<AnalyticsSummary> {
    return apiClient.get<AnalyticsSummary>(`/admin/analytics?days=${days}`, {
      token,
    });
  },
};

export const documentsApi = {
  async list(token: string): Promise<DocumentsListResponse> {
    return apiClient.get<DocumentsListResponse>("/documents/list", { token });
  },

  async delete(
    documentId: string,
    token: string
  ): Promise<DocumentDeleteResponse> {
    return apiClient.delete<DocumentDeleteResponse>(
      `/documents/${documentId}`,
      { token }
    );
  },

  async upload(
    file: File,
    token: string,
    options: DocumentUploadOptions,
  ): Promise<DocumentUploadResponse> {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("access_level", options.accessLevel);
    formData.append("faculty_id", options.facultyId);
    formData.append("target_group_ids", JSON.stringify(options.targetGroupIds));
    formData.append("target_years", JSON.stringify(options.targetYears));
    if (options.targetLevel) {
      formData.append("target_level", options.targetLevel);
    }

    const url = `${API_BASE_URL}${API_PREFIX}/documents/upload`;
    const response = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
      },
      body: formData,
    });

    if (!response.ok) {
      let code = response.status >= 500 ? "server_error" : "upload_failed";
      let serverMessage: string | undefined;
      try {
        const errorData = await response.json();
        if (
          errorData?.detail &&
          typeof errorData.detail === "string" &&
          response.status >= 400 &&
          response.status < 500
        ) {
          serverMessage = errorData.detail;
          code = "upload_failed";
        }
      } catch (parseError) {
        if (process.env.NODE_ENV === "development") {
          console.warn("Failed to parse upload error response as JSON:", parseError);
        }
      }
      throw new ApiError(code, response.status, serverMessage);
    }

    return response.json();
  },

  async getPreview(
    documentId: string,
    token: string,
  ): Promise<DocumentPreviewResponse> {
    return apiClient.get<DocumentPreviewResponse>(
      `/documents/${documentId}/preview`,
      { token },
    );
  },

  async getStats(token: string): Promise<DocumentStats> {
    return apiClient.get<DocumentStats>("/documents/stats", { token });
  },

  async getHealth(token: string): Promise<SystemHealth> {
    return apiClient.get<SystemHealth>("/chat/health", { token });
  },
};

/**
 * Faculty / Group reference dictionaries.
 *
 * Read endpoints have a public variant ("/public") so the registration
 * form can populate dropdowns before the user has a token. Write
 * endpoints (create / update / delete) are admin-only.
 */
export const dictionariesApi = {
  async listFacultiesPublic(): Promise<FacultyResponse[]> {
    return apiClient.get<FacultyResponse[]>("/dictionaries/faculties/public");
  },

  async listFaculties(token: string): Promise<FacultyResponse[]> {
    return apiClient.get<FacultyResponse[]>("/dictionaries/faculties", { token });
  },

  async createFaculty(
    data: FacultyCreateData,
    token: string,
  ): Promise<FacultyResponse> {
    return apiClient.post<FacultyResponse>("/dictionaries/faculties", data, {
      token,
    });
  },

  async updateFaculty(
    id: string,
    data: FacultyCreateData,
    token: string,
  ): Promise<FacultyResponse> {
    return apiClient.put<FacultyResponse>(
      `/dictionaries/faculties/${id}`,
      data,
      { token },
    );
  },

  async deleteFaculty(id: string, token: string): Promise<void> {
    await apiClient.delete<void>(`/dictionaries/faculties/${id}`, { token });
  },

  async listGroupsPublic(
    facultyId?: string,
    level?: StudyLevel,
  ): Promise<GroupResponse[]> {
    const params = new URLSearchParams();
    if (facultyId) params.append("faculty_id", facultyId);
    if (level) params.append("level", level);
    const query = params.toString() ? `?${params.toString()}` : "";
    return apiClient.get<GroupResponse[]>(`/dictionaries/groups/public${query}`);
  },

  async listGroups(
    token: string,
    facultyId?: string,
    level?: StudyLevel,
  ): Promise<GroupResponse[]> {
    const params = new URLSearchParams();
    if (facultyId) params.append("faculty_id", facultyId);
    if (level) params.append("level", level);
    const query = params.toString() ? `?${params.toString()}` : "";
    return apiClient.get<GroupResponse[]>(`/dictionaries/groups${query}`, {
      token,
    });
  },

  async createGroup(
    data: GroupCreateData,
    token: string,
  ): Promise<GroupResponse> {
    return apiClient.post<GroupResponse>("/dictionaries/groups", data, {
      token,
    });
  },

  async updateGroup(
    id: string,
    data: GroupUpdateData,
    token: string,
  ): Promise<GroupResponse> {
    return apiClient.put<GroupResponse>(`/dictionaries/groups/${id}`, data, {
      token,
    });
  },

  async deleteGroup(id: string, token: string): Promise<void> {
    await apiClient.delete<void>(`/dictionaries/groups/${id}`, { token });
  },
};
