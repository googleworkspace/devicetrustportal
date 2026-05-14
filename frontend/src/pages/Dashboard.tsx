import React, { useState, useEffect } from "react";
import { triggerCronCleanup, getMyDevices, DeviceUserItem } from "../services/api";
import { GoogleLoginButton } from "../components/GoogleLoginButton";

export const Dashboard: React.FC = () => {
  const [userEmail, setUserEmail] = useState(() => localStorage.getItem("userEmail") || "");
  const [message, setMessage] = useState("");
  const [authToken, setAuthToken] = useState(() => localStorage.getItem("googleIdToken") || "");
  
  // Real production devices state
  const [devices, setDevices] = useState<DeviceUserItem[]>([]);
  const [loadingDevices, setLoadingDevices] = useState(false);
  const [deviceError, setDeviceError] = useState("");

  useEffect(() => {
    if (userEmail) {
      setLoadingDevices(true);
      setDeviceError("");
      getMyDevices()
        .then((data) => {
          setDevices(data);
          setLoadingDevices(false);
        })
        .catch((err) => {
          setDeviceError(`Failed to load approved devices: ${err.message}`);
          setLoadingDevices(false);
        });
    } else {
      setDevices([]);
    }
  }, [userEmail, authToken]);

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
                  setDevices([]);
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
        
        {!userEmail ? (
          <div style={{ padding: "15px", backgroundColor: "#fff3cd", color: "#856404", border: "1px solid #ffeeba", borderRadius: "4px" }}>
            Please sign in with Google above to view your registered enterprise hardware assets.
          </div>
        ) : loadingDevices ? (
          <div style={{ padding: "15px", color: "#555", fontStyle: "italic" }}>Loading approved devices from Cloud Identity...</div>
        ) : deviceError ? (
          <div style={{ padding: "15px", backgroundColor: "#f8d7da", color: "#721c24", border: "1px solid #f5c6cb", borderRadius: "4px" }}>
            {deviceError}
          </div>
        ) : devices.length === 0 ? (
          <div style={{ padding: "20px", backgroundColor: "#f8f9fa", color: "#6c757d", border: "1px solid #dee2e6", borderRadius: "4px", textAlign: "center" }}>
            No approved personal devices found for <b>{userEmail}</b>. Use the registration portals below to authorize your hardware.
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "10px" }}>
            <thead>
              <tr style={{ backgroundColor: "#f5f5f5", borderBottom: "2px solid #ddd" }}>
                <th style={{ padding: "10px", textAlign: "left" }}>Device Resource Name</th>
                <th style={{ padding: "10px", textAlign: "left" }}>Type</th>
                <th style={{ padding: "10px", textAlign: "left" }}>Approval State</th>
                <th style={{ padding: "10px", textAlign: "left" }}>Last Sync</th>
              </tr>
            </thead>
            <tbody>
              {devices.map((d, i) => (
                <tr key={i} style={{ borderBottom: "1px solid #eee" }}>
                  <td style={{ padding: "10px", fontFamily: "monospace", fontSize: "13px" }}>{d.device_user_name}</td>
                  <td style={{ padding: "10px", fontSize: "14px" }}>{d.device_type}</td>
                  <td style={{ padding: "10px", color: "green", fontWeight: "bold", fontSize: "14px" }}>{d.approval_state}</td>
                  <td style={{ padding: "10px", color: "#666", fontSize: "13px" }}>{d.last_sync_time}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
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
