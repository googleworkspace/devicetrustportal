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
        setLocale(["en", "es", "fr", "ja", "de", "pt", "zh", "it"].includes(browserLang) ? browserLang : data.default_locale);
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
    <div style={{ backgroundColor: "#f8f9fa", minHeight: "100vh", fontFamily: "'Google Sans', Roboto, Arial, sans-serif", color: "#202124" }}>
      {/* Google Cloud Console / Workspace Top Navigation App Bar */}
      <header style={{ backgroundColor: "#ffffff", borderBottom: "1px solid #dadce0", padding: "12px 24px", display: "flex", justifyContent: "space-between", alignItems: "center", position: "sticky", top: 0, zIndex: 1000, boxShadow: "0 1px 2px 0 rgba(60,64,67,0.1)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          {/* Authentic Google Shield Lockup Icon */}
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2L3 6V11C3 16.55 6.84 21.74 12 23C17.16 21.74 21 16.55 21 11V6L12 2Z" fill="#1a73e8"/>
            <path d="M12 6V11H17C16.47 14.19 14.52 16.8 12 17.65V23C17.16 21.74 21 16.55 21 11H12V6Z" fill="#4285F4" opacity="0.8"/>
            <path d="M10.5 15.5L6.5 11.5L7.91 10.09L10.5 12.67L16.09 7.09L17.5 8.5L10.5 15.5Z" fill="#ffffff"/>
          </svg>
          <div>
            <h1 style={{ margin: 0, fontSize: "18px", fontWeight: 500, letterSpacing: "-0.2px", color: "#202124" }}>{t.portalTitle}</h1>
            <div style={{ fontSize: "12px", color: "#5f6368", marginTop: "2px" }}>{t.subtitle}</div>
          </div>
        </div>
        
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <select
            aria-label="Language Selector"
            value={locale}
            onChange={(e) => {
              setLocale(e.target.value);
              localStorage.setItem("userLocale", e.target.value);
            }}
            style={{ padding: "6px 12px", borderRadius: "4px", border: "1px solid #dadce0", fontSize: "13px", backgroundColor: "#ffffff", color: "#3c4043", cursor: "pointer", fontWeight: 500 }}
          >
            <option value="en">English (en)</option>
            <option value="es">Español (es)</option>
            <option value="fr">Français (fr)</option>
            <option value="ja">日本語 (ja)</option>
            <option value="de">Deutsch (de)</option>
            <option value="pt">Português (pt)</option>
            <option value="zh">简体中文 (zh)</option>
            <option value="it">Italiano (it)</option>
          </select>

          {isAdmin && (
            <a
              href="#/admin"
              style={{ padding: "6px 14px", backgroundColor: "#ffffff", color: "#1a73e8", border: "1px solid #dadce0", textDecoration: "none", borderRadius: "4px", fontWeight: 500, fontSize: "13px", display: "inline-flex", alignItems: "center", gap: "6px", boxShadow: "0 1px 2px 0 rgba(60,64,67,0.1)" }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/>
              </svg>
              {t.adminConfigTab}
            </a>
          )}
        </div>
      </header>

      <main style={{ padding: "24px", maxWidth: "1100px", margin: "0 auto" }}>
        {/* Google Workspace Authentication Surface Card */}
        <div style={{ backgroundColor: "#ffffff", padding: "24px", borderRadius: "8px", marginBottom: "24px", border: "1px solid #dadce0", boxShadow: "0 1px 2px 0 rgba(60,64,67,0.3)" }}>
          <h3 style={{ marginTop: 0, marginBottom: "8px", fontSize: "16px", fontWeight: 500, color: "#202124" }}>{t.googleAuthTitle}</h3>
          <p style={{ fontSize: "13px", color: "#5f6368", marginBottom: "16px", marginTop: 0 }}>
            {t.signInPrompt}
          </p>
          
          {!userEmail ? (
            <GoogleLoginButton onLoginSuccess={handleLoginSuccess} />
          ) : (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", backgroundColor: "#f8f9fa", padding: "12px 16px", borderRadius: "6px", border: "1px solid #dadce0", flexWrap: "wrap", gap: "12px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                <div style={{ width: "36px", height: "36px", borderRadius: "50%", backgroundColor: "#e8f0fe", color: "#1a73e8", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 500, fontSize: "15px" }}>
                  {userEmail.charAt(0).toUpperCase()}
                </div>
                <div>
                  <span style={{ fontSize: "11px", color: "#5f6368", fontWeight: 500, display: "block", textTransform: "uppercase", letterSpacing: "0.5px" }}>{t.signedInAs}</span>
                  <span style={{ fontSize: "14px", color: "#202124", fontWeight: 500 }}>{userEmail}</span>
                </div>
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
                style={{ padding: "6px 14px", backgroundColor: "#ffffff", color: "#3c4043", border: "1px solid #dadce0", borderRadius: "4px", cursor: "pointer", fontWeight: 500, fontSize: "13px", transition: "all 0.15s ease" }}
              >
                {t.signOut}
              </button>
            </div>
          )}
        </div>

      {message && (
        <div role="status" aria-live="polite" style={{ padding: "12px 16px", backgroundColor: "#e8f0fe", border: "1px solid #d2e3fc", color: "#1a73e8", marginBottom: "20px", borderRadius: "6px", fontWeight: 500 }}>
          {message}
        </div>
      )}

      <section style={{ marginBottom: "30px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "12px" }}>
          <h2 style={{ margin: 0, fontSize: "20px", fontWeight: 500, color: "#202124" }}>{t.myHardwareAssetsTitle}</h2>
          {selectedDevices.length > 0 && (
            <button
              onClick={() => initiateRevoke(selectedDevices)}
              style={{ padding: "8px 16px", backgroundColor: "#d93025", color: "white", border: "none", borderRadius: "4px", cursor: "pointer", fontSize: "14px", fontWeight: 500 }}
            >
              ✕ {t.bulkRevokeSelected} ({selectedDevices.length})
            </button>
          )}
        </div>
        
        {!userEmail ? (
          <div role="status" style={{ padding: "16px", backgroundColor: "#fef7e0", color: "#b06000", border: "1px solid #feefc3", borderRadius: "6px", fontWeight: 500 }}>
            {t.signInPrompt}
          </div>
        ) : loadingDevices ? (
          <div role="status" aria-live="polite" style={{ padding: "40px 20px", backgroundColor: "#ffffff", border: "1px solid #dadce0", borderRadius: "8px", textAlign: "center", marginTop: "10px", boxShadow: "0 1px 2px 0 rgba(60,64,67,0.3)" }}>
            <style>
              {`@keyframes spin { to { transform: rotate(360deg); } }`}
            </style>
            <div style={{ display: "inline-block", width: "40px", height: "40px", border: "4px solid rgba(26, 115, 232, 0.2)", borderRadius: "50%", borderTopColor: "#1a73e8", animation: "spin 1s ease-in-out infinite", marginBottom: "15px" }} />
            <div style={{ fontWeight: 500, color: "#202124", fontSize: "16px", marginBottom: "6px" }}>{t.loadingDevices}</div>
            <div style={{ color: "#5f6368", fontSize: "13px" }}>Securely verifying your hardware inventory for <b>{userEmail}</b>.</div>
          </div>
        ) : deviceError ? (
          <div role="alert" style={{ padding: "16px", backgroundColor: "#fce8e6", color: "#c5221f", border: "1px solid #f8d7da", borderRadius: "6px", fontWeight: 500 }}>
            {deviceError}
          </div>
        ) : devices.length === 0 ? (
          <div role="status" style={{ padding: "30px", backgroundColor: "#ffffff", color: "#5f6368", border: "1px solid #dadce0", borderRadius: "8px", textAlign: "center", boxShadow: "0 1px 2px 0 rgba(60,64,67,0.3)" }}>
            <div style={{ fontSize: "16px", fontWeight: 500, marginBottom: "8px", color: "#202124" }}>{t.noApprovedDevices}</div>
            <div style={{ fontSize: "14px" }}>We checked your inventory but found no approved devices matching <b>{userEmail}</b>.</div>
          </div>
        ) : (
          <table aria-label="Registered Hardware Inventory Table" style={{ width: "100%", borderCollapse: "collapse", marginTop: "10px", backgroundColor: "#ffffff", boxShadow: "0 1px 2px 0 rgba(60,64,67,0.3), 0 1px 3px 1px rgba(60,64,67,0.15)", borderRadius: "8px", overflow: "hidden" }}>
            <thead>
              <tr style={{ backgroundColor: "#f8f9fa", borderBottom: "2px solid #dadce0" }}>
                <th scope="col" style={{ padding: "14px 16px", width: "40px", textAlign: "center" }}>
                  <input
                    type="checkbox"
                    aria-label="Select all eligible devices"
                    onChange={handleSelectAll}
                    checked={
                      devices.filter((d) => d.owner_type !== "COMPANY" && d.approval_state === "APPROVED").length > 0 &&
                      selectedDevices.length === devices.filter((d) => d.owner_type !== "COMPANY" && d.approval_state === "APPROVED").length
                    }
                  />
                </th>
                <th scope="col" style={{ padding: "14px 16px", textAlign: "left", color: "#202124", fontSize: "14px", fontWeight: 500 }}>{t.deviceHeader}</th>
                <th scope="col" style={{ padding: "14px 16px", textAlign: "left", color: "#202124", fontSize: "14px", fontWeight: 500 }}>{t.osHeader}</th>
                <th scope="col" style={{ padding: "14px 16px", textAlign: "left", color: "#202124", fontSize: "14px", fontWeight: 500 }}>{t.idHeader}</th>
                <th scope="col" style={{ padding: "14px 16px", textAlign: "left", color: "#202124", fontSize: "14px", fontWeight: 500 }}>{t.statusHeader}</th>
                <th scope="col" style={{ padding: "14px 16px", textAlign: "left", color: "#202124", fontSize: "14px", fontWeight: 500 }}>{t.lastSyncHeader}</th>
                <th scope="col" style={{ padding: "14px 16px", textAlign: "center", color: "#202124", fontSize: "14px", fontWeight: 500 }}>{t.actionsHeader}</th>
              </tr>
            </thead>
            <tbody>
              {devices.map((d, i) => {
                const isRevokable = d.owner_type !== "COMPANY" && d.approval_state === "APPROVED";
                return (
                  <tr key={i} style={{ borderBottom: "1px solid #eee", backgroundColor: selectedDevices.includes(d.device_user_name) ? "#fce8e6" : "inherit" }}>
                    <td style={{ padding: "14px 16px", textAlign: "center" }}>
                      <input
                        type="checkbox"
                        aria-label={`Select device ${d.model}`}
                        checked={selectedDevices.includes(d.device_user_name)}
                        onChange={() => handleSelectSingle(d.device_user_name)}
                        disabled={!isRevokable}
                      />
                    </td>
                    <td style={{ padding: "14px 16px", color: "#202124" }}>
                      <div style={{ fontWeight: 500, fontSize: "14px" }}>{d.model}</div>
                      <div style={{ fontSize: "11px", color: d.owner_type === "COMPANY" ? "#1a73e8" : "#5f6368", fontWeight: d.owner_type === "COMPANY" ? 500 : 400, marginTop: "2px", textTransform: "uppercase" }}>
                        {d.owner_type === "COMPANY" ? t.companyOwnedLabel : t.personalByodLabel}
                      </div>
                    </td>
                    <td style={{ padding: "14px 15px", color: "#5f6368", fontSize: "14px" }}>{d.os_version} ({d.device_type})</td>
                    <td style={{ padding: "14px 15px", fontFamily: "monospace", fontSize: "13px", color: "#3c4043" }}>
                      <div>{d.serial_number !== "N/A" ? `${t.serialImeiPrefix} ${d.serial_number}` : t.virtualAssetLabel}</div>
                    </td>
                    <td style={{ padding: "14px 15px" }}>
                      <span style={{ padding: "4px 8px", backgroundColor: d.approval_state === "APPROVED" ? "#e6f4ea" : "#fef7e0", color: d.approval_state === "APPROVED" ? "#137333" : "#b06000", borderRadius: "4px", fontWeight: "bold", fontSize: "12px", textTransform: "uppercase", border: `1px solid ${d.approval_state === "APPROVED" ? "#ceead6" : "#feefc3"}` }}>
                        {d.approval_state === "APPROVED" ? t.approvedStatus : d.approval_state === "PENDING_APPROVAL" ? t.pendingStatus : t.revokedStatus}
                      </span>
                    </td>
                    <td style={{ padding: "14px 15px", color: "#5f6368", fontSize: "13px" }}>{formatLastSync(d.last_sync_time)}</td>
                    <td style={{ padding: "14px 15px", textAlign: "center" }}>
                      {d.owner_type === "COMPANY" ? (
                        <span style={{ padding: "6px 12px", backgroundColor: "#e8f0fe", color: "#1a73e8", borderRadius: "4px", fontSize: "12px", fontWeight: "bold", display: "inline-block", border: "1px solid #d2e3fc" }}>
                          {t.immutableAnchorLabel}
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
      </main>

      {/* Revocation Confirmation Modal Overlay */}
      {showRevokeModal && (
        <div style={{ position: "fixed", top: 0, left: 0, width: "100vw", height: "100vh", backgroundColor: "rgba(0,0,0,0.5)", display: "flex", justifyContent: "center", alignItems: "center", zIndex: 9999 }}>
          <div style={{ backgroundColor: "#fff", padding: "30px", borderRadius: "8px", maxWidth: "500px", width: "90%", boxShadow: "0 4px 15px rgba(0,0,0,0.2)" }}>
            <div style={{ fontSize: "20px", fontWeight: "bold", color: "#d93025", marginBottom: "15px", display: "flex", alignItems: "center", gap: "10px" }}>
              {t.confirmRevocationTitle}
            </div>
            <p style={{ color: "#202124", fontSize: "15px", lineHeight: "1.5", marginBottom: "15px" }}>
              {t.confirmRevocationBody}
            </p>
            <div style={{ maxHeight: "150px", overflowY: "auto", backgroundColor: "#f1f3f4", padding: "12px", borderRadius: "6px", marginBottom: "20px", fontSize: "13px", fontFamily: "monospace", color: "#3c4043" }}>
              {revokeTarget.map((targetName, idx) => {
                const matchingDev = devices.find((d) => d.device_user_name === targetName);
                return (
                  <div key={idx} style={{ marginBottom: "6px" }}>
                    • {matchingDev ? `${matchingDev.model} (${t.serialImeiPrefix} ${matchingDev.serial_number})` : targetName}
                  </div>
                );
              })}
            </div>
            <p style={{ color: "#5f6368", fontSize: "13px", marginBottom: "25px" }}>
              {t.confirmRevocationWarning}
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "15px" }}>
              <button
                onClick={() => setShowRevokeModal(false)}
                disabled={isRevoking}
                style={{ padding: "10px 18px", backgroundColor: "#f1f3f4", color: "#3c4043", border: "none", borderRadius: "4px", cursor: "pointer", fontWeight: "bold", fontSize: "14px" }}
              >
                {t.cancelAction}
              </button>
              <button
                onClick={handleConfirmRevoke}
                disabled={isRevoking}
                style={{ padding: "10px 18px", backgroundColor: "#d93025", color: "white", border: "none", borderRadius: "4px", cursor: "pointer", fontWeight: "bold", fontSize: "14px" }}
              >
                {isRevoking ? t.revokingAction : t.yesRevokeAction}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
