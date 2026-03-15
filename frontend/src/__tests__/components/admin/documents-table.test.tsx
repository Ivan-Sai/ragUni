import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { DocumentsTable } from "@/components/admin/documents-table";
import type { DocumentInfo } from "@/types/api";

const mockDocuments: DocumentInfo[] = [
  {
    id: "d1",
    filename: "syllabus.pdf",
    file_type: "pdf",
    uploaded_at: "2026-03-01T10:00:00Z",
    total_chunks: 15,
  },
  {
    id: "d2",
    filename: "schedule.xlsx",
    file_type: "xlsx",
    uploaded_at: "2026-03-02T14:30:00Z",
    total_chunks: 8,
  },
];

describe("DocumentsTable", () => {
  it("renders document rows", () => {
    render(
      <DocumentsTable
        documents={mockDocuments}
        isLoading={false}
        onDelete={vi.fn()}
      />
    );

    expect(screen.getByText("syllabus.pdf")).toBeInTheDocument();
    expect(screen.getByText("schedule.xlsx")).toBeInTheDocument();
    expect(screen.getByText("PDF")).toBeInTheDocument();
    expect(screen.getByText("XLSX")).toBeInTheDocument();
    expect(screen.getByText("15")).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
  });

  it("shows empty state when no documents", () => {
    render(
      <DocumentsTable
        documents={[]}
        isLoading={false}
        onDelete={vi.fn()}
      />
    );

    expect(screen.getByText("Документів не знайдено")).toBeInTheDocument();
  });

  it("shows skeletons when loading", () => {
    const { container } = render(
      <DocumentsTable
        documents={[]}
        isLoading={true}
        onDelete={vi.fn()}
      />
    );

    const skeletons = container.querySelectorAll("[data-slot='skeleton']");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("renders delete buttons for each document", () => {
    render(
      <DocumentsTable
        documents={mockDocuments}
        isLoading={false}
        onDelete={vi.fn()}
      />
    );

    const deleteButtons = screen.getAllByRole("button");
    expect(deleteButtons).toHaveLength(2);
  });
});
