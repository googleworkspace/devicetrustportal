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
    <div className="dtg-shell">
      <header className="dtg-header">
        <div className="dtg-header-inner">
          <div className="dtg-brand">
            <a href="#/" className="dtg-btn dtg-btn-neutral" style={{ padding: "8px" }} aria-label="Back to Dashboard">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z" />
              </svg>
            </a>
            <div>
              <h1 className="dtg-brand-title">Campus Wi-Fi Approval Portal</h1>
              <div className="dtg-brand-subtitle">
                Approve your personal device automatically while connected to trusted campus networks
              </div>
            </div>
          </div>
          <div className="dtg-header-actions">
            <a href="#/" className="dtg-btn dtg-btn-outline">
              &larr; Back to Dashboard
            </a>
          </div>
        </div>
      </header>

      <main className="dtg-main dtg-main-narrow">
        {message && (
          <div role="status" className="dtg-alert dtg-alert-success">
            <span>{message}</span>
          </div>
        )}
        {error && (
          <div role="alert" className="dtg-alert dtg-alert-error">
            <span>{error}</span>
          </div>
        )}

        <div className="dtg-card">
          <h2 className="dtg-card-title">Self-Service Network Approval</h2>
          <p className="dtg-card-desc" style={{ marginBottom: "20px" }}>
            Our Gateway backend automatically verifies your IP address against configured campus subnets before granting
            access.
          </p>

          <div
            style={{
              marginBottom: "22px",
              borderTop: "1px solid var(--dtg-border-subtle)",
              paddingTop: "18px",
            }}
          >
            <label
              style={{
                display: "block",
                fontWeight: 600,
                marginBottom: "10px",
                color: "var(--dtg-text)",
                fontSize: "13px",
              }}
            >
              Device Identification Strategy:
            </label>
            <div style={{ display: "flex", gap: "16px", marginBottom: "14px", flexWrap: "wrap" }}>
              <label style={{ fontSize: "13px", cursor: "pointer", display: "inline-flex", alignItems: "center", gap: "6px" }}>
                <input
                  type="radio"
                  name="netMode"
                  checked={mode === "optionA"}
                  onChange={() => setMode("optionA")}
                />
                Option A: API Lookup
              </label>
              <label style={{ fontSize: "13px", cursor: "pointer", display: "inline-flex", alignItems: "center", gap: "6px" }}>
                <input
                  type="radio"
                  name="netMode"
                  checked={mode === "optionB"}
                  onChange={() => setMode("optionB")}
                />
                Option B: Endpoint Verif.
              </label>
            </div>

            {mode === "optionA" ? (
              <div>
                <label
                  style={{
                    fontSize: "12px",
                    color: "var(--dtg-text-secondary)",
                    display: "block",
                    marginBottom: "6px",
                  }}
                >
                  Enter Hardware Serial Number / IMEI:
                </label>
                <input
                  type="text"
                  placeholder="e.g., PF2ABC99"
                  value={rawDeviceId}
                  onChange={(e) => setRawDeviceId(e.target.value)}
                  className="dtg-input"
                />
              </div>
            ) : (
              <div
                style={{
                  backgroundColor: "var(--dtg-primary-soft)",
                  padding: "12px",
                  borderRadius: "6px",
                  border: "1px solid var(--dtg-primary-border)",
                }}
              >
                <p style={{ fontSize: "12px", color: "var(--dtg-primary)", margin: 0, lineHeight: 1.45 }}>
                  <b>Endpoint Verification Integration:</b> Your device certificate and resource ID are automatically
                  captured and supplied by the Google Workspace browser extension during submission.
                </p>
              </div>
            )}
          </div>

          <button
            onClick={handleApprove}
            disabled={loading}
            className="dtg-btn dtg-btn-success"
            style={{ width: "100%", padding: "12px 24px", fontSize: "15px" }}
          >
            {loading ? "Verifying Network Trust..." : "Approve This Device"}
          </button>
        </div>
      </main>
    </div>
  );
};
