// API client for communicating with Device Trust Gateway backend

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || "http://localhost:8080";

export interface TenantConfig {
  customer_id: string;
  inactivity_threshold_days: number;
  trusted_ip_ranges: string[];
  chaining_allowed_groups: string[];
  chaining_allowed_ous: string[];
}

export interface GenerateResponse {
  pairing_code: string;
  expires_in_seconds: number;
}

export interface VerifyResponse {
  status: string;
  operation?: any;
}

// Helper to get headers (including user email for auth/simulation)
const getHeaders = () => {
  const userEmail = localStorage.getItem("userEmail") || "user@example.com";
  return {
    "Content-Type": "application/json",
    "X-User-Email": userEmail,
  };
};

export const getAdminConfig = async (): Promise<TenantConfig> => {
  const response = await fetch(`${API_BASE_URL}/api/admin/config`, {
    headers: getHeaders(),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
};

export const updateAdminConfig = async (config: TenantConfig): Promise<{ status: string }> => {
  const response = await fetch(`${API_BASE_URL}/api/admin/config`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(config),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
};

export const generatePairingCode = async (): Promise<GenerateResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/chaining/generate`, {
    method: "POST",
    headers: getHeaders(),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
};

export const verifyPairingCode = async (
  pairingCode: string,
  rawDeviceId?: string,
  evHeader?: string
): Promise<VerifyResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/chaining/verify`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({
      pairing_code: pairingCode,
      raw_device_id: rawDeviceId,
      ev_header: evHeader,
    }),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
};

export const networkApproval = async (
  rawDeviceId?: string,
  evHeader?: string
): Promise<VerifyResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/network/approve`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({
      raw_device_id: rawDeviceId,
      ev_header: evHeader,
    }),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
};

export const triggerCronCleanup = async (): Promise<{ status: string; revoked_count: number }> => {
  const response = await fetch(`${API_BASE_URL}/api/cron/cleanup`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Mock-Cron": "true",
    },
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
};
