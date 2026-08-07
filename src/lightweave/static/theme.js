"use strict";

const THEME_STORAGE_KEY = "lightweave-theme";

function preferredTheme() {
  const saved = localStorage.getItem(THEME_STORAGE_KEY);
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  for (const button of document.querySelectorAll("[data-theme-toggle]")) {
    const next = theme === "dark" ? "light" : "dark";
    button.textContent = `${next} mode`;
    button.setAttribute("aria-label", `Switch to ${next} mode`);
    button.setAttribute("aria-pressed", String(theme === "light"));
  }
}

applyTheme(preferredTheme());

window.addEventListener("DOMContentLoaded", () => {
  applyTheme(document.documentElement.dataset.theme || preferredTheme());
  for (const button of document.querySelectorAll("[data-theme-toggle]")) {
    button.addEventListener("click", () => {
      const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      localStorage.setItem(THEME_STORAGE_KEY, next);
      applyTheme(next);
    });
  }
});
