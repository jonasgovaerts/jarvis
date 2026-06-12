import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { AppShell } from "../components/AppShell";

describe("AppShell theme smoke test", () => {
  it("renders the JARVIS sidebar with nav, mono logo and connection orb", () => {
    render(
      <MemoryRouter>
        <AppShell>
          <p>main content</p>
        </AppShell>
      </MemoryRouter>,
    );

    const logo = screen.getByText("Jarvis");
    expect(logo).toBeTruthy();
    // mono uppercase sci-fi treatment on the logo
    expect(logo.className).toContain("font-mono");
    expect(logo.className).toContain("uppercase");
    expect(logo.className).toContain("text-accent");

    for (const label of ["Board", "Tasks", "Chat", "Settings"]) {
      expect(screen.getByRole("link", { name: label })).toBeTruthy();
    }

    // socket never started in tests -> orb reports offline
    expect(screen.getByText("Link offline")).toBeTruthy();
    expect(screen.getByText("main content")).toBeTruthy();
  });
});
