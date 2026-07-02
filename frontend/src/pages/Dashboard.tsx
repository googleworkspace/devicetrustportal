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

import React, { useState, useEffect, useCallback } from "react";
import { getMyDevices, approveDevice, revokeDevice, revokeDeviceBulk, checkIsAdmin, getPublicConfig, DeviceUserItem } from "../services/api";
import { GoogleLoginButton } from "../components/GoogleLoginButton";
import { getTranslator } from "../i18n/translations";

export const Dashboard: React.FC = () => {
  const [userEmail, setUserEmail] = useState(() => localStorage.getItem("userEmail") || "");
  const [message, setMessage] = useState("");
  const [authToken, setAuthToken] = useState(() => localStorage.getItem("googleIdToken") || "");
  const [locale, setLocale] = useState(() => localStorage.getItem("userLocale") || "en");
  const t = getTranslator(locale);

  useEffect(() => {
    getPublicConfig().then((data) => {
      if (data?.default_locale && !localStorage.getItem("userLocale")) {
        const browserLang = navigator.language?.slice(0, 2);
        setLocale(["en", "es", "fr", "ja"].includes(browserLang) ? browserLang : data.default_locale);
      }
    }).catch(() => {});
  }, []);

  const [devices, setDevices] = useState<DeviceUserItem[]>([]);
  const [loadingDevices, setLoadingDevices] = useState(false);
  const [deviceError, setDeviceError] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);

  // Bulk Selection & Revocation Modal State
  const [selectedDevices, setSelectedDevices] = useState<string[]>([]);
  const [revokeTarget, setRevokeTarget] = useState<string[]>([]);
  const [showRevokeModal, setShowRevokeModal] = useState(false);
  const [isRevoking, setIsRevoking] = useState(false);

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
      setDevices((prev) =>
        prev.map((d) => (d.device_user_name === name ? { ...d, approval_state: "APPROVED" } : d))
      );
    } catch (e: any) {
      setMessage(`Failed to approve device: ${e.message}`);
    }
  };

  const initiateRevoke = (names: string[]) => {
    setRevokeTarget(names);
    setShowRevokeModal(true);
  };

  // Execute confirmed revocation (Single or Bulk Batch)
  const handleConfirmRevoke = async () => {
    setIsRevoking(true);
    setMessage("");

    try {
      if (revokeTarget.length === 1) {
        await revokeDevice(revokeTarget[0]);
      } else {
        await revokeDeviceBulk(revokeTarget);
      }

      setDevices((prev) =>
        prev.map((d) => (revokeTarget.includes(d.device_user_name) ? { ...d, approval_state: "UNMANAGED" } : d))
      );
      setMessage(`Successfully revoked approval for ${revokeTarget.length} device(s).`);
    } catch (e: any) {
      setMessage(`Failed to revoke device(s): ${e.message}`);
    }

    setIsRevoking(false);
    setShowRevokeModal(false);
    setSelectedDevices([]);
    setRevokeTarget([]);
  };

  const handleSelectAll = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.checked) {
      const revokable = devices
        .filter((d) => d.owner_type !== "COMPANY" && d.approval_state === "APPROVED")
        .map((d) => d.device_user_name);
      setSelectedDevices(revokable);
    } else {
      setSelectedDevices([]);
    }
  };

  const handleSelectSingle = (name: string) => {
    if (selectedDevices.includes(name)) {
      setSelectedDevices((prev) => prev.filter((n) => n !== name));
    } else {
      setSelectedDevices((prev) => [...prev, name]);
    }
  };

  const formatLastSync = (isoStr: string) => {
    if (!isoStr || isoStr === "N/A") return "N/A";
    try {
      const d = new Date(isoStr);
      if (isNaN(d.getTime())) return isoStr;
      return d.toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch (e) {
      return isoStr;
    }
  };

  return (
    <div style={{ padding: "20px", fontFamily: "sans-serif", maxWidth: "950px", margin: "0 auto", position: "relative" }}>
      <header style={{ borderBottom: "1px solid #ccc", paddingBottom: "15px", marginBottom: "20px", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "15px" }}>
        <div>
          <h1 style={{ margin: 0 }}>{t.portalTitle}</h1>
          <div style={{ fontSize: "13px", color: "#5f6368", marginTop: "4px" }}>{t.subtitle}</div>
        </div>
        
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <select
            value={locale}
            onChange={(e) => {
              setLocale(e.target.value);
              localStorage.setItem("userLocale", e.target.value);
            }}
            style={{ padding: "8px 12px", borderRadius: "4px", border: "1px solid #ccc", fontSize: "14px", backgroundColor: "#fff", cursor: "pointer" }}
          >
            <option value="en">🌐 English (en)</option>
            <option value="es">🌐 Español (es)</option>
            <option value="fr">🌐 Français (fr)</option>
            <option value="ja">🌐 日本語 (ja)</option>
          </select>

          {isAdmin && (
            <a
              href="#/admin"
              style={{ padding: "10px 18px", backgroundColor: "#ea4335", color: "white", textDecoration: "none", borderRadius: "5px", fontWeight: "bold", fontSize: "14px", display: "inline-block" }}
            >
              ⚙️ {t.adminConfigTab}
            </a>
          )}
        </div>
      </header>

      {/* Google Sign-In Container */}
      <div style={{ backgroundColor: "#f8f9fa", padding: "20px", borderRadius: "8px", marginBottom: "25px", border: "1px solid #e9ecef" }}>
        <h3 style={{ marginTop: 0, marginBottom: "10px", fontSize: "18px", color: "#202124" }}>Google Workspace Authentication</h3>
        <p style={{ fontSize: "14px", color: "#5f6368", marginBottom: "15px" }}>
          {t.signInPrompt}
        </p>
        
        {!userEmail ? (
          <GoogleLoginButton onLoginSuccess={handleLoginSuccess} />
        ) : (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", backgroundColor: "#e6f4ea", padding: "12px 18px", borderRadius: "6px", border: "1px solid #ceead6", flexWrap: "wrap", gap: "10px" }}>
            <div>
              <span style={{ fontSize: "12px", color: "#137333", fontWeight: "bold", display: "block", textTransform: "uppercase" }}>{t.signedInAs}</span>
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
              {t.signOut}
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
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "15px", flexWrap: "wrap", gap: "10px" }}>
          <h2 style={{ margin: 0 }}>My Hardware Assets</h2>
          {selectedDevices.length > 0 && (
            <button
              onClick={() => initiateRevoke(selectedDevices)}
              style={{ padding: "8px 16px", backgroundColor: "#d93025", color: "white", border: "none", borderRadius: "4px", cursor: "pointer", fontSize: "14px", fontWeight: "bold" }}
            >
              ✕ Bulk Revoke Selected ({selectedDevices.length})
            </button>
          )}
        </div>
        
        {!userEmail ? (
          <div style={{ padding: "15px", backgroundColor: "#fff3cd", color: "#856404", border: "1px solid #ffeeba", borderRadius: "4px" }}>
            {t.signInPrompt}
          </div>
        ) : loadingDevices ? (
          <div style={{ padding: "40px 20px", backgroundColor: "#f8f9fa", border: "1px solid #e9ecef", borderRadius: "8px", textAlign: "center", marginTop: "10px" }}>
            <style>
              {`@keyframes spin { to { transform: rotate(360deg); } }`}
            </style>
            <div style={{ display: "inline-block", width: "40px", height: "40px", border: "4px solid rgba(26, 115, 232, 0.2)", borderRadius: "50%", borderTopColor: "#1a73e8", animation: "spin 1s ease-in-out infinite", marginBottom: "15px" }} />
            <div style={{ fontWeight: "bold", color: "#202124", fontSize: "16px", marginBottom: "6px" }}>{t.loadingDevices}</div>
            <div style={{ color: "#5f6368", fontSize: "13px" }}>Securely verifying your hardware inventory for <b>{userEmail}</b>.</div>
          </div>
        ) : deviceError ? (
          <div style={{ padding: "15px", backgroundColor: "#f8d7da", color: "#721c24", border: "1px solid #f5c6cb", borderRadius: "4px" }}>
            {deviceError}
          </div>
        ) : devices.length === 0 ? (
          <div style={{ padding: "25px", backgroundColor: "#f8f9fa", color: "#6c757d", border: "1px solid #dee2e6", borderRadius: "6px", textAlign: "center" }}>
            <div style={{ fontSize: "16px", fontWeight: "bold", marginBottom: "8px", color: "#3c4043" }}>{t.noApprovedDevices}</div>
            <div style={{ fontSize: "14px" }}>We checked your inventory but found no approved devices matching <b>{userEmail}</b>.</div>
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "10px", backgroundColor: "#fff", boxShadow: "0 1px 3px rgba(0,0,0,0.1)", borderRadius: "6px", overflow: "hidden" }}>
            <thead>
              <tr style={{ backgroundColor: "#f1f3f4", borderBottom: "2px solid #dadce0" }}>
                <th style={{ padding: "12px 15px", width: "30px", textAlign: "center" }}>
                  <input
                    type="checkbox"
                    onChange={handleSelectAll}
                    checked={
                      devices.filter((d) => d.owner_type !== "COMPANY" && d.approval_state === "APPROVED").length > 0 &&
                      selectedDevices.length === devices.filter((d) => d.owner_type !== "COMPANY" && d.approval_state === "APPROVED").length
                    }
                  />
                </th>
                <th style={{ padding: "12px 15px", textAlign: "left", color: "#202124", fontSize: "14px" }}>{t.deviceHeader}</th>
                <th style={{ padding: "12px 15px", textAlign: "left", color: "#202124", fontSize: "14px" }}>Operating System</th>
                <th style={{ padding: "12px 15px", textAlign: "left", color: "#202124", fontSize: "14px" }}>Identifier</th>
                <th style={{ padding: "12px 15px", textAlign: "left", color: "#202124", fontSize: "14px" }}>{t.statusHeader}</th>
                <th style={{ padding: "12px 15px", textAlign: "left", color: "#202124", fontSize: "14px" }}>Last Sync</th>
                <th style={{ padding: "12px 15px", textAlign: "center", color: "#202124", fontSize: "14px" }}>{t.actionsHeader}</th>
              </tr>
            </thead>
            <tbody>
              {devices.map((d, i) => {
                const isRevokable = d.owner_type !== "COMPANY" && d.approval_state === "APPROVED";
                return (
                  <tr key={i} style={{ borderBottom: "1px solid #eee", backgroundColor: selectedDevices.includes(d.device_user_name) ? "#fce8e6" : "inherit" }}>
                    <td style={{ padding: "14px 15px", textAlign: "center" }}>
                      <input
                        type="checkbox"
                        checked={selectedDevices.includes(d.device_user_name)}
                        onChange={() => handleSelectSingle(d.device_user_name)}
                        disabled={!isRevokable}
                      />
                    </td>
                    <td style={{ padding: "14px 15px", color: "#202124" }}>
                      <div style={{ fontWeight: "bold", fontSize: "14px" }}>{d.model}</div>
                      <div style={{ fontSize: "11px", color: d.owner_type === "COMPANY" ? "#1a73e8" : "#5f6368", fontWeight: d.owner_type === "COMPANY" ? "bold" : "normal", marginTop: "2px", textTransform: "uppercase" }}>
                        {d.owner_type === "COMPANY" ? "🏢 Company Owned Asset" : "👤 Personal BYOD"}
                      </div>
                    </td>
                    <td style={{ padding: "14px 15px", color: "#5f6368", fontSize: "14px" }}>{d.os_version} ({d.device_type})</td>
                    <td style={{ padding: "14px 15px", fontFamily: "monospace", fontSize: "13px", color: "#3c4043" }}>
                      <div>{d.serial_number !== "N/A" ? `Serial/IMEI: ${d.serial_number}` : "Virtual Asset / EV Cert"}</div>
                    </td>
                    <td style={{ padding: "14px 15px" }}>
                      <span style={{ padding: "4px 8px", backgroundColor: d.approval_state === "APPROVED" ? "#e6f4ea" : "#fef7e0", color: d.approval_state === "APPROVED" ? "#137333" : "#b06000", borderRadius: "4px", fontWeight: "bold", fontSize: "12px", textTransform: "uppercase", border: `1px solid ${d.approval_state === "APPROVED" ? "#ceead6" : "#feefc3"}` }}>
                        {d.approval_state}
                      </span>
                    </td>
                    <td style={{ padding: "14px 15px", color: "#5f6368", fontSize: "13px" }}>{formatLastSync(d.last_sync_time)}</td>
                    <td style={{ padding: "14px 15px", textAlign: "center" }}>
                      {d.owner_type === "COMPANY" ? (
                        <span style={{ padding: "6px 12px", backgroundColor: "#e8f0fe", color: "#1a73e8", borderRadius: "4px", fontSize: "12px", fontWeight: "bold", display: "inline-block", border: "1px solid #d2e3fc" }}>
                          🔒 Immutable Anchor
                        </span>
                      ) : d.approval_state === "APPROVED" ? (
                        <button
                          onClick={() => initiateRevoke([d.device_user_name])}
                          style={{ padding: "6px 12px", backgroundColor: "#d93025", color: "white", border: "none", borderRadius: "4px", cursor: "pointer", fontSize: "12px", fontWeight: "bold" }}
                        >
                          ✕ {t.revokeAction}
                        </button>
                      ) : (
                        <button
                          onClick={() => handleApprove(d.device_user_name)}
                          style={{ padding: "6px 12px", backgroundColor: "#137333", color: "white", border: "none", borderRadius: "4px", cursor: "pointer", fontSize: "12px", fontWeight: "bold" }}
                        >
                          ✓ {t.approveAction}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>

      {/* Revocation Confirmation Modal Overlay */}
      {showRevokeModal && (
        <div style={{ position: "fixed", top: 0, left: 0, width: "100vw", height: "100vh", backgroundColor: "rgba(0,0,0,0.5)", display: "flex", justifyContent: "center", alignItems: "center", zIndex: 9999 }}>
          <div style={{ backgroundColor: "#fff", padding: "30px", borderRadius: "8px", maxWidth: "500px", width: "90%", boxShadow: "0 4px 15px rgba(0,0,0,0.2)" }}>
            <div style={{ fontSize: "20px", fontWeight: "bold", color: "#d93025", marginBottom: "15px", display: "flex", alignItems: "center", gap: "10px" }}>
              ⚠️ Confirm Access Revocation
            </div>
            <p style={{ color: "#202124", fontSize: "15px", lineHeight: "1.5", marginBottom: "15px" }}>
              Are you absolutely sure you want to revoke approval for the following <b>{revokeTarget.length}</b> device(s)?
            </p>
            <div style={{ maxHeight: "150px", overflowY: "auto", backgroundColor: "#f1f3f4", padding: "12px", borderRadius: "6px", marginBottom: "20px", fontSize: "13px", fontFamily: "monospace", color: "#3c4043" }}>
              {revokeTarget.map((t, idx) => {
                const matchingDev = devices.find((d) => d.device_user_name === t);
                return (
                  <div key={idx} style={{ marginBottom: "6px" }}>
                    • {matchingDev ? `${matchingDev.model} (Serial: ${matchingDev.serial_number})` : t}
                  </div>
                );
              })}
            </div>
            <p style={{ color: "#5f6368", fontSize: "13px", marginBottom: "25px" }}>
              This action will instantly unapprove the device binding in Cloud Identity. Enterprise resources gated by Context-Aware Access policies will be immediately blocked.
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "15px" }}>
              <button
                onClick={() => setShowRevokeModal(false)}
                disabled={isRevoking}
                style={{ padding: "10px 18px", backgroundColor: "#f1f3f4", color: "#3c4043", border: "none", borderRadius: "4px", cursor: "pointer", fontWeight: "bold", fontSize: "14px" }}
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmRevoke}
                disabled={isRevoking}
                style={{ padding: "10px 18px", backgroundColor: "#d93025", color: "white", border: "none", borderRadius: "4px", cursor: "pointer", fontWeight: "bold", fontSize: "14px" }}
              >
                {isRevoking ? "Revoking Access..." : "Yes, Revoke Access"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
