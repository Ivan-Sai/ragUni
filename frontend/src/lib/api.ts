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
  DocumentStats,
  SystemHealth,
  UserRole,
} from "@/types/api";
import { API_BASE_URL, API_PREFIX } from "@/lib/env";

class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

interface RequestOptions {
  token?: string;
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  options?: RequestOptions & { headers?: Record<string, string> }
): Promise<T> {
  const url = `${API_BASE_URL}${API_PREFIX}${path}`;

  const headers: Record<string, string> = {
    ...(options?.headers || {}),
  };

  if (options?.token) {
    headers["Authorization"] = `Bearer ${options.token}`;
  }

  // Default to JSON content type for non-form requests
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

  const response = await fetch(url, config);

  if (!response.ok) {
    // If an authenticated request comes back 401 the token is no longer
    // valid (expired, revoked, or signed with a different secret). The
    // session is dead — sign the user out so the UI falls back to the
    // login screen instead of rendering half-broken pages. Skipped on
    // the server and for unauthenticated calls so the login form can
    // still surface "wrong password" errors as 401.
    if (
      response.status === 401 &&
      Boolean(options?.token) &&
      typeof window !== "undefined"
    ) {
      const { signOut } = await import("next-auth/react");
      await signOut({ callbackUrl: "/login" });
    }

    let detail = "Помилка сервера";
    try {
      const errorData = await response.json();
      if (errorData.detail && typeof errorData.detail === "string") {
        // Only show server messages for client errors (4xx), not server errors (5xx)
        if (response.status >= 400 && response.status < 500) {
          detail = errorData.detail;
        }
      }
    } catch {
      // JSON parse failed — response may not be JSON
    }
    throw new ApiError(detail, response.status);
  }

  return response.json();
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
      let detail = "Помилка сервера";
      try {
        const errorData = await response.json();
        if (errorData.detail) {
          detail = errorData.detail;
        }
      } catch (parseError) {
        // JSON parse failed — response may not be JSON
        if (process.env.NODE_ENV === "development") {
          console.warn("Failed to parse chat error response as JSON:", parseError);
        }
      }
      throw new ApiError(detail, response.status);
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

  async getFeedbackStats(token: string): Promise<FeedbackStats> {
    return apiClient.get<FeedbackStats>("/chat/feedback/stats", { token });
  },

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async getAnalytics(token: string, days = 30): Promise<any> {
    return apiClient.get(`/admin/analytics?days=${days}`, { token });
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
    token: string
  ): Promise<DocumentUploadResponse> {
    const formData = new FormData();
    formData.append("file", file);

    const url = `${API_BASE_URL}${API_PREFIX}/documents/upload`;
    const response = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
      },
      body: formData,
    });

    if (!response.ok) {
      let detail = "Помилка завантаження";
      try {
        const errorData = await response.json();
        if (errorData.detail) detail = errorData.detail;
      } catch (parseError) {
        // JSON parse failed — response may not be JSON
        if (process.env.NODE_ENV === "development") {
          console.warn("Failed to parse upload error response as JSON:", parseError);
        }
      }
      throw new ApiError(detail, response.status);
    }

    return response.json();
  },

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async getPreview(documentId: string, token: string): Promise<any> {
    return apiClient.get(`/documents/${documentId}/preview`, { token });
  },

  async getStats(token: string): Promise<DocumentStats> {
    return apiClient.get<DocumentStats>("/documents/stats", { token });
  },

  async getHealth(token: string): Promise<SystemHealth> {
    return apiClient.get<SystemHealth>("/chat/health", { token });
  },
};
