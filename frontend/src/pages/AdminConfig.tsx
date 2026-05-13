import React, { useState, useEffect } from "react";
import { getAdminConfig, updateAdminConfig, TenantConfig } from "../services/api";

export const AdminConfig: React.FC = () => {
  const [config, setConfig] = useState<TenantConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  // Form fields
  const [customerId, setCustomerId] = useState("");
  const [threshold, setThreshold] = useState(90);
  const [trustedIps, setTrustedIps] = useState("");
  const [chainingGroups, setChainingGroups] = useState("");
  const [chainingOus, setChainingOus] = useState("");

  const userEmail = localStorage.getItem("userEmail") || "admin@example.com";
  const isAdmin = userEmail.toLowerCase().includes("admin");

  useEffect(() => {
    if (!isAdmin) {
      setLoading(false);
      setError("Access denied: Workspace Administrator privileges required.");
      return;
    }

    const load = async () => {
      try {
        const data = await getAdminConfig();
        setConfig(data);
        setCustomerId(data.customer_id);
        setThreshold(data.inactivity_threshold_days);
        setTrustedIps(data.trusted_ip_ranges.join("\n"));
        setChainingGroups(data.chaining_allowed_groups.join("\n"));
        setChainingOus(data.chaining_allowed_ous.join("\n"));
        setLoading(false);
      } catch (e: any) {
        setError(`Failed to load configurations: ${e.message}`);
        setLoading(false);
      }
    };

    load();
  }, [isAdmin]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage("");
    setError("");

    const updatedConfig: TenantConfig = {
      customer_id: customerId,
      inactivity_threshold_days: Number(threshold),
      trusted_ip_ranges: trustedIps.split("\n").map((s) => s.trim()).filter(Boolean),
      chaining_allowed_groups: chainingGroups.split("\n").map((s) => s.trim()).filter(Boolean),
      chaining_allowed_ous: chainingOus.split("\n").map((s) => s.trim()).filter(Boolean),
    };

    try {
      await updateAdminConfig(updatedConfig);
      setMessage("Configuration successfully updated in GCP Secret Manager / local .env!");
    } catch (err: any) {
      setError(`Update failed: ${err.message}`);
    }
  };

  if (loading) {
    return <div style={{ padding: "20px", fontFamily: "sans-serif" }}>Loading admin configurations...</div>;
  }

  if (!isAdmin) {
    return (
      <div style={{ padding: "20px", fontFamily: "sans-serif", maxWidth: "600px", margin: "0 auto" }}>
        <a href="#/" style={{ color: "#1a73e8", textDecoration: "none", fontWeight: "bold" }}>&larr; Back to Dashboard</a>
        <h1 style={{ color: "#d93025", marginTop: "20px" }}>Access Denied</h1>
        <p style={{ color: "#555" }}>
          Your current active role (<b>{userEmail}</b>) does not have Workspace Administrator privileges.
        </p>
        <p style={{ fontSize: "14px", color: "#777" }}>
          To test this view, return to the Dashboard and update your active email to contain "admin" (e.g., admin@example.com).
        </p>
      </div>
    );
  }

  return (
    <div style={{ padding: "20px", fontFamily: "sans-serif", maxWidth: "800px", margin: "0 auto" }}>
      <a href="#/" style={{ color: "#1a73e8", textDecoration: "none", fontWeight: "bold" }}>&larr; Back to Dashboard</a>
      <h1 style={{ marginTop: "20px" }}>Admin Configurations</h1>
      <p style={{ color: "#555" }}>
        Dynamically manage tenant-wide security thresholds and access policies.
      </p>

      {message && <div style={{ padding: "12px", backgroundColor: "#d4edda", color: "#155724", borderRadius: "4px", marginBottom: "20px" }}>{message}</div>}
      {error && <div style={{ padding: "12px", backgroundColor: "#f8d7da", color: "#721c24", borderRadius: "4px", marginBottom: "20px" }}>{error}</div>}

      <form onSubmit={handleSubmit} style={{ border: "1px solid #ddd", padding: "25px", borderRadius: "8px", backgroundColor: "#fdfdfd" }}>
        <div style={{ marginBottom: "20px" }}>
          <label style={{ display: "block", fontWeight: "bold", marginBottom: "6px" }}>Google Workspace Customer ID:</label>
          <input
            type="text"
            value={customerId}
            onChange={(e) => setCustomerId(e.target.value)}
            style={{ padding: "10px", width: "100%", boxSizing: "border-box", fontSize: "16px" }}
          />
          <span style={{ fontSize: "12px", color: "#777" }}>Format: customers/my_customer or customers/C0123456</span>
        </div>

        <div style={{ marginBottom: "20px" }}>
          <label style={{ display: "block", fontWeight: "bold", marginBottom: "6px" }}>Inactivity Threshold (Days):</label>
          <input
            type="number"
            value={threshold}
            onChange={(e) => setThreshold(Number(e.target.value))}
            style={{ padding: "10px", width: "100%", boxSizing: "border-box", fontSize: "16px" }}
          />
          <span style={{ fontSize: "12px", color: "#777" }}>Automated cron revocation triggers for BYOD devices idle longer than this window.</span>
        </div>

        <div style={{ marginBottom: "20px" }}>
          <label style={{ display: "block", fontWeight: "bold", marginBottom: "6px" }}>Campus Trusted IP Ranges (CIDR):</label>
          <textarea
            rows={4}
            value={trustedIps}
            onChange={(e) => setTrustedIps(e.target.value)}
            style={{ padding: "10px", width: "100%", boxSizing: "border-box", fontSize: "14px", fontFamily: "monospace" }}
          />
          <span style={{ fontSize: "12px", color: "#777" }}>One CIDR block per line (e.g., 10.0.0.0/8). Used for network-gated self-service approvals.</span>
        </div>

        <div style={{ marginBottom: "20px" }}>
          <label style={{ display: "block", fontWeight: "bold", marginBottom: "6px" }}>Chaining Allowed Google Groups:</label>
          <textarea
            rows={3}
            value={chainingGroups}
            onChange={(e) => setChainingGroups(e.target.value)}
            style={{ padding: "10px", width: "100%", boxSizing: "border-box", fontSize: "14px", fontFamily: "monospace" }}
          />
          <span style={{ fontSize: "12px", color: "#777" }}>Group membership overrides OU policies for trust chaining authorization.</span>
        </div>

        <div style={{ marginBottom: "20px" }}>
          <label style={{ display: "block", fontWeight: "bold", marginBottom: "6px" }}>Chaining Allowed Organizational Units (OUs):</label>
          <textarea
            rows={3}
            value={chainingOus}
            onChange={(e) => setChainingOus(e.target.value)}
            style={{ padding: "10px", width: "100%", boxSizing: "border-box", fontSize: "14px", fontFamily: "monospace" }}
          />
          <span style={{ fontSize: "12px", color: "#777" }}>Root paths (e.g., /Staff, /Faculty) authorized for trust chaining if not in an override group.</span>
        </div>

        <button
          type="submit"
          style={{ padding: "14px 25px", backgroundColor: "#1a73e8", color: "white", border: "none", borderRadius: "5px", fontWeight: "bold", cursor: "pointer", fontSize: "16px", width: "100%" }}
        >
          Save Configurations
        </button>
      </form>
    </div>
  );
};
