import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useAdminDocuments } from "@/hooks/use-admin-documents";
import { documentsApi } from "@/lib/api";
import type { DocumentInfo } from "@/types/api";

vi.mock("@/lib/api", () => ({
  documentsApi: {
    list: vi.fn(),
    upload: vi.fn(),
    delete: vi.fn(),
  },
}));

const mockList = vi.mocked(documentsApi.list);
const mockUpload = vi.mocked(documentsApi.upload);
const mockDelete = vi.mocked(documentsApi.delete);

const mockDocuments: DocumentInfo[] = [
  {
    id: "d1",
    filename: "syllabus.pdf",
    file_type: "pdf",
    uploaded_at: "2026-03-01T00:00:00Z",
    total_chunks: 15,
  },
  {
    id: "d2",
    filename: "schedule.xlsx",
    file_type: "xlsx",
    uploaded_at: "2026-03-02T00:00:00Z",
    total_chunks: 8,
  },
];

describe("useAdminDocuments", () => {
  const token = "admin-token";

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetches documents on mount", async () => {
    mockList.mockResolvedValueOnce({ documents: mockDocuments, total: 2 });

    const { result } = renderHook(() => useAdminDocuments({ token }));

    expect(result.current.isLoading).toBe(true);

    await vi.waitFor(() => {
      expect(result.current.documents).toEqual(mockDocuments);
    });

    expect(result.current.total).toBe(2);
    expect(result.current.isLoading).toBe(false);
  });

  it("handles fetch error", async () => {
    mockList.mockRejectedValueOnce(new Error("Server error"));

    const { result } = renderHook(() => useAdminDocuments({ token }));

    await vi.waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.error).toBe("Server error");
  });

  it("uploads a document", async () => {
    mockList.mockResolvedValueOnce({ documents: mockDocuments, total: 2 });
    mockUpload.mockResolvedValueOnce({
      id: "d3",
      filename: "new.docx",
      file_type: "docx",
      uploaded_at: "2026-03-03T00:00:00Z",
      total_chunks: 5,
      message: "Success",
    });

    const { result } = renderHook(() => useAdminDocuments({ token }));

    await vi.waitFor(() => {
      expect(result.current.documents).toHaveLength(2);
    });

    const file = new File(["content"], "new.docx");

    await act(async () => {
      await result.current.uploadDocument(file);
    });

    expect(mockUpload).toHaveBeenCalledWith(file, token);
    expect(result.current.documents).toHaveLength(3);
    expect(result.current.documents[0].filename).toBe("new.docx");
    expect(result.current.total).toBe(3);
  });

  it("deletes a document", async () => {
    mockList.mockResolvedValueOnce({ documents: mockDocuments, total: 2 });
    mockDelete.mockResolvedValueOnce({
      message: "Deleted",
      filename: "syllabus.pdf",
      chunks_deleted: 15,
    });

    const { result } = renderHook(() => useAdminDocuments({ token }));

    await vi.waitFor(() => {
      expect(result.current.documents).toHaveLength(2);
    });

    await act(async () => {
      await result.current.deleteDocument("d1");
    });

    expect(mockDelete).toHaveBeenCalledWith("d1", token);
    expect(result.current.documents).toHaveLength(1);
    expect(result.current.total).toBe(1);
  });

  it("handles upload error", async () => {
    mockList.mockResolvedValueOnce({ documents: [], total: 0 });
    mockUpload.mockRejectedValueOnce(new Error("File too large"));

    const { result } = renderHook(() => useAdminDocuments({ token }));

    await vi.waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    const file = new File(["content"], "huge.pdf");

    let thrownError: Error | undefined;
    await act(async () => {
      try {
        await result.current.uploadDocument(file);
      } catch (err) {
        thrownError = err as Error;
      }
    });

    expect(thrownError?.message).toBe("File too large");
    expect(result.current.error).toBe("File too large");
    expect(result.current.isUploading).toBe(false);
  });

  it("does not fetch when token is empty", async () => {
    renderHook(() => useAdminDocuments({ token: "" }));

    expect(mockList).not.toHaveBeenCalled();
  });
});
