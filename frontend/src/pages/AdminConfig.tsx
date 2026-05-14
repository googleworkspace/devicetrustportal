import React, { useState, useEffect } from "react";
import { getAdminConfig, updateAdminConfig, TenantConfig } from "../services/api";

export const AdminConfig: React.FC = () => {
  const [config, setConfig] = useState<TenantConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const [threshold, setThreshold] = useState(90);

  const userEmail = localStorage.getItem("userEmail") || "";

  useEffect(() => {
    if (!userEmail) {
      setLoading(false);
      setError("Authentication required. Please sign in with Google on the Dashboard.");
      return;
    }

    const load = async () => {
      try {
        const data = await getAdminConfig();
        setConfig(data);
        setThreshold(data.inactivity_threshold_days);
        setLoading(false);
      } catch (e: any) {
        setError(`Access Denied: ${e.message || "Workspace Administrator privileges required."}`);
        setLoading(false);
      }
    };

    load();
  }, [userEmail]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage("");
    setError("");

    const updatedConfig: TenantConfig = {
      customer_id: "customers/my_customer",
      inactivity_threshold_days: Number(threshold),
      trusted_ip_ranges: config?.trusted_ip_ranges || [],
      chaining_allowed_groups: config?.chaining_allowed_groups || [],
      chaining_allowed_ous: config?.chaining_allowed_ous || [],
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

  if (error && !config) {
    return (
      <div style={{ padding: "20px", fontFamily: "sans-serif", maxWidth: "600px", margin: "0 auto" }}>
        <a href="#/" style={{ color: "#1a73e8", textDecoration: "none", fontWeight: "bold" }}>&larr; Back to Dashboard</a>
        <h1 style={{ color: "#d93025", marginTop: "20px" }}>Access Denied</h1>
        <p style={{ color: "#555" }}>
          {error}
        </p>
        <p style={{ fontSize: "14px", color: "#777" }}>
          Active Session: <b>{userEmail || "None"}</b>. Only authorized Google Workspace Super Administrators may manage tenant configurations.
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
        <div style={{ marginBottom: "25px" }}>
          <label style={{ display: "block", fontWeight: "bold", marginBottom: "6px" }}>Inactivity Threshold (Days):</label>
          <input
            type="number"
            value={threshold}
            onChange={(e) => setThreshold(Number(e.target.value))}
            style={{ padding: "10px", width: "100%", boxSizing: "border-box", fontSize: "16px" }}
          />
          <span style={{ fontSize: "12px", color: "#777" }}>Automated cron revocation triggers for BYOD devices idle longer than this window.</span>
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
