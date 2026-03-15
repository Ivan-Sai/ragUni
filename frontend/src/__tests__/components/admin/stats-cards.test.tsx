import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatsCards } from "@/components/admin/stats-cards";

describe("StatsCards", () => {
  it("renders all stat cards with values", () => {
    render(
      <StatsCards
        totalUsers={42}
        pendingTeachers={3}
        totalDocuments={15}
        totalChunks={250}
        isLoading={false}
      />
    );

    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("15")).toBeInTheDocument();
    expect(screen.getByText("250")).toBeInTheDocument();
    expect(screen.getByText("Користувачі")).toBeInTheDocument();
    expect(screen.getByText("Документи")).toBeInTheDocument();
  });

  it("shows skeletons when loading", () => {
    const { container } = render(
      <StatsCards
        totalUsers={0}
        pendingTeachers={0}
        totalDocuments={0}
        totalChunks={0}
        isLoading={true}
      />
    );

    // Should not show values when loading
    expect(screen.queryByText("0")).not.toBeInTheDocument();
    // Should have skeleton elements
    const skeletons = container.querySelectorAll("[data-slot='skeleton']");
    expect(skeletons.length).toBe(4);
  });
});
