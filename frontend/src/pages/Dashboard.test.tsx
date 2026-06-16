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
import { Dashboard } from "./Dashboard";
import { getMyDevices, checkIsAdmin } from "../services/api";

// Mock the API service
jest.mock("../services/api", () => ({
  getMyDevices: jest.fn(),
  checkIsAdmin: jest.fn(),
  approveDevice: jest.fn(),
  revokeDevice: jest.fn(),
  revokeDeviceBulk: jest.fn(),
}));

// Mock GoogleLoginButton to simplify authentication testing
jest.mock("../components/GoogleLoginButton", () => ({
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

const mockGetMyDevices = getMyDevices as jest.Mock;
const mockCheckIsAdmin = checkIsAdmin as jest.Mock;

describe("Dashboard Page", () => {
  beforeEach(() => {
    localStorage.clear();
    jest.clearAllMocks();
  });

  test("renders logged out state by default", () => {
    render(<Dashboard />);
    expect(screen.getByText("Device Trust Gateway")).toBeInTheDocument();
    expect(screen.getByText("Google Authentication")).toBeInTheDocument();
    expect(screen.getByText("Please sign in with Google above to view your registered enterprise hardware assets.")).toBeInTheDocument();
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

  test("renders logged in state with devices for regular user", async () => {
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

    expect(screen.getByText("Device Trust Gateway")).toBeInTheDocument();
    expect(screen.getByText("Active Session")).toBeInTheDocument();
    expect(screen.getAllByText("user@example.com").length).toBeGreaterThan(0);
    
    // Wait for devices to load
    await waitFor(() => {
      expect(screen.getByText("MacBook Pro")).toBeInTheDocument();
    });

    expect(screen.getByText("macOS 14.0 (DESKTOP)")).toBeInTheDocument();
    expect(screen.getByText("Serial/IMEI: C02XX123XX")).toBeInTheDocument();
    expect(screen.getByText("APPROVED")).toBeInTheDocument();
    
    // Admin config should NOT be visible
    expect(screen.queryByText(/Admin Configurations/)).not.toBeInTheDocument();
  });

  test("renders admin configurations link for admin user", async () => {
    localStorage.setItem("userEmail", "admin@example.com");
    localStorage.setItem("googleIdToken", "mock-token");
    
    mockCheckIsAdmin.mockResolvedValue(true);
    mockGetMyDevices.mockResolvedValue([]);

    render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByText("⚙️ Admin Configurations")).toBeInTheDocument();
    });
  });
});
