/**
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { vi, describe, test, expect, beforeEach } from "vitest";
import { AdminConfig } from "./AdminConfig";
import {
  getAdminConfig,
  updateAdminConfig,
  getSessionWatchMetrics,
} from "../services/api";

vi.mock("../services/api", () => ({
  getAdminConfig: vi.fn(),
  updateAdminConfig: vi.fn(),
  getSessionWatchMetrics: vi.fn(),
  syncSessionWatchInventory: vi.fn(),
  attestBrowserSession: vi.fn(),
  runLiveLoginSweep: vi.fn(),
  sendClientLog: vi.fn(),
}));

const mockGetAdminConfig = getAdminConfig as ReturnType<typeof vi.fn>;
const mockUpdateAdminConfig = updateAdminConfig as ReturnType<typeof vi.fn>;
const mockGetSessionWatchMetrics = getSessionWatchMetrics as ReturnType<typeof vi.fn>;

describe("AdminConfig Page", () => {
  const defaultConfig = {
    access_policy_id: "accessPolicies/12345",
    Access_Level_Name: "Approved_BYOD_Overlay",
    customer_id: "C012345",
    admin_emails: ["admin@example.com"],
    default_locale: "en",
    company_owned_mode: "USER_ACCESSED_ONLY" as const,
    caa_enforcement_enabled: false,
    session_watch_enabled: false,
    session_watch_dry_run: true,
    session_watch_exempt_admins: false,
    session_watch_grace_seconds: 900,
    session_watch_push_endpoint: "",
  };

  const defaultMetrics = {
    status: "ok",
    session_watch_enabled: false,
    session_watch_dry_run: true,
    session_watch_exempt_admins: false,
    session_watch_grace_seconds: 900,
    metrics: {
      events_evaluated: 4,
      sessions_allowed: 2,
      sessions_revoked: 1,
      audit_would_signout: 1,
      grace_passes_granted: 0,
      errors: 0,
      cached_approved_devices: 3,
      cached_unapproved_devices: 1,
      last_inventory_sync: 1759670000,
    },
    recent_actions: [
      {
        id: 1,
        timestamp: 1759670100,
        user_email: "student@example.com",
        event_name: "LIVE_DEVICE_SYNC_SWEEP_UNAPPROVED",
        ip_address: "device-sync",
        matched_device: "devices/mac-unapproved",
        decision: "AUDIT_WOULD_SIGN_OUT",
        reason: "Unapproved personal device sync detected in Audit-Only mode",
        dry_run: 1,
      },
    ],
  };

  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem("userEmail", "admin@example.com");
    localStorage.setItem("googleIdToken", "mock-admin-token");
    vi.clearAllMocks();
    mockGetAdminConfig.mockResolvedValue({ ...defaultConfig });
    mockGetSessionWatchMetrics.mockResolvedValue(defaultMetrics);
    mockUpdateAdminConfig.mockImplementation(async (newCfg) => ({ ...newCfg }));
  });

  test("renders toggle switches (role='switch') instead of checkboxes and displays button explanations", async () => {
    render(<AdminConfig />);

    await waitFor(() => {
      expect(screen.getByTestId("toggle-session-watch")).toBeInTheDocument();
    });

    const sessionToggle = screen.getByTestId("toggle-session-watch");
    const caaToggle = screen.getByTestId("toggle-caa-enforcement");
    const dryRunToggle = screen.getByTestId("toggle-dry-run");
    const exemptAdminsToggle = screen.getByTestId("toggle-exempt-admins");

    expect(sessionToggle).toHaveAttribute("role", "switch");
    expect(sessionToggle).toHaveAttribute("aria-checked", "false");
    expect(caaToggle).toHaveAttribute("role", "switch");
    expect(caaToggle).toHaveAttribute("aria-checked", "false");
    expect(dryRunToggle).toHaveAttribute("role", "switch");
    expect(dryRunToggle).toHaveAttribute("aria-checked", "true");
    expect(exemptAdminsToggle).toHaveAttribute("role", "switch");
    expect(exemptAdminsToggle).toHaveAttribute("aria-checked", "false");

    // Verify 3-button explanation card is rendered
    const explanationBox = screen.getByTestId("admin-buttons-explanation");
    expect(explanationBox).toBeInTheDocument();
    expect(explanationBox).toHaveTextContent("Sync Inventory Cache");
    expect(explanationBox).toHaveTextContent("Attest Current Session");
    expect(explanationBox).toHaveTextContent("Run Live Login Sweep");
  });

  test("clicking a toggle opens confirmation dialog and confirming auto-saves with confirmation banner", async () => {
    render(<AdminConfig />);

    await waitFor(() => {
      expect(screen.getByTestId("toggle-session-watch")).toBeInTheDocument();
    });

    // Click toggle-session-watch
    fireEvent.click(screen.getByTestId("toggle-session-watch"));

    // Expect confirmation modal to appear
    expect(screen.getByTestId("confirm-toggle-modal")).toBeInTheDocument();
    expect(
      screen.getByText(/Enable Session Management \(Education Fundamentals\)\?/i)
    ).toBeInTheDocument();

    // Confirm & Auto-Save
    fireEvent.click(screen.getByTestId("confirm-autosave-btn"));

    await waitFor(() => {
      expect(mockUpdateAdminConfig).toHaveBeenCalledTimes(1);
    });

    expect(mockUpdateAdminConfig).toHaveBeenCalledWith(
      expect.objectContaining({
        session_watch_enabled: true,
      })
    );

    await waitFor(() => {
      expect(screen.getByTestId("auto-save-confirmation")).toBeInTheDocument();
    });
    expect(screen.getByTestId("auto-save-confirmation")).toHaveTextContent(/Auto-Saved/i);
  });

  test("renders Audit-Only counter and Live Session Enforcement & Audit-Only Log viewer", async () => {
    render(<AdminConfig />);

    await waitFor(() => {
      expect(screen.getByTestId("metric-audit-would-signout")).toBeInTheDocument();
    });

    expect(screen.getByTestId("metric-audit-would-signout")).toHaveTextContent("1");
    expect(screen.getByTestId("admin-audit-log-table")).toBeInTheDocument();
    expect(screen.getByText("student@example.com")).toBeInTheDocument();
    expect(screen.getAllByText(/AUDIT_WOULD_SIGN_OUT/i).length).toBeGreaterThan(0);
  });

  test("changing Default Tenant UI Language (Localization Fallback) immediately localizes Admin UI and auto-saves", async () => {
    render(<AdminConfig />);

    await waitFor(() => {
      expect(screen.getByTestId("default-locale-select")).toBeInTheDocument();
    });

    const localeSelect = screen.getByTestId("default-locale-select");
    expect(localeSelect).toHaveValue("en");

    // Change Default Tenant UI Language to Spanish ('es')
    fireEvent.change(localeSelect, { target: { value: "es" } });

    await waitFor(() => {
      expect(mockUpdateAdminConfig).toHaveBeenCalledWith(
        expect.objectContaining({
          default_locale: "es",
        })
      );
    });

    // Verify Admin UI strings localized to Spanish
    expect(
      screen.getByText("Configuración de Google Workspace")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Administración del Portal de Confianza")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Controles de Administración de Sesiones y Telemetría en Vivo")
    ).toBeInTheDocument();
    expect(
      screen.getByText("1. 🔄 Sincronizar Caché de Inventario:")
    ).toBeInTheDocument();
    expect(screen.getByTestId("auto-save-confirmation")).toHaveTextContent(
      /Guardado automático/i
    );
    expect(localStorage.getItem("userLocale")).toBe("es");
  });
});
