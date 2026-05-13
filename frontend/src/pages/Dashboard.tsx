import React, { useState, useEffect } from "react";
import { triggerCronCleanup } from "../services/api";
import { GoogleLoginButton } from "../components/GoogleLoginButton";

export const Dashboard: React.FC = () => {
  const [userEmail, setUserEmail] = useState(() => localStorage.getItem("userEmail") || "");
  const [message, setMessage] = useState("");
  const [authToken, setAuthToken] = useState(() => localStorage.getItem("googleIdToken") || "");

  const handleLoginSuccess = (email: string, token: string) => {
    setUserEmail(email);
    setAuthToken(token);
    setMessage(`Successfully authenticated with Google Sign-In as ${email}`);
  };

  const handleCron = async () => {
    try {
      const res = await triggerCronCleanup();
      setMessage(`Cleanup successful: Revoked ${res.revoked_count} stale device(s).`);
    } catch (e: any) {
      setMessage(`Error: ${e.message}`);
    }
  };

  return (
    <div style={{ padding: "20px", fontFamily: "sans-serif", maxWidth: "800px", margin: "0 auto" }}>
      <header style={{ borderBottom: "1px solid #ccc", paddingBottom: "15px", marginBottom: "20px" }}>
        <h1>Device Trust Gateway</h1>
        
        {/* Google Sign-In Authentication */}
        <div style={{ backgroundColor: "#f8f9fa", padding: "20px", borderRadius: "8px", marginTop: "15px", border: "1px solid #e9ecef" }}>
          <h3 style={{ marginTop: 0, marginBottom: "10px", fontSize: "18px", color: "#202124" }}>Google Authentication</h3>
          <p style={{ fontSize: "14px", color: "#5f6368", marginBottom: "15px" }}>
            Sign in with your Google Workspace enterprise account to authorize live device approvals and manage configurations.
          </p>
          
          {!userEmail ? (
            <GoogleLoginButton onLoginSuccess={handleLoginSuccess} />
          ) : (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", backgroundColor: "#e6f4ea", padding: "12px 18px", borderRadius: "6px", border: "1px solid #ceead6" }}>
              <div>
                <span style={{ fontSize: "12px", color: "#137333", fontWeight: "bold", display: "block", textTransform: "uppercase" }}>Active Production Session</span>
                <span style={{ fontSize: "16px", color: "#202124", fontWeight: "bold" }}>{userEmail}</span>
              </div>
              <button
                onClick={() => {
                  localStorage.removeItem("userEmail");
                  localStorage.removeItem("googleIdToken");
                  setUserEmail("");
                  setAuthToken("");
                  setMessage("Signed out successfully.");
                }}
                style={{ padding: "8px 14px", backgroundColor: "#137333", color: "white", border: "none", borderRadius: "4px", cursor: "pointer", fontWeight: "bold", fontSize: "12px" }}
              >
                Sign Out
              </button>
            </div>
          )}
        </div>
      </header>

      {message && (
        <div style={{ padding: "12px", backgroundColor: "#e6f7ff", border: "1px solid #91d5ff", marginBottom: "20px", borderRadius: "4px" }}>
          {message}
        </div>
      )}

      <section style={{ marginBottom: "30px" }}>
        <h2>My Approved Devices</h2>
        <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "10px" }}>
          <thead>
            <tr style={{ backgroundColor: "#f5f5f5", borderBottom: "2px solid #ddd" }}>
              <th style={{ padding: "10px", textAlign: "left" }}>Device Name</th>
              <th style={{ padding: "10px", textAlign: "left" }}>Type</th>
              <th style={{ padding: "10px", textAlign: "left" }}>Approval State</th>
            </tr>
          </thead>
          <tbody>
            <tr style={{ borderBottom: "1px solid #eee" }}>
              <td style={{ padding: "10px" }}>devices/chrome-cb123/deviceUsers/du-1</td>
              <td style={{ padding: "10px" }}>School Chromebook (Trust Anchor)</td>
              <td style={{ padding: "10px", color: "green", fontWeight: "bold" }}>APPROVED</td>
            </tr>
            <tr style={{ borderBottom: "1px solid #eee" }}>
              <td style={{ padding: "10px" }}>devices/pixel-phone99/deviceUsers/du-2</td>
              <td style={{ padding: "10px" }}>Personal Smartphone</td>
              <td style={{ padding: "10px", color: "green", fontWeight: "bold" }}>APPROVED</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section style={{ display: "flex", gap: "15px", flexWrap: "wrap", marginBottom: "30px" }}>
        <a
          href="#/chaining"
          style={{ padding: "15px 25px", backgroundColor: "#1a73e8", color: "white", textDecoration: "none", borderRadius: "5px", fontWeight: "bold" }}
        >
          Trust Chaining Portal
        </a>
        <a
          href="#/network"
          style={{ padding: "15px 25px", backgroundColor: "#34a853", color: "white", textDecoration: "none", borderRadius: "5px", fontWeight: "bold" }}
        >
          Campus Wi-Fi Approval
        </a>
        <a
          href="#/admin"
          style={{ padding: "15px 25px", backgroundColor: "#ea4335", color: "white", textDecoration: "none", borderRadius: "5px", fontWeight: "bold" }}
        >
          Admin Configurations
        </a>
      </section>

      <section style={{ borderTop: "1px solid #ccc", paddingTop: "20px" }}>
        <h3>System Lifecycle Management</h3>
        <p style={{ color: "#555", fontSize: "14px" }}>
          Simulate the Cloud Scheduler cron job that evaluates active BYOD devices against inactivity thresholds.
        </p>
        <button
          onClick={handleCron}
          style={{ padding: "10px 20px", backgroundColor: "#555", color: "white", border: "none", borderRadius: "4px", cursor: "pointer" }}
        >
          Trigger Inactivity Cleanup Cron
        </button>
      </section>
    </div>
  );
};
