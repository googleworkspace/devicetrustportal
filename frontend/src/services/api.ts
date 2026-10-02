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

// API client for communicating with Device Trust Gateway backend

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || "";

export interface TenantConfig {
  customer_id: string;
  inactivity_threshold_days: number;
  portal_admins: string[];
  revocation_action?: string;
  google_client_id?: string;
  default_locale?: string;
  trusted_ip_ranges?: string[];
  chaining_allowed_groups?: string[];
  chaining_allowed_ous?: string[];
}

export interface GenerateResponse {
  pairing_code: string;
  expires_in_seconds: number;
}

export interface VerifyResponse {
  status: string;
  operation?: any;
}

export interface DeviceUserItem {
  device_user_name: string;
  device_type: string;
  model: string;
  os_version: string;
  serial_number: string;
  approval_state: string;
  owner_type: string;
  last_sync_time: string;
}

export const sendClientLog = (
  level: "INFO" | "WARNING" | "ERROR",
  event: string,
  message: string,
  details?: Record<string, any>
): void => {
  try {
    const userEmail = localStorage.getItem("userEmail") || undefined;
    const route = window.location.hash || window.location.pathname || "/";
    const userAgent = typeof navigator !== "undefined" ? navigator.userAgent : undefined;
    fetch(`${API_BASE_URL}/api/client-logs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      keepalive: true,
      body: JSON.stringify({
        level,
        event,
        message,
        user_email: userEmail,
        route,
        user_agent: userAgent,
        details: details || {},
      }),
    }).catch(() => {});
  } catch (_) {
    // Ignore telemetry errors
  }
};

const getHeaders = () => {
  const idToken = localStorage.getItem("googleIdToken");
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (idToken) {
    headers["Authorization"] = `Bearer ${idToken}`;
  }
  return headers;
};

const fetchWithAuth = async (url: string, options: RequestInit = {}): Promise<Response> => {
  let response: Response;
  try {
    response = await fetch(url, options);
  } catch (netErr: any) {
    sendClientLog("ERROR", "API_NETWORK_ERROR", `Network failure calling ${url}`, {
      url,
      method: options.method || "GET",
      error: netErr?.message || String(netErr),
    });
    throw netErr;
  }

  if (response.status === 401) {
    console.warn("Session expired or invalid credentials. Clearing local storage.");
    sendClientLog("WARNING", "API_AUTH_EXPIRED", `401 Unauthorized on ${url}; clearing session`, {
      url,
      method: options.method || "GET",
    });
    localStorage.removeItem("googleIdToken");
    localStorage.removeItem("userEmail");
    window.location.reload();
    throw new Error("Your authentication session has expired. Please sign in again.");
  }
  if (!response.ok) {
    const errText = await response.text();
    sendClientLog("ERROR", "API_HTTP_ERROR", `HTTP ${response.status} on ${url}`, {
      url,
      method: options.method || "GET",
      status: response.status,
      response_body: errText.slice(0, 1000),
    });
    throw new Error(errText);
  }
  return response;
};

export const checkIsAdmin = async (): Promise<boolean> => {
  try {
    const response = await fetchWithAuth(`${API_BASE_URL}/api/admin/status`, {
      headers: getHeaders(),
    });
    const data = await response.json();
    return data.is_admin;
  } catch (e) {
    return false;
  }
};

export const getPublicConfig = async (): Promise<{ google_client_id: string; default_locale?: string }> => {
  const response = await fetch(`${API_BASE_URL}/api/config/public`);
  return response.json();
};

export const getAdminConfig = async (): Promise<TenantConfig> => {
  const response = await fetchWithAuth(`${API_BASE_URL}/api/admin/config`, {
    headers: getHeaders(),
  });
  return response.json();
};

export const updateAdminConfig = async (config: TenantConfig): Promise<{ status: string }> => {
  const response = await fetchWithAuth(`${API_BASE_URL}/api/admin/config`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(config),
  });
  return response.json();
};

export const generatePairingCode = async (): Promise<GenerateResponse> => {
  const response = await fetchWithAuth(`${API_BASE_URL}/api/chaining/generate`, {
    method: "POST",
    headers: getHeaders(),
  });
  return response.json();
};

export const verifyPairingCode = async (
  pairingCode: string,
  rawDeviceId?: string,
  evHeader?: string
): Promise<VerifyResponse> => {
  const response = await fetchWithAuth(`${API_BASE_URL}/api/chaining/verify`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({
      pairing_code: pairingCode,
      raw_device_id: rawDeviceId,
      ev_header: evHeader,
    }),
  });
  return response.json();
};

export const networkApproval = async (
  rawDeviceId?: string,
  evHeader?: string
): Promise<VerifyResponse> => {
  const response = await fetchWithAuth(`${API_BASE_URL}/api/network/approve`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({
      raw_device_id: rawDeviceId,
      ev_header: evHeader,
    }),
  });
  return response.json();
};

export const getMyDevices = async (): Promise<DeviceUserItem[]> => {
  const response = await fetchWithAuth(`${API_BASE_URL}/api/devices/my-devices`, {
    headers: getHeaders(),
  });
  return response.json();
};

export const approveDevice = async (deviceUserName: string): Promise<{ status: string }> => {
  const response = await fetchWithAuth(`${API_BASE_URL}/api/devices/approve`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ device_user_name: deviceUserName }),
  });
  return response.json();
};

export const revokeDevice = async (deviceUserName: string): Promise<{ status: string }> => {
  const response = await fetchWithAuth(`${API_BASE_URL}/api/devices/revoke`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ device_user_name: deviceUserName }),
  });
  return response.json();
};

export const revokeDeviceBulk = async (deviceUserNames: string[]): Promise<{ status: string; revoked_count: number }> => {
  const response = await fetchWithAuth(`${API_BASE_URL}/api/devices/revoke-bulk`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ device_user_names: deviceUserNames }),
  });
  return response.json();
};
