import React, { useState, useEffect } from "react";
import { triggerCronCleanup } from "../services/api";

export const Dashboard: React.FC = () => {
  const [userEmail, setUserEmail] = useState(() => localStorage.getItem("userEmail") || "student@example.com");
  const [message, setMessage] = useState("");

  useEffect(() => {
    localStorage.setItem("userEmail", userEmail);
  }, [userEmail]);

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
      <header style={{ borderBottom: "1px solid #ccc", paddingBottom: "10px", marginBottom: "20px" }}>
        <h1>Device Trust Gateway</h1>
        <div style={{ marginTop: "10px" }}>
          <label style={{ fontWeight: "bold", marginRight: "10px" }}>Active User:</label>
          <input
            type="email"
            value={userEmail}
            onChange={(e) => setUserEmail(e.target.value)}
            style={{ padding: "5px", width: "250px" }}
          />
          <span style={{ marginLeft: "10px", fontSize: "12px", color: "#666" }}>(Update to simulate different roles)</span>
        </div>
      </header>

      {message && (
        <div style={{ padding: "10px", backgroundColor: "#e6f7ff", border: "1px solid #91d5ff", marginBottom: "20px" }}>
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
