import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ThemeButton, ThemeChoice } from "../components/ThemeSwitch";
import { getTheme, resetTheme } from "./theme";

const root = document.documentElement;

describe("theme", () => {
  it("follows the system until one is chosen", () => {
    expect(getTheme()).toBe("system");
    expect(root.hasAttribute("data-theme")).toBe(false);
  });

  it("the top bar button switches to the other theme and remembers it", async () => {
    render(<ThemeButton />);
    // jsdom reports no dark preference, so the page starts light.
    await userEvent.click(screen.getByRole("button", { name: "Switch to dark theme" }));
    expect(root.getAttribute("data-theme")).toBe("dark");
    expect(localStorage.getItem("fincore:theme")).toBe("dark");

    await userEvent.click(screen.getByRole("button", { name: "Switch to light theme" }));
    expect(root.getAttribute("data-theme")).toBe("light");

    resetTheme();
    expect(getTheme()).toBe("light");
  });

  it("the account page offers all three, and the device's own again", async () => {
    render(<ThemeChoice />);
    await userEvent.click(screen.getByRole("button", { name: "Dark" }));
    expect(screen.getByRole("button", { name: "Dark" })).toHaveAttribute("aria-pressed", "true");

    await userEvent.click(screen.getByRole("button", { name: "Same as device" }));
    expect(root.hasAttribute("data-theme")).toBe(false);
    expect(localStorage.getItem("fincore:theme")).toBeNull();
  });
});
