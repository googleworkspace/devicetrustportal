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
import { generatePairingCode, verifyPairingCode } from "../services/api";

export const ChainingApproval: React.FC = () => {
  const [pairingCode, setPairingCode] = useState("");
  const [generatedCode, setGeneratedCode] = useState("");
  const [expiresIn, setExpiresIn] = useState(0);

  const [mode, setMode] = useState<"optionA" | "optionB">("optionA");
  const [rawDeviceId, setRawDeviceId] = useState("");

  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const handleGenerate = async () => {
    setMessage("");
    setError("");
    try {
      const res = await generatePairingCode();
      setGeneratedCode(res.pairing_code);
      setExpiresIn(res.expires_in_seconds);
      setMessage("Pairing code generated successfully!");
    } catch (e: any) {
      setError(`Generation failed: ${e.message || "Access denied."}`);
    }
  };

  const handleVerify = async () => {
    setMessage("");
    setError("");
    try {
      const evHeader = mode === "optionB" ? "devices/ev-client-cert/deviceUsers/active-user" : undefined;

      const res = await verifyPairingCode(
        pairingCode,
        mode === "optionA" ? rawDeviceId : undefined,
        evHeader
      );
      setMessage(`Success! Device approved. Operation ID: ${res.operation?.name || "completed"}`);
    } catch (e: any) {
      setError(`Verification failed: ${e.message || "Device identification error."}`);
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
              <h1 className="dtg-brand-title">Trust Chaining Portal</h1>
              <div className="dtg-brand-subtitle">
                Approve a new personal device by chaining trust from an already-approved device
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

        <div className="dtg-two-col-grid">
          {/* View 1: Approved Device (Generate Code) */}
          <div className="dtg-card" style={{ marginBottom: 0 }}>
            <h2 className="dtg-card-title">Step 1: Generate Code</h2>
            <p className="dtg-card-desc" style={{ marginBottom: "20px" }}>
              Open this view on your approved Chromebook or laptop to generate a 10-minute pairing code.
            </p>
            <button
              onClick={handleGenerate}
              className="dtg-btn dtg-btn-primary"
              style={{ width: "100%", padding: "12px 20px", fontSize: "15px" }}
            >
              Generate Pairing Code
            </button>

            {generatedCode && (
              <div
                style={{
                  marginTop: "22px",
                  textAlign: "center",
                  padding: "18px",
                  backgroundColor: "var(--dtg-surface-subtle)",
                  borderRadius: "8px",
                  border: "1px solid var(--dtg-border)",
                }}
              >
                <div
                  style={{
                    fontSize: "30px",
                    fontWeight: 700,
                    letterSpacing: "6px",
                    color: "var(--dtg-text)",
                    fontFamily: "monospace",
                  }}
                >
                  {generatedCode}
                </div>
                <div style={{ fontSize: "12px", color: "var(--dtg-text-secondary)", marginTop: "6px" }}>
                  Expires in {expiresIn} seconds
                </div>
              </div>
            )}
          </div>

          {/* View 2: New Personal Device (Enter Code) */}
          <div className="dtg-card" style={{ marginBottom: 0 }}>
            <h2 className="dtg-card-title">Step 2: Enter Code</h2>
            <p className="dtg-card-desc" style={{ marginBottom: "20px" }}>
              Open this view on your unapproved personal phone or laptop and submit the pairing code.
            </p>

            <div style={{ marginBottom: "18px" }}>
              <label
                style={{
                  display: "block",
                  fontWeight: 600,
                  marginBottom: "6px",
                  color: "var(--dtg-text)",
                  fontSize: "13px",
                }}
              >
                Pairing Code:
              </label>
              <input
                type="text"
                placeholder="123456"
                value={pairingCode}
                onChange={(e) => setPairingCode(e.target.value)}
                className="dtg-input"
                style={{ fontSize: "18px", textAlign: "center", letterSpacing: "4px", fontFamily: "monospace" }}
              />
            </div>

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
                    name="idMode"
                    checked={mode === "optionA"}
                    onChange={() => setMode("optionA")}
                  />
                  Option A: API Lookup
                </label>
                <label style={{ fontSize: "13px", cursor: "pointer", display: "inline-flex", alignItems: "center", gap: "6px" }}>
                  <input
                    type="radio"
                    name="idMode"
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
              onClick={handleVerify}
              className="dtg-btn dtg-btn-success"
              style={{ width: "100%", padding: "12px 20px", fontSize: "15px" }}
            >
              Approve This Device
            </button>
          </div>
        </div>
      </main>
    </div>
  );
};
