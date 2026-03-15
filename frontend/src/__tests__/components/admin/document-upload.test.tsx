import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DocumentUpload } from "@/components/admin/document-upload";

describe("DocumentUpload", () => {
  it("renders upload area", () => {
    render(<DocumentUpload onUpload={vi.fn()} isUploading={false} />);

    expect(screen.getByText("Завантажити документ")).toBeInTheDocument();
    expect(
      screen.getByText(/Підтримувані формати/)
    ).toBeInTheDocument();
  });

  it("shows file info after selection", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <DocumentUpload onUpload={vi.fn()} isUploading={false} />
    );

    const file = new File(["content"], "test.pdf", {
      type: "application/pdf",
    });
    const fileInput = container.querySelector(
      'input[type="file"]'
    ) as HTMLInputElement;
    await user.upload(fileInput, file);
    expect(screen.getByText("test.pdf")).toBeInTheDocument();
  });

  it("shows uploading state", () => {
    render(<DocumentUpload onUpload={vi.fn()} isUploading={true} />);

    expect(screen.getByText("Завантажити документ")).toBeInTheDocument();
  });

  it("renders description text", () => {
    render(<DocumentUpload onUpload={vi.fn()} isUploading={false} />);

    expect(
      screen.getByText("Підтримувані формати: PDF, DOCX, XLSX (до 10 МБ)")
    ).toBeInTheDocument();
  });
});
