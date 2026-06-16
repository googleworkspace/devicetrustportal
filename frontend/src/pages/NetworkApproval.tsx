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

import React, { useState } from "react";
import { networkApproval } from "../services/api";

export const NetworkApproval: React.FC = () => {
  const [rawDeviceId, setRawDeviceId] = useState("");
  const [mode, setMode] = useState<"optionA" | "optionB">("optionA");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleApprove = async () => {
    setMessage("");
    setError("");
    setLoading(true);
    try {
      const evHeader = mode === "optionB" ? "devices/ev-client-cert/deviceUsers/active-user" : undefined;
      const res = await networkApproval(
        mode === "optionA" ? rawDeviceId : undefined,
        evHeader
      );
      setMessage(`Success! Device approved via campus Wi-Fi trust. Operation: ${res.operation?.name || "completed"}`);
      setLoading(false);
    } catch (err: any) {
      setError(`Approval failed: ${err.message || "Network authorization error."}`);
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

        <div style={{ marginBottom: "25px", borderTop: "1px solid #eee", paddingTop: "20px" }}>
          <label style={{ display: "block", fontWeight: "bold", marginBottom: "10px", color: "#202124" }}>Device Identification Strategy:</label>
          <div style={{ display: "flex", gap: "20px", marginBottom: "15px" }}>
            <label style={{ fontSize: "14px", cursor: "pointer" }}>
              <input type="radio" name="netMode" checked={mode === "optionA"} onChange={() => setMode("optionA")} /> Option A: API Lookup
            </label>
            <label style={{ fontSize: "14px", cursor: "pointer" }}>
              <input type="radio" name="netMode" checked={mode === "optionB"} onChange={() => setMode("optionB")} /> Option B: Endpoint Verif.
            </label>
          </div>

          {mode === "optionA" ? (
            <div>
              <label style={{ fontSize: "12px", color: "#5f6368", display: "block", marginBottom: "6px" }}>Enter Hardware Serial Number / IMEI:</label>
              <input
                type="text"
                placeholder="e.g., PF2ABC99"
                value={rawDeviceId}
                onChange={(e) => setRawDeviceId(e.target.value)}
                style={{ padding: "10px", width: "100%", boxSizing: "border-box", fontSize: "14px", borderRadius: "4px", border: "1px solid #ccc" }}
              />
            </div>
          ) : (
            <div style={{ backgroundColor: "#e8f0fe", padding: "12px", borderRadius: "4px", border: "1px solid #d2e3fc" }}>
              <p style={{ fontSize: "12px", color: "#1a73e8", margin: 0, lineHeight: "1.4" }}>
                <b>Endpoint Verification Integration:</b> Your device certificate and resource ID are automatically captured and supplied by the Google Workspace browser extension during submission.
              </p>
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
