import React, { useState } from "react";
import { generatePairingCode, verifyPairingCode } from "../services/api";

export const ChainingApproval: React.FC = () => {
  const [pairingCode, setPairingCode] = useState("");
  const [generatedCode, setGeneratedCode] = useState("");
  const [expiresIn, setExpiresIn] = useState(0);
  
  // Options A vs B UI states
  const [mode, setMode] = useState<"optionA" | "optionB">("optionA");
  const [rawDeviceId, setRawDeviceId] = useState("pixel-phone99");
  const [evHeader, setEvHeader] = useState("devices/pixel-phone99/deviceUsers/du-2");
  
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
      setError(`Generation failed: ${e.message}`);
    }
  };

  const handleVerify = async () => {
    setMessage("");
    setError("");
    try {
      const res = await verifyPairingCode(
        pairingCode,
        mode === "optionA" ? rawDeviceId : undefined,
        mode === "optionB" ? evHeader : undefined
      );
      setMessage(`Success! Device approved. Operation ID: ${res.operation?.name || "mock-op"}`);
    } catch (e: any) {
      setError(`Verification failed: ${e.message}`);
    }
  };

  return (
    <div style={{ padding: "20px", fontFamily: "sans-serif", maxWidth: "800px", margin: "0 auto" }}>
      <a href="#/" style={{ color: "#1a73e8", textDecoration: "none", fontWeight: "bold" }}>&larr; Back to Dashboard</a>
      <h1 style={{ marginTop: "20px" }}>Trust Chaining Portal</h1>
      <p style={{ color: "#555" }}>
        Approve a new personal device by chaining trust from an already-approved device (like your school Chromebook).
      </p>

      {message && <div style={{ padding: "12px", backgroundColor: "#d4edda", color: "#155724", borderRadius: "4px", marginBottom: "20px" }}>{message}</div>}
      {error && <div style={{ padding: "12px", backgroundColor: "#f8d7da", color: "#721c24", borderRadius: "4px", marginBottom: "20px" }}>{error}</div>}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "30px", marginTop: "30px" }}>
        {/* View 1: Approved Device (Generate Code) */}
        <div style={{ padding: "20px", border: "1px solid #ddd", borderRadius: "8px", backgroundColor: "#fdfdfd" }}>
          <h2>Step 1: Generate Code</h2>
          <p style={{ fontSize: "14px", color: "#666" }}>Open this on your approved Chromebook/laptop to generate a 10-minute pairing code.</p>
          <button
            onClick={handleGenerate}
            style={{ padding: "12px 20px", backgroundColor: "#1a73e8", color: "white", border: "none", borderRadius: "4px", fontWeight: "bold", cursor: "pointer", width: "100%" }}
          >
            Generate Pairing Code
          </button>

          {generatedCode && (
            <div style={{ marginTop: "20px", textAlign: "center", padding: "15px", backgroundColor: "#eee", borderRadius: "6px" }}>
              <div style={{ fontSize: "28px", fontWeight: "bold", letterSpacing: "5px", color: "#333" }}>{generatedCode}</div>
              <div style={{ fontSize: "12px", color: "#777", marginTop: "5px" }}>Expires in {expiresIn} seconds</div>
            </div>
          )}
        </div>

        {/* View 2: New Personal Device (Enter Code) */}
        <div style={{ padding: "20px", border: "1px solid #ddd", borderRadius: "8px", backgroundColor: "#fdfdfd" }}>
          <h2>Step 2: Enter Code</h2>
          <p style={{ fontSize: "14px", color: "#666" }}>Open this on your unapproved phone/tablet and enter the pairing code.</p>
          
          <div style={{ marginBottom: "15px" }}>
            <label style={{ display: "block", fontWeight: "bold", marginBottom: "5px" }}>Pairing Code:</label>
            <input
              type="text"
              placeholder="123456"
              value={pairingCode}
              onChange={(e) => setPairingCode(e.target.value)}
              style={{ padding: "10px", width: "100%", boxSizing: "border-box", fontSize: "18px", textAlign: "center", letterSpacing: "3px" }}
            />
          </div>

          {/* UX Flexibility: Option A vs Option B selection */}
          <div style={{ marginBottom: "20px", borderTop: "1px solid #eee", paddingTop: "15px" }}>
            <label style={{ display: "block", fontWeight: "bold", marginBottom: "8px" }}>Device Identification Strategy:</label>
            <div style={{ display: "flex", gap: "15px", marginBottom: "10px" }}>
              <label style={{ fontSize: "14px" }}>
                <input type="radio" name="idMode" checked={mode === "optionA"} onChange={() => setMode("optionA")} /> Option A: API Lookup
              </label>
              <label style={{ fontSize: "14px" }}>
                <input type="radio" name="idMode" checked={mode === "optionB"} onChange={() => setMode("optionB")} /> Option B: Endpoint Verif.
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
            onClick={handleVerify}
            style={{ padding: "12px 20px", backgroundColor: "#34a853", color: "white", border: "none", borderRadius: "4px", fontWeight: "bold", cursor: "pointer", width: "100%" }}
          >
            Approve This Device
          </button>
        </div>
      </div>
    </div>
  );
};
