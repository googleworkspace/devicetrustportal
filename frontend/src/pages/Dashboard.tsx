import React, { useState, useEffect, useCallback } from "react";
import { getMyDevices, approveDevice, revokeDevice, checkIsAdmin, DeviceUserItem } from "../services/api";
import { GoogleLoginButton } from "../components/GoogleLoginButton";

export const Dashboard: React.FC = () => {
  const [userEmail, setUserEmail] = useState(() => localStorage.getItem("userEmail") || "");
  const [message, setMessage] = useState("");
  const [authToken, setAuthToken] = useState(() => localStorage.getItem("googleIdToken") || "");
  
  const [devices, setDevices] = useState<DeviceUserItem[]>([]);
  const [loadingDevices, setLoadingDevices] = useState(false);
  const [deviceError, setDeviceError] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);

  const loadDevices = useCallback(() => {
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
  }, [userEmail]);

  useEffect(() => {
    loadDevices();
    if (userEmail) {
      checkIsAdmin().then(setIsAdmin);
    } else {
      setIsAdmin(false);
    }
  }, [userEmail, authToken, loadDevices]);

  const handleLoginSuccess = (email: string, token: string) => {
    setUserEmail(email);
    setAuthToken(token);
    setMessage(`Successfully authenticated with Google Sign-In as ${email}`);
  };

  const handleApprove = async (name: string) => {
    setMessage("");
    try {
      await approveDevice(name);
      setMessage("Device approved successfully.");
      // Instant local state update without re-fetching or triggering spinning loader
      setDevices((prev) =>
        prev.map((d) => (d.device_user_name === name ? { ...d, approval_state: "APPROVED" } : d))
      );
    } catch (e: any) {
      setMessage(`Failed to approve device: ${e.message}`);
    }
  };

  const handleRevoke = async (name: string) => {
    setMessage("");
    try {
      await revokeDevice(name);
      setMessage("Device revoked successfully.");
      // Instant local state update without re-fetching or triggering spinning loader
      setDevices((prev) =>
        prev.map((d) => (d.device_user_name === name ? { ...d, approval_state: "UNMANAGED" } : d))
      );
    } catch (e: any) {
      setMessage(`Failed to revoke device: ${e.message}`);
    }
  };

  return (
    <div style={{ padding: "20px", fontFamily: "sans-serif", maxWidth: "950px", margin: "0 auto" }}>
      <header style={{ borderBottom: "1px solid #ccc", paddingBottom: "15px", marginBottom: "20px", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "15px" }}>
        <h1 style={{ margin: 0 }}>Device Trust Gateway</h1>
        
        {/* Admin Config UI dynamically gated by Workspace Super Admin privileges at top header */}
        {isAdmin && (
          <a
            href="#/admin"
            style={{ padding: "10px 18px", backgroundColor: "#ea4335", color: "white", textDecoration: "none", borderRadius: "5px", fontWeight: "bold", fontSize: "14px", display: "inline-block" }}
          >
            ⚙️ Admin Configurations
          </a>
        )}
      </header>

      {/* Google Sign-In Authentication Container */}
      <div style={{ backgroundColor: "#f8f9fa", padding: "20px", borderRadius: "8px", marginBottom: "25px", border: "1px solid #e9ecef" }}>
        <h3 style={{ marginTop: 0, marginBottom: "10px", fontSize: "18px", color: "#202124" }}>Google Authentication</h3>
        <p style={{ fontSize: "14px", color: "#5f6368", marginBottom: "15px" }}>
          Sign in with your Google Workspace enterprise account to authorize live device approvals and manage configurations.
        </p>
        
        {!userEmail ? (
          <GoogleLoginButton onLoginSuccess={handleLoginSuccess} />
        ) : (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", backgroundColor: "#e6f4ea", padding: "12px 18px", borderRadius: "6px", border: "1px solid #ceead6", flexWrap: "wrap", gap: "10px" }}>
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
                setIsAdmin(false);
                setMessage("Signed out successfully.");
              }}
              style={{ padding: "8px 14px", backgroundColor: "#137333", color: "white", border: "none", borderRadius: "4px", cursor: "pointer", fontWeight: "bold", fontSize: "12px" }}
            >
              Sign Out
            </button>
          </div>
        )}
      </div>

      {message && (
        <div style={{ padding: "12px", backgroundColor: "#e6f7ff", border: "1px solid #91d5ff", marginBottom: "20px", borderRadius: "4px" }}>
          {message}
        </div>
      )}

      <section style={{ marginBottom: "30px" }}>
        <h2>My Hardware Assets</h2>
        
        {!userEmail ? (
          <div style={{ padding: "15px", backgroundColor: "#fff3cd", color: "#856404", border: "1px solid #ffeeba", borderRadius: "4px" }}>
            Please sign in with Google above to view your registered enterprise hardware assets.
          </div>
        ) : loadingDevices ? (
          <div style={{ padding: "40px 20px", backgroundColor: "#f8f9fa", border: "1px solid #e9ecef", borderRadius: "8px", textAlign: "center", marginTop: "10px" }}>
            <style>
              {`@keyframes spin { to { transform: rotate(360deg); } }`}
            </style>
            <div style={{ display: "inline-block", width: "40px", height: "40px", border: "4px solid rgba(26, 115, 232, 0.2)", borderRadius: "50%", borderTopColor: "#1a73e8", animation: "spin 1s ease-in-out infinite", marginBottom: "15px" }} />
            <div style={{ fontWeight: "bold", color: "#202124", fontSize: "16px", marginBottom: "6px" }}>Retrieving your registered devices...</div>
            <div style={{ color: "#5f6368", fontSize: "13px" }}>Securely verifying your hardware inventory for <b>{userEmail}</b>.</div>
          </div>
        ) : deviceError ? (
          <div style={{ padding: "15px", backgroundColor: "#f8d7da", color: "#721c24", border: "1px solid #f5c6cb", borderRadius: "4px" }}>
            {deviceError}
          </div>
        ) : devices.length === 0 ? (
          <div style={{ padding: "25px", backgroundColor: "#f8f9fa", color: "#6c757d", border: "1px solid #dee2e6", borderRadius: "6px", textAlign: "center" }}>
            <div style={{ fontSize: "16px", fontWeight: "bold", marginBottom: "8px", color: "#3c4043" }}>No Registered Hardware Assets Discovered</div>
            <div style={{ fontSize: "14px" }}>We successfully checked your inventory but found no approved devices matching <b>{userEmail}</b>.</div>
            <div style={{ fontSize: "13px", marginTop: "10px", color: "#1a73e8" }}>Ensure your Endpoint Verification extension is actively reporting your device!</div>
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "10px", backgroundColor: "#fff", boxShadow: "0 1px 3px rgba(0,0,0,0.1)", borderRadius: "6px", overflow: "hidden" }}>
            <thead>
              <tr style={{ backgroundColor: "#f1f3f4", borderBottom: "2px solid #dadce0" }}>
                <th style={{ padding: "12px 15px", textAlign: "left", color: "#202124", fontSize: "14px" }}>Hardware Model</th>
                <th style={{ padding: "12px 15px", textAlign: "left", color: "#202124", fontSize: "14px" }}>Operating System</th>
                <th style={{ padding: "12px 15px", textAlign: "left", color: "#202124", fontSize: "14px" }}>Identifier</th>
                <th style={{ padding: "12px 15px", textAlign: "left", color: "#202124", fontSize: "14px" }}>Approval State</th>
                <th style={{ padding: "12px 15px", textAlign: "left", color: "#202124", fontSize: "14px" }}>Last Sync</th>
                <th style={{ padding: "12px 15px", textAlign: "center", color: "#202124", fontSize: "14px" }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {devices.map((d, i) => (
                <tr key={i} style={{ borderBottom: "1px solid #eee" }}>
                  <td style={{ padding: "14px 15px", color: "#202124", fontWeight: "bold", fontSize: "14px" }}>{d.model}</td>
                  <td style={{ padding: "14px 15px", color: "#5f6368", fontSize: "14px" }}>{d.os_version} ({d.device_type})</td>
                  <td style={{ padding: "14px 15px", fontFamily: "monospace", fontSize: "13px", color: "#3c4043" }}>
                    <div>{d.serial_number !== "N/A" ? `Serial/IMEI: ${d.serial_number}` : "Virtual Asset / EV Cert"}</div>
                  </td>
                  <td style={{ padding: "14px 15px" }}>
                    <span style={{ padding: "4px 8px", backgroundColor: d.approval_state === "APPROVED" ? "#e6f4ea" : "#fef7e0", color: d.approval_state === "APPROVED" ? "#137333" : "#b06000", borderRadius: "4px", fontWeight: "bold", fontSize: "12px", textTransform: "uppercase", border: `1px solid ${d.approval_state === "APPROVED" ? "#ceead6" : "#feefc3"}` }}>
                      {d.approval_state}
                    </span>
                  </td>
                  <td style={{ padding: "14px 15px", color: "#5f6368", fontSize: "13px" }}>{d.last_sync_time}</td>
                  <td style={{ padding: "14px 15px", textAlign: "center" }}>
                    {d.approval_state === "APPROVED" ? (
                      <button
                        onClick={() => handleRevoke(d.device_user_name)}
                        style={{ padding: "6px 12px", backgroundColor: "#d93025", color: "white", border: "none", borderRadius: "4px", cursor: "pointer", fontSize: "12px", fontWeight: "bold" }}
                      >
                        ✕ Revoke
                      </button>
                    ) : (
                      <button
                        onClick={() => handleApprove(d.device_user_name)}
                        style={{ padding: "6px 12px", backgroundColor: "#137333", color: "white", border: "none", borderRadius: "4px", cursor: "pointer", fontSize: "12px", fontWeight: "bold" }}
                      >
                        ✓ Approve
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
};
