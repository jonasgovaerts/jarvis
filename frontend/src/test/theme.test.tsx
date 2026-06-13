import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppShell } from "../components/AppShell";

function renderShell() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, enabled: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AppShell>
          <p>main content</p>
        </AppShell>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AppShell theme smoke test", () => {
  it("renders the JARVIS sidebar with nav, mono logo and connection orb", () => {
    renderShell();

    // Two wordmarks: the sidebar logo and the mobile (md:hidden) header.
    const logo = screen.getAllByText("Jarvis").find((el) => el.className.includes("text-lg"));
    expect(logo).toBeTruthy();
    // mono uppercase sci-fi treatment on the logo
    expect(logo?.className).toContain("font-mono");
    expect(logo?.className).toContain("uppercase");
    expect(logo?.className).toContain("text-accent");

    for (const label of ["Board", "Tasks", "Chat", "Settings"]) {
      expect(screen.getByRole("link", { name: label })).toBeTruthy();
    }

    // socket never started in tests -> orb reports offline (sidebar + mobile header)
    expect(screen.getAllByText("Link offline").length).toBeGreaterThan(0);
    expect(screen.getByText("main content")).toBeTruthy();
  });
});
