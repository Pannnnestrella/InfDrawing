import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  apiFetch,
  clearSessionApiKey,
  getSessionApiKey,
  setSessionApiKey,
} from "./api-client";

describe("API key request helper", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("stores the key only in sessionStorage", () => {
    const localStorageSet = vi.spyOn(Storage.prototype, "setItem");

    setSessionApiKey("  infd_secret  ");

    expect(getSessionApiKey()).toBe("infd_secret");
    expect(window.sessionStorage.getItem("infd.api-key")).toBe("infd_secret");
    expect(window.localStorage.getItem("infd.api-key")).toBeNull();
    expect(localStorageSet).toHaveBeenCalledTimes(1);
  });

  it("injects X-API-Key while preserving caller headers", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}"));
    vi.stubGlobal("fetch", fetchMock);
    setSessionApiKey("infd_secret");

    await apiFetch("/api/v1/agent/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    const headers = init.headers as Headers;
    expect(headers.get("X-API-Key")).toBe("infd_secret");
    expect(headers.get("Content-Type")).toBe("application/json");
  });

  it("allows development requests without a key", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}"));
    vi.stubGlobal("fetch", fetchMock);
    clearSessionApiKey();

    await apiFetch("/api/v1/system/capabilities");

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Headers).has("X-API-Key")).toBe(false);
  });
});
