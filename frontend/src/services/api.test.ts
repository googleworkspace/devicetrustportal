import { getAdminConfig, generatePairingCode, verifyPairingCode } from "./api";

// Mock global fetch
const unmockedFetch = global.fetch;

beforeEach(() => {
  global.fetch = jest.fn();
});

afterEach(() => {
  global.fetch = unmockedFetch;
});

describe("Frontend API Service", () => {
  test("getAdminConfig fetches configuration successfully", async () => {
    const mockConfig = {
      customer_id: "customers/my_customer",
      inactivity_threshold_days: 90,
      trusted_ip_ranges: ["127.0.0.1/32"],
      chaining_allowed_groups: ["group@example.com"],
      chaining_allowed_ous: ["/Staff"],
    };

    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => mockConfig,
    });

    const data = await getAdminConfig();
    expect(data.customer_id).toBe("customers/my_customer");
    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining("/api/admin/config"), expect.any(Object));
  });

  test("generatePairingCode successfully returns a pairing code", async () => {
    const mockRes = { pairing_code: "123456", expires_in_seconds: 600 };

    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => mockRes,
    });

    const data = await generatePairingCode();
    expect(data.pairing_code).toBe("123456");
  });

  test("verifyPairingCode successfully verifies and approves device", async () => {
    const mockRes = { status: "SUCCESS", operation: { name: "operations/op-1" } };

    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => mockRes,
    });

    const data = await verifyPairingCode("123456", "pixel-phone99");
    expect(data.status).toBe("SUCCESS");
  });
});
