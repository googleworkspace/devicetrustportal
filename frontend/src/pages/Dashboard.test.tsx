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
import { Dashboard } from "./Dashboard";
import { getMyDevices, checkIsAdmin, getPublicConfig, startOnboardingLease } from "../services/api";

// Mock the API service
vi.mock("../services/api", () => ({
  getMyDevices: vi.fn(),
  checkIsAdmin: vi.fn(),
  approveDevice: vi.fn(),
  revokeDevice: vi.fn(),
  revokeDeviceBulk: vi.fn(),
  getPublicConfig: vi.fn(),
  sendClientLog: vi.fn(),
  getSessionWatchMetrics: vi.fn(),
  syncSessionWatchInventory: vi.fn(),
  attestBrowserSession: vi.fn(),
  startOnboardingLease: vi.fn(),
  verifySessionStatus: vi.fn(),
  runLiveLoginSweep: vi.fn(),
}));

// Mock GoogleLoginButton to simplify authentication testing
vi.mock("../components/GoogleLoginButton", () => ({
  GoogleLoginButton: ({ onLoginSuccess }: { onLoginSuccess: (email: string, token: string) => void }) => (
    <button
      onClick={() => {
        global.localStorage.setItem("userEmail", "user@example.com");
        global.localStorage.setItem("googleIdToken", "mock-token");
        onLoginSuccess("user@example.com", "mock-token");
      }}
    >
      Mock Login Button
    </button>
  ),
}));

const mockGetMyDevices = getMyDevices as ReturnType<typeof vi.fn>;
const mockCheckIsAdmin = checkIsAdmin as ReturnType<typeof vi.fn>;
const mockGetPublicConfig = getPublicConfig as ReturnType<typeof vi.fn>;

describe("Dashboard Page", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    mockGetPublicConfig.mockResolvedValue({ default_locale: "en" });
  });

  test("renders logged out state by default", () => {
    render(<Dashboard />);
    expect(screen.getByText("Device Trust Gateway Portal")).toBeInTheDocument();
    expect(screen.getByText("Google Workspace Authentication")).toBeInTheDocument();
    expect(screen.getAllByText("Please sign in with your Google Workspace corporate account to manage device access:").length).toBeGreaterThan(0);
    expect(screen.queryByText("Active Session")).not.toBeInTheDocument();
  });

  test("allows logging in", async () => {
    mockCheckIsAdmin.mockResolvedValue(false);
    mockGetMyDevices.mockResolvedValue([]);

    render(<Dashboard />);

    const loginButton = screen.getByText("Mock Login Button");
    fireEvent.click(loginButton);

    await waitFor(() => {
      expect(screen.getByText("Active Session")).toBeInTheDocument();
    });

    expect(screen.getAllByText("user@example.com").length).toBeGreaterThan(0);
    expect(localStorage.getItem("userEmail")).toBe("user@example.com");
    expect(localStorage.getItem("googleIdToken")).toBe("mock-token");
  });

  test("renders logged in state with personal BYOD devices", async () => {
    localStorage.setItem("userEmail", "user@example.com");
    localStorage.setItem("googleIdToken", "mock-token");
    
    mockCheckIsAdmin.mockResolvedValue(false);
    mockGetMyDevices.mockResolvedValue([
      {
        device_user_name: "devices/1/deviceUsers/1",
        device_type: "DESKTOP",
        model: "MacBook Pro",
        os_version: "macOS 14.0",
        serial_number: "C02XX123XX",
        approval_state: "APPROVED",
        owner_type: "BYOD",
        last_sync_time: "2026-06-15T12:00:00Z",
      },
    ]);

    render(<Dashboard />);

    expect(screen.getByText("Device Trust Gateway Portal")).toBeInTheDocument();
    expect(screen.getByText("Active Session")).toBeInTheDocument();
    expect(screen.getAllByText("user@example.com").length).toBeGreaterThan(0);
    
    // Wait for devices to load
    await waitFor(() => {
      expect(screen.getByText("MacBook Pro")).toBeInTheDocument();
    });

    expect(screen.getByText("Personal BYOD Devices")).toBeInTheDocument();
    expect(screen.getByText("macOS 14.0 (DESKTOP)")).toBeInTheDocument();
    expect(screen.getByText("Serial/IMEI: C02XX123XX")).toBeInTheDocument();
    expect(screen.getByText("APPROVED")).toBeInTheDocument();
    expect(screen.getByText("✕ Revoke")).toBeInTheDocument();
    
    // Admin config should NOT be visible
    expect(screen.queryByText(/Admin Configurations/)).not.toBeInTheDocument();
  });

  test("renders separated company-owned devices table without checkboxes or action buttons", async () => {
    localStorage.setItem("userEmail", "user@example.com");
    localStorage.setItem("googleIdToken", "mock-token");

    mockCheckIsAdmin.mockResolvedValue(false);
    mockGetMyDevices.mockResolvedValue([
      {
        device_user_name: "devices/1/deviceUsers/1",
        device_type: "DESKTOP",
        model: "MacBook Pro BYOD",
        os_version: "macOS 14.0",
        serial_number: "C02XX123XX",
        approval_state: "APPROVED",
        owner_type: "BYOD",
        last_sync_time: "2026-06-15T12:00:00Z",
      },
      {
        device_user_name: "devices/2/deviceUsers/2",
        device_type: "CHROME_OS",
        model: "Lenovo 300e Chromebook",
        os_version: "ChromeOS 120",
        serial_number: "LR00ABCD",
        approval_state: "APPROVED",
        owner_type: "COMPANY",
        last_sync_time: "2026-06-16T08:30:00Z",
      },
    ]);

    render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByText("Personal BYOD Devices")).toBeInTheDocument();
      expect(screen.getAllByText("Company-Owned Devices").length).toBeGreaterThan(0);
    });

    // Ensure admin-only Session Watch operation buttons are NOT on the Dashboard
    expect(screen.queryByText(/Sync Inventory Cache/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Run Live Login Sweep/i)).not.toBeInTheDocument();

    // Check personal BYOD device has checkbox & revoke button
    expect(screen.getByText("MacBook Pro BYOD")).toBeInTheDocument();
    expect(screen.getByLabelText("Select device MacBook Pro BYOD")).toBeInTheDocument();
    expect(screen.getByText("✕ Revoke")).toBeInTheDocument();

    // Check company-owned device renders in separate table with badge, NO checkbox, NO revoke button
    expect(screen.getByText("Lenovo 300e Chromebook")).toBeInTheDocument();
    expect(screen.queryByLabelText("Select device Lenovo 300e Chromebook")).not.toBeInTheDocument();
    expect(screen.getAllByText("🏢 Company Owned Device").length).toBeGreaterThan(0);
    expect(screen.queryByText("Immutable Anchor")).not.toBeInTheDocument();
  });

  test("renders admin configurations link for admin user while keeping identical device approval view", async () => {
    localStorage.setItem("userEmail", "admin@example.com");
    localStorage.setItem("googleIdToken", "mock-token");
    
    mockCheckIsAdmin.mockResolvedValue(true);
    mockGetMyDevices.mockResolvedValue([]);

    render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByText("Admin Configurations")).toBeInTheDocument();
    });
    // Admin sees the same device approval view without admin-only telemetry buttons on Dashboard
    expect(screen.queryByText(/Sync Inventory Cache/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Run Live Login Sweep/i)).not.toBeInTheDocument();
  });

  test("clicking refresh devices button triggers getMyDevices", async () => {
    localStorage.setItem("userEmail", "user@example.com");
    localStorage.setItem("googleIdToken", "mock-token");

    mockCheckIsAdmin.mockResolvedValue(false);
    mockGetMyDevices.mockResolvedValue([
      {
        device_user_name: "devices/1/deviceUsers/1",
        device_type: "DESKTOP",
        model: "MacBook Pro",
        os_version: "macOS 14.0",
        serial_number: "C02XX123XX",
        approval_state: "APPROVED",
        owner_type: "BYOD",
        last_sync_time: "2026-06-15T12:00:00Z",
      },
    ]);

    render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByText("MacBook Pro")).toBeInTheDocument();
    });

    expect(mockGetMyDevices).toHaveBeenCalledTimes(1);

    const refreshButtons = screen.getAllByRole("button", { name: /Refresh Devices/i });
    expect(refreshButtons.length).toBeGreaterThan(0);

    fireEvent.click(refreshButtons[0]);

    await waitFor(() => {
      expect(mockGetMyDevices).toHaveBeenCalledTimes(2);
    });
  });

  test("clicking Add Personal Device (15m Grace Pass) starts onboarding lease when session_watch_enabled is true", async () => {
    localStorage.setItem("userEmail", "user@example.com");
    localStorage.setItem("googleIdToken", "mock-token");

    mockGetPublicConfig.mockResolvedValue({
      default_locale: "en",
      enforcement_mode: "SESSION_WATCH",
      session_watch_enabled: true,
      caa_enforcement_enabled: false,
    });
    mockCheckIsAdmin.mockResolvedValue(false);
    mockGetMyDevices.mockResolvedValue([
      {
        device_user_name: "devices/2/deviceUsers/2",
        device_type: "CHROME_OS",
        model: "Lenovo 300e Chromebook",
        os_version: "ChromeOS 120",
        serial_number: "LR00ABCD",
        approval_state: "APPROVED",
        owner_type: "COMPANY",
        last_sync_time: "2026-06-16T08:30:00Z",
      },
    ]);
    const mockStartOnboardingLease = startOnboardingLease as ReturnType<typeof vi.fn>;
    mockStartOnboardingLease.mockResolvedValue({
      status: "ONBOARDING_GRACE_ACTIVE",
      user_email: "user@example.com",
      expires_at_iso: "2026-06-16T08:45:00Z",
      minutes: 15,
      message: "15-minute personal device onboarding pass activated for user@example.com.",
    });

    render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByText("+ Add Personal Device (15m Grace Pass)")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("+ Add Personal Device (15m Grace Pass)"));

    await waitFor(() => {
      expect(mockStartOnboardingLease).toHaveBeenCalledTimes(1);
      expect(
        screen.getByText("15-minute personal device onboarding pass activated for user@example.com.")
      ).toBeInTheDocument();
    });
  });

  test("renders enforcement standby badge for admin on new install (both toggles disabled) and active badge when enabled", async () => {
    localStorage.setItem("userEmail", "admin@example.com");
    localStorage.setItem("googleIdToken", "mock-token");

    mockGetPublicConfig.mockResolvedValue({
      default_locale: "en",
      enforcement_mode: "DISABLED",
      session_watch_enabled: false,
      caa_enforcement_enabled: false,
    });
    mockCheckIsAdmin.mockResolvedValue(true);
    mockGetMyDevices.mockResolvedValue([]);

    const { unmount } = render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByTestId("enforcement-standby-badge")).toBeInTheDocument();
      expect(screen.getByText(/ENFORCEMENT STANDBY — CONFIGURE IN ADMIN/i)).toBeInTheDocument();
    });

    unmount();

    mockGetPublicConfig.mockResolvedValue({
      default_locale: "en",
      enforcement_mode: "SESSION_WATCH",
      session_watch_enabled: true,
      caa_enforcement_enabled: false,
    });

    render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByTestId("enforcement-mode-badge")).toBeInTheDocument();
      expect(screen.getByText(/SESSION MANAGEMENT ACTIVE/i)).toBeInTheDocument();
    });
  });
});

