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
  getDirectoryMetadata,
} from "../services/api";

vi.mock("../services/api", () => ({
  getAdminConfig: vi.fn(),
  updateAdminConfig: vi.fn(),
  getSessionWatchMetrics: vi.fn(),
  getDirectoryMetadata: vi.fn(),
  syncSessionWatchInventory: vi.fn(),
  attestBrowserSession: vi.fn(),
  runLiveLoginSweep: vi.fn(),
  sendClientLog: vi.fn(),
}));

const mockGetAdminConfig = getAdminConfig as ReturnType<typeof vi.fn>;
const mockUpdateAdminConfig = updateAdminConfig as ReturnType<typeof vi.fn>;
const mockGetSessionWatchMetrics = getSessionWatchMetrics as ReturnType<typeof vi.fn>;
const mockGetDirectoryMetadata = getDirectoryMetadata as ReturnType<typeof vi.fn>;

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
    mockGetDirectoryMetadata.mockResolvedValue({
      status: "ok",
      organizational_units: [
        { org_unit_path: "/", name: "Root Domain (/)", parent_path: "", depth: 0 },
        { org_unit_path: "/Students", name: "Students", parent_path: "/", depth: 1 },
        { org_unit_path: "/Students/MiddleSchool", name: "MiddleSchool", parent_path: "/Students", depth: 2 },
        { org_unit_path: "/Staff", name: "Staff", parent_path: "/", depth: 1 },
      ],
      groups: [
        { email: "students-byod@school.edu", name: "Students BYOD", description: "BYOD group" },
        { email: "cookie-sentinel-pilot@school.edu", name: "Cookie Sentinel Pilot", description: "Pilot group" },
      ],
    });
    mockUpdateAdminConfig.mockImplementation(async (newCfg) => ({ ...newCfg }));
  });

  test("renders toggle switches (role='switch') with green ON color (#137333) and no manual diagnostic buttons", async () => {
    render(<AdminConfig />);

    await waitFor(() => {
      expect(screen.getByTestId("toggle-session-watch")).toBeInTheDocument();
    });

    const sessionToggle = screen.getByTestId("toggle-session-watch");
    const cookieToggle = screen.getByTestId("toggle-cookie-threat-detection");
    const dryRunToggle = screen.getByTestId("toggle-dry-run");
    const exemptAdminsToggle = screen.getByTestId("toggle-exempt-admins");

    expect(sessionToggle).toHaveAttribute("role", "switch");
    expect(sessionToggle).toHaveAttribute("aria-checked", "false");
    expect(cookieToggle).toHaveAttribute("role", "switch");
    expect(cookieToggle).toHaveAttribute("aria-checked", "false");
    expect(screen.queryByTestId("toggle-caa-enforcement")).not.toBeInTheDocument();
    expect(dryRunToggle).toHaveAttribute("role", "switch");
    expect(dryRunToggle).toHaveAttribute("aria-checked", "true");
    // Verify ON toggle is green (#137333)
    expect(dryRunToggle).toHaveStyle({ backgroundColor: "#137333" });
    expect(exemptAdminsToggle).toHaveAttribute("role", "switch");
    expect(exemptAdminsToggle).toHaveAttribute("aria-checked", "false");

    // Verify manual diagnostic buttons and in-page log table are removed
    expect(screen.queryByTestId("admin-session-watch-operations")).not.toBeInTheDocument();
    expect(screen.queryByTestId("admin-buttons-explanation")).not.toBeInTheDocument();
    expect(screen.queryByTestId("admin-audit-log-table")).not.toBeInTheDocument();
  });

  test("clicking a toggle opens confirmation dialog and confirming auto-saves and turns toggle green", async () => {
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
    expect(screen.getByTestId("auto-save-confirmation")).toHaveTextContent(/Auto-saved/i);
    expect(screen.getByTestId("toggle-session-watch")).toHaveAttribute("aria-checked", "true");
    expect(screen.getByTestId("toggle-session-watch")).toHaveStyle({ backgroundColor: "#137333" });
  });

  test("renders Cloud Logging helper box pointing to Google Cloud Logging (Logs Explorer)", async () => {
    render(<AdminConfig />);

    await waitFor(() => {
      expect(screen.getByTestId("cloud-logging-helper")).toBeInTheDocument();
    });

    const cloudHelper = screen.getByTestId("cloud-logging-helper");
    expect(cloudHelper).toHaveTextContent(/Google Cloud Logging/i);
    expect(cloudHelper).toHaveTextContent(/AUDIT_WOULD_SIGN_OUT/i);
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
      screen.getByText("Políticas Generales de Seguridad")
    ).toBeInTheDocument();
    expect(screen.getByTestId("cloud-logging-helper")).toHaveTextContent(
      /Google Cloud Logging/i
    );
    expect(screen.getByTestId("auto-save-confirmation")).toHaveTextContent(
      /Guardado automático/i
    );
    expect(localStorage.getItem("userLocale")).toBe("es");
  });

  test("allows enabling Stolen Cookie & Token Threat Detection while keeping Session Management OFF", async () => {
    render(<AdminConfig />);

    await waitFor(() => {
      expect(screen.getByTestId("toggle-cookie-threat-detection")).toBeInTheDocument();
    });

    const sessionToggle = screen.getByTestId("toggle-session-watch");
    const cookieToggle = screen.getByTestId("toggle-cookie-threat-detection");

    expect(sessionToggle).toHaveAttribute("aria-checked", "false");
    expect(cookieToggle).toHaveAttribute("aria-checked", "false");

    // Toggle Stolen Cookie & Token Threat Detection ON while Session Management stays OFF
    fireEvent.click(cookieToggle);

    expect(screen.getByTestId("confirm-toggle-modal")).toBeInTheDocument();
    expect(
      screen.getByText(/Enable Stolen Cookie & Token Threat Detection\?/i)
    ).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("confirm-autosave-btn"));

    await waitFor(() => {
      expect(mockUpdateAdminConfig).toHaveBeenCalledWith(
        expect.objectContaining({
          session_watch_enabled: false,
          cookie_threat_detection_enabled: true,
          enforcement_mode: "COOKIE_SENTINEL",
        })
      );
    });

    expect(screen.getByTestId("toggle-session-watch")).toHaveAttribute("aria-checked", "false");
    expect(screen.getByTestId("toggle-cookie-threat-detection")).toHaveAttribute("aria-checked", "true");
    expect(screen.getByTestId("toggle-cookie-threat-detection")).toHaveStyle({ backgroundColor: "#137333" });
    expect(screen.getByTestId("active-enforcement-mode-pill")).toHaveTextContent(/COOKIE_SENTINEL/i);
  });

  test("clarifies that Context-Aware Access (CAA) is ON by default and renders independent OU Tree & Google Group checkbox selectors", async () => {
    render(<AdminConfig />);

    await waitFor(() => {
      expect(screen.getByTestId("caa-default-active-banner")).toBeInTheDocument();
    });

    const caaBanner = screen.getByTestId("caa-default-active-banner");
    expect(caaBanner).toHaveTextContent(/Context-Aware Access \(CAA\) Integration \(Education Standard & Plus\) — ON by Default/i);
    expect(caaBanner).toHaveTextContent(/ALWAYS ON BY DEFAULT/i);
    expect(caaBanner).toHaveTextContent(/device\.is_admin_approved_device/i);

    // Check /Students in Session Management OU Tree
    const sessionStudentsCheckbox = screen.getByTestId("ou-tree-session-watch-checkbox-/Students");
    fireEvent.click(sessionStudentsCheckbox);

    await waitFor(() => {
      expect(mockUpdateAdminConfig).toHaveBeenCalledWith(
        expect.objectContaining({
          session_watch_target_ous: ["/Students"],
          cookie_threat_target_ous: [],
        })
      );
    });

    // Check /Staff in Cookie & Token Threat Detection OU Tree and cookie-sentinel-pilot@school.edu in Group selector
    const cookieStaffCheckbox = screen.getByTestId("ou-tree-cookie-threat-checkbox-/Staff");
    fireEvent.click(cookieStaffCheckbox);

    await waitFor(() => {
      expect(mockUpdateAdminConfig).toHaveBeenCalledWith(
        expect.objectContaining({
          session_watch_target_ous: ["/Students"],
          cookie_threat_target_ous: ["/Staff"],
        })
      );
    });

    const cookieGroupCheckbox = screen.getByTestId(
      "group-selector-cookie-threat-checkbox-cookie-sentinel-pilot@school.edu"
    );
    fireEvent.click(cookieGroupCheckbox);

    await waitFor(() => {
      expect(mockUpdateAdminConfig).toHaveBeenCalledWith(
        expect.objectContaining({
          session_watch_target_ous: ["/Students"],
          cookie_threat_target_ous: ["/Staff"],
          cookie_threat_target_groups: ["cookie-sentinel-pilot@school.edu"],
        })
      );
    });
  });
});

