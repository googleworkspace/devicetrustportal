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
      // In Option B production mode, the browser extension supplies the X-Endpoint-Verification certificate header
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
    <div style={{ padding: "20px", fontFamily: "sans-serif", maxWidth: "850px", margin: "0 auto" }}>
      <a href="#/" style={{ color: "#1a73e8", textDecoration: "none", fontWeight: "bold" }}>&larr; Back to Dashboard</a>
      <h1 style={{ marginTop: "20px" }}>Trust Chaining Portal</h1>
      <p style={{ color: "#555" }}>
        Approve a new personal device by chaining trust from an already-approved device (like your school Chromebook).
      </p>

      {message && <div style={{ padding: "12px", backgroundColor: "#d4edda", color: "#155724", borderRadius: "4px", marginBottom: "20px" }}>{message}</div>}
      {error && <div style={{ padding: "12px", backgroundColor: "#f8d7da", color: "#721c24", borderRadius: "4px", marginBottom: "20px" }}>{error}</div>}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "30px", marginTop: "30px" }}>
        {/* View 1: Approved Device (Generate Code) */}
        <div style={{ padding: "25px", border: "1px solid #ddd", borderRadius: "8px", backgroundColor: "#fdfdfd" }}>
          <h2>Step 1: Generate Code</h2>
          <p style={{ fontSize: "14px", color: "#666" }}>Open this view on your approved Chromebook/laptop to generate a 10-minute pairing code.</p>
          <button
            onClick={handleGenerate}
            style={{ padding: "14px 20px", backgroundColor: "#1a73e8", color: "white", border: "none", borderRadius: "5px", fontWeight: "bold", cursor: "pointer", width: "100%", fontSize: "16px" }}
          >
            Generate Pairing Code
          </button>

          {generatedCode && (
            <div style={{ marginTop: "25px", textAlign: "center", padding: "20px", backgroundColor: "#f1f3f4", borderRadius: "6px", border: "1px solid #dadce0" }}>
              <div style={{ fontSize: "32px", fontWeight: "bold", letterSpacing: "6px", color: "#202124" }}>{generatedCode}</div>
              <div style={{ fontSize: "12px", color: "#5f6368", marginTop: "6px" }}>Expires in {expiresIn} seconds</div>
            </div>
          )}
        </div>

        {/* View 2: New Personal Device (Enter Code) */}
        <div style={{ padding: "25px", border: "1px solid #ddd", borderRadius: "8px", backgroundColor: "#fdfdfd" }}>
          <h2>Step 2: Enter Code</h2>
          <p style={{ fontSize: "14px", color: "#666" }}>Open this view on your unapproved personal phone or laptop and submit the pairing code.</p>
          
          <div style={{ marginBottom: "20px" }}>
            <label style={{ display: "block", fontWeight: "bold", marginBottom: "8px", color: "#202124" }}>Pairing Code:</label>
            <input
              type="text"
              placeholder="123456"
              value={pairingCode}
              onChange={(e) => setPairingCode(e.target.value)}
              style={{ padding: "12px", width: "100%", boxSizing: "border-box", fontSize: "20px", textAlign: "center", letterSpacing: "4px", borderRadius: "4px", border: "1px solid #ccc" }}
            />
          </div>

          <div style={{ marginBottom: "25px", borderTop: "1px solid #eee", paddingTop: "20px" }}>
            <label style={{ display: "block", fontWeight: "bold", marginBottom: "10px", color: "#202124" }}>Device Identification Strategy:</label>
            <div style={{ display: "flex", gap: "20px", marginBottom: "15px" }}>
              <label style={{ fontSize: "14px", cursor: "pointer" }}>
                <input type="radio" name="idMode" checked={mode === "optionA"} onChange={() => setMode("optionA")} /> Option A: API Lookup
              </label>
              <label style={{ fontSize: "14px", cursor: "pointer" }}>
                <input type="radio" name="idMode" checked={mode === "optionB"} onChange={() => setMode("optionB")} /> Option B: Endpoint Verif.
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
            onClick={handleVerify}
            style={{ padding: "14px 20px", backgroundColor: "#34a853", color: "white", border: "none", borderRadius: "5px", fontWeight: "bold", cursor: "pointer", width: "100%", fontSize: "16px" }}
          >
            Approve This Device
          </button>
        </div>
      </div>
    </div>
  );
};
