import React, { useState } from "react";
import { networkApproval } from "../services/api";

export const NetworkApproval: React.FC = () => {
  const [rawDeviceId, setRawDeviceId] = useState("pixel-phone99");
  const [evHeader, setEvHeader] = useState("devices/pixel-phone99/deviceUsers/du-2");
  const [mode, setMode] = useState<"optionA" | "optionB">("optionA");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleApprove = async () => {
    setMessage("");
    setError("");
    setLoading(true);
    try {
      const res = await networkApproval(
        mode === "optionA" ? rawDeviceId : undefined,
        mode === "optionB" ? evHeader : undefined
      );
      setMessage(`Success! Device approved via campus Wi-Fi trust. Operation: ${res.operation?.name || "op-1"}`);
      setLoading(false);
    } catch (err: any) {
      setError(`Approval failed: ${err.message}`);
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: "20px", fontFamily: "sans-serif", maxWidth: "800px", margin: "0 auto" }}>
      <a href="#/" style={{ color: "#1a73e8", textDecoration: "none", fontWeight: "bold" }}>&larr; Back to Dashboard</a>
      <h1 style={{ marginTop: "20px" }}>Campus Wi-Fi Approval Portal</h1>
      <p style={{ color: "#555" }}>
        If you are currently connected to the campus secure Wi-Fi network (or trusted LAN), you can approve your personal device with one click.
      </p>

      {message && <div style={{ padding: "12px", backgroundColor: "#d4edda", color: "#155724", borderRadius: "4px", marginBottom: "20px" }}>{message}</div>}
      {error && <div style={{ padding: "12px", backgroundColor: "#f8d7da", color: "#721c24", borderRadius: "4px", marginBottom: "20px" }}>{error}</div>}

      <div style={{ border: "1px solid #ddd", padding: "25px", borderRadius: "8px", backgroundColor: "#fdfdfd", marginTop: "25px" }}>
        <h2>Self-Service Approval</h2>
        <p style={{ fontSize: "14px", color: "#666" }}>
          Our Gateway backend automatically verifies your IP address against configured campus subnets before granting access.
        </p>

        <div style={{ marginBottom: "20px", borderTop: "1px solid #eee", paddingTop: "15px" }}>
          <label style={{ display: "block", fontWeight: "bold", marginBottom: "8px" }}>Device Identification Strategy:</label>
          <div style={{ display: "flex", gap: "15px", marginBottom: "10px" }}>
            <label style={{ fontSize: "14px" }}>
              <input type="radio" name="netMode" checked={mode === "optionA"} onChange={() => setMode("optionA")} /> Option A: API Lookup
            </label>
            <label style={{ fontSize: "14px" }}>
              <input type="radio" name="netMode" checked={mode === "optionB"} onChange={() => setMode("optionB")} /> Option B: Endpoint Verif.
            </label>
          </div>

          {mode === "optionA" ? (
            <div>
              <label style={{ fontSize: "12px", color: "#555", display: "block", marginBottom: "4px" }}>Device ID / Serial Number:</label>
              <input
                type="text"
                value={rawDeviceId}
                onChange={(e) => setRawDeviceId(e.target.value)}
                style={{ padding: "8px", width: "100%", boxSizing: "border-box", fontSize: "14px" }}
              />
            </div>
          ) : (
            <div>
              <label style={{ fontSize: "12px", color: "#555", display: "block", marginBottom: "4px" }}>Simulated EV / CAA Header:</label>
              <input
                type="text"
                value={evHeader}
                onChange={(e) => setEvHeader(e.target.value)}
                style={{ padding: "8px", width: "100%", boxSizing: "border-box", fontSize: "14px" }}
              />
            </div>
          )}
        </div>

        <button
          onClick={handleApprove}
          disabled={loading}
          style={{ padding: "14px 25px", backgroundColor: "#34a853", color: "white", border: "none", borderRadius: "5px", fontWeight: "bold", cursor: "pointer", fontSize: "16px", width: "100%" }}
        >
          {loading ? "Verifying Network Trust..." : "Approve This Device"}
        </button>
      </div>
    </div>
  );
};
