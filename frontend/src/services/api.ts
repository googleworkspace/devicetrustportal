// API client for communicating with Device Trust Gateway backend

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || "";

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

export interface DeviceUserItem {
  device_user_name: string;
  device_type: string;
  approval_state: string;
  last_sync_time: string;
}

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

// Helper fetch wrapper intercepting 401 Unauthorized to handle stale/expired sessions
const fetchWithAuth = async (url: string, options: RequestInit = {}): Promise<Response> => {
  const response = await fetch(url, options);
  if (response.status === 401) {
    console.warn("Session expired or invalid credentials. Clearing local storage.");
    localStorage.removeItem("googleIdToken");
    localStorage.removeItem("userEmail");
    window.location.reload();
    throw new Error("Your authentication session has expired. Please sign in again.");
  }
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response;
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

export const triggerCronCleanup = async (): Promise<{ status: string; revoked_count: number }> => {
  const response = await fetchWithAuth(`${API_BASE_URL}/api/cron/cleanup`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Mock-Cron": "true",
    },
  });
  return response.json();
};

export const getMyDevices = async (): Promise<DeviceUserItem[]> => {
  const response = await fetchWithAuth(`${API_BASE_URL}/api/devices/my-devices`, {
    headers: getHeaders(),
  });
  return response.json();
};
