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

import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  getMyDevices,
  approveDevice,
  revokeDevice,
  revokeDeviceBulk,
  checkIsAdmin,
  getPublicConfig,
  sendClientLog,
  getSessionWatchMetrics,
  syncSessionWatchInventory,
  attestBrowserSession,
  startOnboardingLease,
  verifySessionStatus,
  runLiveLoginSweep,
  generatePairingCode,
  verifyPairingCode,
  DeviceUserItem,
  SessionWatchMetricsResponse,
} from "../services/api";
import { GoogleLoginButton } from "../components/GoogleLoginButton";
import { getTranslator } from "../i18n/translations";

const renderPlatformIcon = (deviceType: string) => {
  const upper = (deviceType || "").toUpperCase();
  if (upper.includes("ANDROID") || upper.includes("IOS") || upper.includes("PHONE")) {
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M17 1.01L7 1c-1.1 0-2 .9-2 2v18c0 1.1.9 2 2 2h10c1.1 0 2-.9 2-2V3c0-1.1-.9-1.99-2-1.99zM17 19H7V5h10v14z" />
      </svg>
    );
  }
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M20 18c1.1 0 1.99-.9 1.99-2L22 6c0-1.1-.9-2-2-2H4c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2H0v2h24v-2h-4zM4 6h16v10H4V6z" />
    </svg>
  );
};

const detectBrowserPlatform = (): "CHROME_OS" | "MAC_OS" | "WINDOWS" | "ANDROID" | "IOS" | "UNKNOWN" => {
  if (typeof navigator === "undefined" || !navigator.userAgent) return "UNKNOWN";
  const ua = navigator.userAgent;
  if (ua.includes("CrOS")) return "CHROME_OS";
  if (ua.includes("iPhone") || ua.includes("iPad")) return "IOS";
  if (ua.includes("Android")) return "ANDROID";
  if (ua.includes("Macintosh") || ua.includes("Mac OS X")) return "MAC_OS";
  if (ua.includes("Windows")) return "WINDOWS";
  return "UNKNOWN";
};

const selectPlatformMatchedDevice = (list: DeviceUserItem[]): DeviceUserItem | undefined => {
  const platform = detectBrowserPlatform();
  if (platform === "CHROME_OS") {
    return (
      list.find(
        (d) =>
          (d.owner_type === "COMPANY" || (d.device_type || "").toUpperCase().includes("CHROME")) &&
          d.approval_state === "APPROVED" &&
          d.serial_number &&
          d.serial_number !== "N/A"
      ) ||
      list.find(
        (d) =>
          (d.owner_type === "COMPANY" || (d.device_type || "").toUpperCase().includes("CHROME")) &&
          d.approval_state === "APPROVED"
      )
    );
  }
  if (platform !== "UNKNOWN") {
    const matchesPlatform = (d: DeviceUserItem) => {
      const dtype = (d.device_type || "").toUpperCase();
      const osVer = (d.os_version || "").toUpperCase();
      if (platform === "MAC_OS") return dtype.includes("MAC") || osVer.includes("MAC");
      if (platform === "WINDOWS") return dtype.includes("WINDOWS") || osVer.includes("WINDOWS");
      if (platform === "ANDROID") return dtype.includes("ANDROID") || osVer.includes("ANDROID");
      if (platform === "IOS") return dtype.includes("IOS") || osVer.includes("IOS");
      return false;
    };
    return (
      list.find(
        (d) =>
          d.approval_state === "APPROVED" &&
          d.serial_number &&
          d.serial_number !== "N/A" &&
          matchesPlatform(d)
      ) || list.find((d) => d.approval_state === "APPROVED" && matchesPlatform(d))
    );
  }
  return (
    list.find((d) => d.owner_type === "COMPANY" && d.serial_number && d.serial_number !== "N/A") ||
    list.find((d) => d.approval_state === "APPROVED" && d.serial_number && d.serial_number !== "N/A") ||
    list.find((d) => d.approval_state === "APPROVED")
  );
};

export const Dashboard: React.FC = () => {
  const [userEmail, setUserEmail] = useState(() => localStorage.getItem("userEmail") || "");
  const [message, setMessage] = useState("");
  const [authToken, setAuthToken] = useState(() => localStorage.getItem("googleIdToken") || "");
  const [locale, setLocale] = useState(() => localStorage.getItem("userLocale") || "en");
  const [enforcementMode, setEnforcementMode] = useState<string>("DISABLED");
  const [sessionWatchEnabled, setSessionWatchEnabled] = useState<boolean>(false);
  const [cookieThreatDetectionEnabled, setCookieThreatDetectionEnabled] = useState<boolean>(false);
  const [caaEnforcementEnabled, setCaaEnforcementEnabled] = useState<boolean>(false);
  const [enableTrustChaining, setEnableTrustChaining] = useState<boolean>(false);
  const [generatedPairingCode, setGeneratedPairingCode] = useState<string>("");
  const [pairingCodeGenerating, setPairingCodeGenerating] = useState<boolean>(false);
  const [redeemCodeInput, setRedeemCodeInput] = useState<string>("");
  const [redeemCodeLoading, setRedeemCodeLoading] = useState<boolean>(false);
  const [sessionWatchData, setSessionWatchData] = useState<SessionWatchMetricsResponse | null>(null);
  const [sessionWatchLoading, setSessionWatchLoading] = useState(false);
  const autoAttestedForUserRef = useRef<string>("");
  const t = getTranslator(locale);

  const loadSessionWatchStatus = useCallback(() => {
    if (typeof getSessionWatchMetrics !== "function") return;
    const p = getSessionWatchMetrics();
    if (p && typeof p.then === "function") {
      p.then((res) => {
        setSessionWatchData(res);
        if (res?.enforcement_mode) {
          setEnforcementMode(res.enforcement_mode);
        }
        if (typeof res?.session_watch_enabled === "boolean") {
          setSessionWatchEnabled(res.session_watch_enabled);
        } else if (res?.enforcement_mode) {
          setSessionWatchEnabled(res.enforcement_mode === "SESSION_WATCH" || res.enforcement_mode === "BOTH");
        }
        if (typeof res?.cookie_threat_detection_enabled === "boolean") {
          setCookieThreatDetectionEnabled(res.cookie_threat_detection_enabled);
        } else if (res?.enforcement_mode) {
          setCookieThreatDetectionEnabled(res.enforcement_mode === "COOKIE_SENTINEL");
        }
        if (typeof res?.caa_enforcement_enabled === "boolean") {
          setCaaEnforcementEnabled(res.caa_enforcement_enabled);
        } else if (res?.enforcement_mode) {
          setCaaEnforcementEnabled(res.enforcement_mode === "CAA" || res.enforcement_mode === "BOTH");
        }
      }).catch(() => {});
    }
  }, []);

  useEffect(() => {
    if (typeof getPublicConfig === "function") {
      const p = getPublicConfig();
      if (p && typeof p.then === "function") {
        p.then((data) => {
          if (data?.enforcement_mode) {
            setEnforcementMode(data.enforcement_mode);
          }
          if (typeof data?.session_watch_enabled === "boolean") {
            setSessionWatchEnabled(data.session_watch_enabled);
          } else if (data?.enforcement_mode) {
            setSessionWatchEnabled(data.enforcement_mode === "SESSION_WATCH" || data.enforcement_mode === "BOTH");
          }
          if (typeof data?.cookie_threat_detection_enabled === "boolean") {
            setCookieThreatDetectionEnabled(data.cookie_threat_detection_enabled);
          } else if (data?.enforcement_mode) {
            setCookieThreatDetectionEnabled(data.enforcement_mode === "COOKIE_SENTINEL");
          }
          if (typeof data?.caa_enforcement_enabled === "boolean") {
            setCaaEnforcementEnabled(data.caa_enforcement_enabled);
          } else if (data?.enforcement_mode) {
            setCaaEnforcementEnabled(data.enforcement_mode === "CAA" || data.enforcement_mode === "BOTH");
          }
          if (typeof data?.enable_trust_chaining === "boolean") {
            setEnableTrustChaining(data.enable_trust_chaining);
          }
          if (data?.default_locale) {
            const hasManualOverride = sessionStorage.getItem("userLocaleOverride") === "true";
            if (!hasManualOverride) {
              setLocale(data.default_locale);
              localStorage.setItem("userLocale", data.default_locale);
            }
          } else if (!localStorage.getItem("userLocale")) {
            const browserLang = navigator.language?.slice(0, 2);
            setLocale(
              ["en", "es", "fr", "ja", "de", "pt", "zh", "it", "ko", "ar", "hi", "nl", "pl", "sv", "tr"].includes(browserLang)
                ? browserLang
                : "en"
            );
          }
        }).catch(() => {});
      }
    }
    loadSessionWatchStatus();
  }, [loadSessionWatchStatus]);

  // Proactively renew Google Sign-In ID token before its 60-minute expiration
  useEffect(() => {
    if (!authToken || !userEmail) return;
    let timerId: ReturnType<typeof setTimeout> | null = null;
    try {
      const parts = authToken.split(".");
      if (parts.length === 3) {
        const payload = JSON.parse(atob(parts[1]));
        if (payload?.exp) {
          const expiresAtMs = payload.exp * 1000;
          const refreshDelayMs = Math.max(30000, expiresAtMs - Date.now() - 5 * 60 * 1000);
          timerId = setTimeout(() => {
            const googleAccounts = (window as any).google?.accounts?.id;
            if (googleAccounts && typeof googleAccounts.prompt === "function") {
              googleAccounts.prompt();
            }
          }, refreshDelayMs);
        }
      }
    } catch (_) {
      // Ignore non-JWT mock tokens in tests
    }
    return () => {
      if (timerId) clearTimeout(timerId);
    };
  }, [authToken, userEmail]);

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
      if (typeof sendClientLog === "function") {
        sendClientLog("INFO", "LOAD_DEVICES_START", `Requesting /api/devices/my-devices for ${userEmail}`);
      }
      getMyDevices()
        .then((data) => {
          const list = Array.isArray(data) ? data : [];
          setDevices(list);
          setLoadingDevices(false);

          // Auto-attest current browser session ONLY if the current browser OS matches an approved/company device
          // and the user has no unapproved PENDING_APPROVAL BYOD devices
          const hasPending = list.some((d) => d.approval_state === "PENDING_APPROVAL");
          const trustedCandidate = selectPlatformMatchedDevice(list);
          if (
            !hasPending &&
            trustedCandidate &&
            autoAttestedForUserRef.current !== userEmail &&
            typeof attestBrowserSession === "function"
          ) {
            autoAttestedForUserRef.current = userEmail;
            const candidateSerial =
              trustedCandidate.serial_number && trustedCandidate.serial_number !== "N/A"
                ? trustedCandidate.serial_number
                : trustedCandidate.device_user_name;
            const pAttest = attestBrowserSession(userEmail, candidateSerial);
            if (pAttest && typeof pAttest.then === "function") {
              pAttest.then(() => loadSessionWatchStatus()).catch(() => {});
            }
          } else if (hasPending) {
            loadSessionWatchStatus();
          }

          if (typeof sendClientLog === "function") {
            if (list.length === 0) {
              sendClientLog(
                "WARNING",
                "LOAD_DEVICES_EMPTY",
                `Portal UI received 0 devices for ${userEmail}`,
                { count: 0 }
              );
            } else {
              sendClientLog(
                "INFO",
                "LOAD_DEVICES_SUCCESS",
                `Portal UI rendered ${list.length} device(s) for ${userEmail}`,
                {
                  count: list.length,
                  devices: list.map((d) => ({
                    device_user_name: d.device_user_name,
                    device_type: d.device_type,
                    model: d.device_type ? `${d.model} (${d.device_type})` : d.model,
                    approval_state: d.approval_state,
                    owner_type: d.owner_type,
                  })),
                }
              );
            }
          }
        })
        .catch((err) => {
          const errMsg = `Failed to load approved devices: ${err.message}`;
          setDeviceError(errMsg);
          setLoadingDevices(false);
          if (typeof sendClientLog === "function") {
            sendClientLog("ERROR", "LOAD_DEVICES_ERROR", errMsg, {
              error: err?.message || String(err),
            });
          }
        });
    } else {
      setDevices([]);
    }
  }, [userEmail, loadSessionWatchStatus]);

  useEffect(() => {
    loadDevices();
    loadSessionWatchStatus();
    if (userEmail) {
      checkIsAdmin().then(setIsAdmin);
    } else {
      setIsAdmin(false);
    }
  }, [userEmail, authToken, loadDevices, loadSessionWatchStatus]);

  useEffect(() => {
    if (!userEmail || !sessionWatchEnabled || typeof verifySessionStatus !== "function") {
      return;
    }
    const checkStatus = () => {
      const p = verifySessionStatus();
      if (p && typeof p.catch === "function") {
        p.catch(() => {});
      }
    };
    checkStatus();
    const intervalId = setInterval(checkStatus, 8000);
    return () => clearInterval(intervalId);
  }, [userEmail, authToken, sessionWatchEnabled]);

  const handleLoginSuccess = (email: string, token: string) => {
    setUserEmail(email);
    setAuthToken(token);
    setMessage(`Successfully authenticated with Google Sign-In as ${email}`);
  };

  const handleApprove = async (name: string) => {
    setMessage("");
    sendClientLog("INFO", "APPROVE_DEVICE_START", `User initiated approval for ${name}`, {
      device_user_name: name,
    });
    try {
      await approveDevice(name);
      setMessage(t.deviceApprovedSuccess);
      setDevices((prev) =>
        prev.map((d) => (d.device_user_name === name ? { ...d, approval_state: "APPROVED" } : d))
      );
      loadSessionWatchStatus();
      sendClientLog("INFO", "APPROVE_DEVICE_SUCCESS", `Device approved successfully: ${name}`, {
        device_user_name: name,
      });
    } catch (e: any) {
      const errMsg = `Failed to approve device: ${e.message}`;
      setMessage(errMsg);
      sendClientLog("ERROR", "APPROVE_DEVICE_ERROR", errMsg, {
        device_user_name: name,
        error: e?.message || String(e),
      });
    }
  };

  const handleStartOnboardingLease = async () => {
    if (!userEmail) return;
    setSessionWatchLoading(true);
    setMessage("");
    try {
      const res = await startOnboardingLease();
      setMessage(res.message);
      loadSessionWatchStatus();
    } catch (e: any) {
      setMessage(`Failed to start personal device onboarding pass: ${e.message}`);
    } finally {
      setSessionWatchLoading(false);
    }
  };

  const handleGeneratePairingCode = async () => {
    if (!userEmail || typeof generatePairingCode !== "function") return;
    setPairingCodeGenerating(true);
    setMessage("");
    try {
      const res = await generatePairingCode();
      setGeneratedPairingCode(res.pairing_code);
      setMessage(
        `Generated 6-digit pairing code ${res.pairing_code} (valid for 24 hours). Redeem this code on your secondary device to start your 15-minute grace window and approve it.`
      );
    } catch (e: any) {
      setMessage(`Failed to generate pairing code: ${e.message}`);
    } finally {
      setPairingCodeGenerating(false);
    }
  };

  const handleRedeemPairingCode = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const cleaned = (redeemCodeInput || "").replace(/\s+/g, "").trim();
    if (!cleaned || typeof verifyPairingCode !== "function") return;
    setRedeemCodeLoading(true);
    setMessage("");
    try {
      const res = await verifyPairingCode(cleaned);
      setMessage(
        res.message ||
          (res.status === "LEASE_ACTIVATED"
            ? "Pairing code verified! Your 15-minute Onboarding Grace Pass is now active—sign in with Google to complete approval."
            : "Secondary device approved via 6-digit pairing code!")
      );
      if (res.status === "SUCCESS") {
        setRedeemCodeInput("");
        if (userEmail) {
          loadDevices();
        }
      }
      loadSessionWatchStatus();
    } catch (err: any) {
      setMessage(`Failed to redeem pairing code: ${err.message}`);
    } finally {
      setRedeemCodeLoading(false);
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
    sendClientLog("INFO", "REVOKE_DEVICE_START", `User initiated revocation for ${revokeTarget.length} device(s)`, {
      device_user_names: revokeTarget,
    });

    try {
      if (revokeTarget.length === 1) {
        await revokeDevice(revokeTarget[0]);
      } else {
        await revokeDeviceBulk(revokeTarget);
      }

      setDevices((prev) =>
        prev.map((d) => (revokeTarget.includes(d.device_user_name) ? { ...d, approval_state: "BLOCKED" } : d))
      );
      setMessage(`Successfully revoked approval for ${revokeTarget.length} device(s).`);
      sendClientLog("INFO", "REVOKE_DEVICE_SUCCESS", `Successfully revoked ${revokeTarget.length} device(s)`, {
        device_user_names: revokeTarget,
      });
    } catch (e: any) {
      const errMsg = `Failed to revoke device(s): ${e.message}`;
      setMessage(errMsg);
      sendClientLog("ERROR", "REVOKE_DEVICE_ERROR", errMsg, {
        device_user_names: revokeTarget,
        error: e?.message || String(e),
      });
    }

    setIsRevoking(false);
    setShowRevokeModal(false);
    setSelectedDevices([]);
    setRevokeTarget([]);
  };

  const personalDevices = devices.filter((d) => d.owner_type !== "COMPANY");
  const companyDevices = devices.filter((d) => d.owner_type === "COMPANY");
  const approvedByodCount = personalDevices.filter((d) => d.approval_state === "APPROVED").length;
  const pendingByodCount = personalDevices.filter((d) => d.approval_state === "PENDING_APPROVAL").length;
  const activeUserLease = sessionWatchData?.active_onboarding_leases?.find(
    (l) => l.user_email.toLowerCase() === userEmail.toLowerCase()
  );

  const handleSelectAll = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.checked) {
      const revokable = personalDevices
        .filter((d) => d.approval_state === "APPROVED")
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
      return new Intl.DateTimeFormat(locale || "en", {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }).format(d);
    } catch (e) {
      return isoStr;
    }
  };

  return (
    <div className="dtg-shell" lang={locale} dir={locale === "ar" ? "rtl" : "ltr"}>
      {/* Google Workspace Top Navigation App Bar */}
      <header className="dtg-header">
        <div className="dtg-header-inner">
          <div className="dtg-brand">
            <div className="dtg-brand-icon" aria-hidden="true">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M12 2L3 6V11C3 16.55 6.84 21.74 12 23C17.16 21.74 21 16.55 21 11V6L12 2Z" fill="#1a73e8" />
                <path
                  d="M12 6V11H17C16.47 14.19 14.52 16.8 12 17.65V23C17.16 21.74 21 16.55 21 11H12V6Z"
                  fill="#4285F4"
                  opacity="0.8"
                />
                <path d="M10.5 15.5L6.5 11.5L7.91 10.09L10.5 12.67L16.09 7.09L17.5 8.5L10.5 15.5Z" fill="#ffffff" />
              </svg>
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
                <h1 className="dtg-brand-title">{t.portalTitle}</h1>
                {(sessionWatchEnabled || cookieThreatDetectionEnabled) ? (
                  <span
                    data-testid="enforcement-mode-badge"
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "5px",
                      padding: "3px 10px",
                      borderRadius: "999px",
                      fontSize: "11px",
                      fontWeight: 700,
                      letterSpacing: "0.02em",
                      backgroundColor: sessionWatchEnabled ? "#e8f0fe" : "#e6f4ea",
                      color: sessionWatchEnabled ? "#1967d2" : "#137333",
                      border: sessionWatchEnabled ? "1px solid #aecbfa" : "1px solid #ceead6",
                    }}
                  >
                    {sessionWatchEnabled
                      ? t.enforcementBadgeSessionWatch
                      : t.enforcementBadgeCookieSentinel}
                  </span>
                ) : isAdmin ? (
                  <a
                    href="#/admin"
                    data-testid="enforcement-standby-badge"
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "5px",
                      padding: "3px 10px",
                      borderRadius: "999px",
                      fontSize: "11px",
                      fontWeight: 700,
                      letterSpacing: "0.02em",
                      backgroundColor: "#f1f3f4",
                      color: "#5f6368",
                      border: "1px solid #dadce0",
                      textDecoration: "none",
                    }}
                    title="New install default: Session Management and Stolen Cookie Threat Detection are disabled until configured in Admin Configurations"
                  >
                    {t.enforcementStandbyBadge}
                  </a>
                ) : null}
              </div>
              <div className="dtg-brand-subtitle">{t.subtitle}</div>
            </div>
          </div>

          <div className="dtg-header-actions">
            <select
              aria-label="Language Selector"
              value={locale}
              onChange={(e) => {
                setLocale(e.target.value);
                localStorage.setItem("userLocale", e.target.value);
                sessionStorage.setItem("userLocaleOverride", "true");
              }}
              className="dtg-select"
            >
              <option value="en">English (en)</option>
              <option value="es">Español (es)</option>
              <option value="fr">Français (fr)</option>
              <option value="ja">日本語 (ja)</option>
              <option value="de">Deutsch (de)</option>
              <option value="pt">Português (Brasil) (pt-BR)</option>
              <option value="zh">简体中文 (zh)</option>
              <option value="it">Italiano (it)</option>
              <option value="ko">한국어 (ko)</option>
              <option value="ar">العربية (ar)</option>
              <option value="hi">हिन्दी (hi)</option>
              <option value="nl">Nederlands (nl)</option>
              <option value="pl">Polski (pl)</option>
              <option value="sv">Svenska (sv)</option>
              <option value="tr">Türkçe (tr)</option>
            </select>

            {isAdmin && (
              <a href="#/admin" className="dtg-btn dtg-btn-outline">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                  <path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z" />
                </svg>
                {t.adminConfigTab}
              </a>
            )}
          </div>
        </div>
      </header>

      <main className="dtg-main">
        {/* Google Workspace Authentication Surface Card */}
        <div className="dtg-card" style={{ padding: "clamp(20px, 3.2vw, 28px)" }}>
          <div className="dtg-card-header" style={{ marginBottom: userEmail ? "16px" : "16px" }}>
            <div>
              <h3 className="dtg-card-title" style={{ marginBottom: "6px" }}>{t.googleAuthTitle}</h3>
              <p className="dtg-card-desc" style={{ marginTop: "6px", lineHeight: 1.6 }}>{t.signInPrompt}</p>
            </div>
          </div>

          {!userEmail ? (
            <>
              <GoogleLoginButton onLoginSuccess={handleLoginSuccess} />
              <div className="dtg-steps-grid">
                <div className="dtg-step-item">
                  <div className="dtg-step-num">1</div>
                  <div>
                    <div className="dtg-step-title">{t.step1Title}</div>
                    <div className="dtg-step-text">{t.step1Desc}</div>
                  </div>
                </div>
                <div className="dtg-step-item">
                  <div className="dtg-step-num">2</div>
                  <div>
                    <div className="dtg-step-title">{t.step2Title}</div>
                    <div className="dtg-step-text">{t.step2Desc}</div>
                  </div>
                </div>
                <div className="dtg-step-item">
                  <div className="dtg-step-num">3</div>
                  <div>
                    <div className="dtg-step-title">{t.step3Title}</div>
                    <div className="dtg-step-text">{t.step3Desc}</div>
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div className="dtg-session-bar">
              <div className="dtg-user-profile">
                <div className="dtg-avatar" aria-hidden="true">
                  {userEmail.charAt(0).toUpperCase()}
                </div>
                <div className="dtg-user-meta">
                  <span className="dtg-user-label">{t.signedInAs}</span>
                  <span className="dtg-user-email">{userEmail}</span>
                </div>
              </div>
              <div className="dtg-session-actions">
                <button
                  onClick={loadDevices}
                  disabled={loadingDevices}
                  aria-label={t.refreshDevices}
                  className="dtg-btn dtg-btn-outline"
                  title={t.refreshDevices}
                >
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="currentColor"
                    style={{ animation: loadingDevices ? "dtg-spin 1s linear infinite" : "none" }}
                    aria-hidden="true"
                  >
                    <path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z" />
                  </svg>
                  {t.refreshDevices}
                </button>
                <button
                  onClick={() => {
                    localStorage.removeItem("userEmail");
                    localStorage.removeItem("googleIdToken");
                    setUserEmail("");
                    setAuthToken("");
                    setDevices([]);
                    setIsAdmin(false);
                    setGeneratedPairingCode("");
                    setMessage(t.signedOutSuccess);
                  }}
                  className="dtg-btn dtg-btn-neutral"
                >
                  {t.signOut}
                </button>
              </div>
            </div>
          )}

          {/* 6-Digit Pairing Code Redemption Bar (Works Pre-Login, Post-SignOut, or While Signed In) */}
          <form
            onSubmit={handleRedeemPairingCode}
            data-testid="redeem-pairing-code-box"
            style={{
              marginTop: "16px",
              paddingTop: "14px",
              borderTop: "1px solid var(--dtg-border-subtle)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "12px",
            }}
          >
            <div style={{ flex: "1 1 320px" }}>
              <div style={{ fontSize: "13px", fontWeight: 700, color: "var(--dtg-text)", marginBottom: "2px" }}>
                🔑 Have a 6-Digit Pairing Code? (Valid 24 Hours)
              </div>
              <div style={{ fontSize: "12px", color: "var(--dtg-text-secondary)", lineHeight: 1.45 }}>
                Generated a pairing code on your approved Chromebook? Enter it here{" "}
                <b>before signing in</b> (to start your 15m grace window without getting signed out) or{" "}
                <b>after signing in</b> to immediately authorize this secondary device.
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
              <input
                type="text"
                inputMode="numeric"
                maxLength={7}
                placeholder="6-digit code"
                aria-label="6-Digit Pairing Code"
                data-testid="redeem-pairing-code-input"
                value={redeemCodeInput}
                onChange={(e) => setRedeemCodeInput(e.target.value)}
                className="dtg-input"
                style={{
                  width: "140px",
                  padding: "7px 10px",
                  fontSize: "14px",
                  fontFamily: "monospace",
                  fontWeight: 700,
                  letterSpacing: "0.1em",
                  textAlign: "center",
                }}
              />
              <button
                type="submit"
                data-testid="redeem-pairing-code-submit"
                disabled={redeemCodeLoading || !redeemCodeInput.trim()}
                className="dtg-btn dtg-btn-primary"
                style={{ padding: "8px 14px", fontSize: "13px" }}
              >
                {redeemCodeLoading ? "Verifying..." : "Redeem & Authorize"}
              </button>
            </div>
          </form>
        </div>

        {/* Summary Metric Cards when signed in and devices loaded */}
        {userEmail && !loadingDevices && !deviceError && devices.length > 0 && (
          <div className="dtg-stats-grid" aria-label="Device Inventory Summary">
            <div className="dtg-stat-card">
              <div>
                <div className="dtg-stat-label">{t.totalRegisteredLabel}</div>
                <div className="dtg-stat-value">{devices.length}</div>
              </div>
              <div
                className="dtg-stat-icon"
                style={{ backgroundColor: "var(--dtg-primary-soft)", color: "var(--dtg-primary)" }}
                aria-hidden="true"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M4 6h18V4H4c-1.1 0-2 .9-2 2v11H0v3h14v-3H4V6zm19 2h-6c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h6c.55 0 1-.45 1-1V9c0-.55-.45-1-1-1zm-1 9h-4v-7h4v7z" />
                </svg>
              </div>
            </div>

            <div className="dtg-stat-card">
              <div>
                <div className="dtg-stat-label">{t.approvedStatus} (BYOD)</div>
                <div className="dtg-stat-value" style={{ color: "var(--dtg-success)" }}>
                  {approvedByodCount}
                </div>
              </div>
              <div
                className="dtg-stat-icon"
                style={{ backgroundColor: "var(--dtg-success-bg)", color: "var(--dtg-success)" }}
                aria-hidden="true"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" />
                </svg>
              </div>
            </div>

            <div className={`dtg-stat-card ${pendingByodCount > 0 ? "dtg-stat-pending-active" : ""}`}>
              <div>
                <div className="dtg-stat-label">{t.pendingStatus}</div>
                <div
                  className="dtg-stat-value"
                  style={{ color: pendingByodCount > 0 ? "var(--dtg-warning)" : "var(--dtg-text)" }}
                >
                  {pendingByodCount}
                </div>
              </div>
              <div
                className="dtg-stat-icon"
                style={{ backgroundColor: "var(--dtg-warning-bg)", color: "var(--dtg-warning)" }}
                aria-hidden="true"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z" />
                </svg>
              </div>
            </div>

            <div className="dtg-stat-card">
              <div>
                <div className="dtg-stat-label">{t.companyDevicesTitle}</div>
                <div className="dtg-stat-value" style={{ color: "var(--dtg-primary)" }}>
                  {companyDevices.length}
                </div>
              </div>
              <div
                className="dtg-stat-icon"
                style={{ backgroundColor: "var(--dtg-primary-soft)", color: "var(--dtg-primary)" }}
                aria-hidden="true"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z" />
                </svg>
              </div>
            </div>
          </div>
        )}

        {message && (
          <div
            role="status"
            aria-live="polite"
            className={`dtg-alert ${
              message.toLowerCase().includes("failed") || message.toLowerCase().includes("error")
                ? "dtg-alert-error"
                : "dtg-alert-info"
            }`}
          >
            <span>{message}</span>
          </div>
        )}

        {activeUserLease && (
          <div
            style={{
              marginBottom: "16px",
              padding: "10px 14px",
              borderRadius: "8px",
              backgroundColor: "var(--dtg-success-bg)",
              border: "1px solid var(--dtg-success-border)",
              color: "var(--dtg-success)",
              fontSize: "13px",
              fontWeight: 600,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: "10px",
              flexWrap: "wrap",
            }}
          >
            <span>
              {t.onboardingPassActiveBanner.replace(
                "{minutes}",
                String(Math.max(1, Math.ceil(activeUserLease.remaining_seconds / 60)))
              )}
            </span>
          </div>
        )}

        {generatedPairingCode && (
          <div
            data-testid="generated-pairing-code-card"
            style={{
              marginBottom: "16px",
              padding: "14px 16px",
              borderRadius: "8px",
              backgroundColor: "#e8f0fe",
              border: "1.5px solid #aecbfa",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "12px",
            }}
          >
            <div>
              <div style={{ fontSize: "13px", fontWeight: 700, color: "#1967d2", marginBottom: "4px" }}>
                🔑 6-Digit Pairing Code (Valid for 24 Hours • Single-Use)
              </div>
              <div style={{ fontSize: "12px", color: "#3c4043", lineHeight: 1.5 }}>
                Enter this code on your secondary device within 24 hours. Redeeming the code automatically activates your 15-minute Onboarding Grace Pass and authorizes the device without IT intervention.
              </div>
            </div>
            <div
              data-testid="generated-pairing-code-value"
              style={{
                fontFamily: "monospace",
                fontSize: "22px",
                fontWeight: 800,
                letterSpacing: "0.18em",
                padding: "8px 16px",
                borderRadius: "8px",
                backgroundColor: "#ffffff",
                color: "#1967d2",
                border: "1px solid #aecbfa",
              }}
            >
              {generatedPairingCode}
            </div>
          </div>
        )}

        {!userEmail ? (
          <div role="status" className="dtg-alert dtg-alert-warning">
            <span>{t.signInPrompt}</span>
          </div>
        ) : loadingDevices ? (
          <div role="status" aria-live="polite" className="dtg-empty-state">
            <div className="dtg-spinner" />
            <div style={{ fontWeight: 600, color: "var(--dtg-text)", fontSize: "16px", marginBottom: "6px" }}>
              {t.loadingDevices}
            </div>
            <div style={{ color: "var(--dtg-text-secondary)", fontSize: "13px" }}>
              {t.verifyingInventoryFor} <b>{userEmail}</b>.
            </div>
          </div>
        ) : deviceError ? (
          <div role="alert" className="dtg-alert dtg-alert-error">
            <span>{deviceError}</span>
            <button
              onClick={loadDevices}
              disabled={loadingDevices}
              className="dtg-btn dtg-btn-danger-outline"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z" />
              </svg>
              {t.refreshDevices}
            </button>
          </div>
        ) : devices.length === 0 ? (
          <div role="status" className="dtg-empty-state">
            <div style={{ fontSize: "16px", fontWeight: 600, marginBottom: "8px", color: "var(--dtg-text)" }}>
              {t.noApprovedDevices}
            </div>
            <div style={{ fontSize: "14px", marginBottom: "18px", color: "var(--dtg-text-secondary)" }}>
              {t.noDevicesFoundFor} <b>{userEmail}</b>.
            </div>
            <button
              onClick={loadDevices}
              disabled={loadingDevices}
              className="dtg-btn dtg-btn-primary"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="currentColor"
                style={{ animation: loadingDevices ? "dtg-spin 1s linear infinite" : "none" }}
                aria-hidden="true"
              >
                <path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z" />
              </svg>
              {t.refreshDevices}
            </button>
          </div>
        ) : (
          <>
            {/* Section 1: Personal BYOD Devices (Self-Service Approvals) */}
            <section className="dtg-section">
              <div className="dtg-section-header">
                <div>
                  <h2 className="dtg-section-title">
                    {t.personalDevicesTitle}
                    <span className="dtg-section-count">{personalDevices.length}</span>
                  </h2>
                  <div className="dtg-section-subtitle">{t.personalDevicesSubtitle}</div>
                </div>
                <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
                  {enableTrustChaining && (
                    <button
                      type="button"
                      data-testid="generate-pairing-code-btn"
                      onClick={handleGeneratePairingCode}
                      disabled={pairingCodeGenerating}
                      className="dtg-btn dtg-btn-primary"
                      title="Generate a 6-digit pairing code (valid for 24 hours) to authorize a secondary device"
                    >
                      🔑 {pairingCodeGenerating ? "Generating..." : "Generate 6-Digit Pairing Code (24h)"}
                    </button>
                  )}
                  {sessionWatchEnabled && (
                    <button
                      type="button"
                      onClick={handleStartOnboardingLease}
                      disabled={sessionWatchLoading}
                      className="dtg-btn dtg-btn-success"
                      title={t.addPersonalDeviceTooltip}
                    >
                      {t.addPersonalDeviceBtn}
                    </button>
                  )}
                  <button
                    onClick={loadDevices}
                    disabled={loadingDevices}
                    aria-label={t.refreshDevices}
                    className="dtg-btn dtg-btn-outline"
                    title={t.refreshDevices}
                  >
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="currentColor"
                      style={{ animation: loadingDevices ? "dtg-spin 1s linear infinite" : "none" }}
                      aria-hidden="true"
                    >
                      <path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z" />
                    </svg>
                    {t.refreshDevices}
                  </button>
                  {selectedDevices.length > 0 && (
                    <button
                      onClick={() => initiateRevoke(selectedDevices)}
                      className="dtg-btn dtg-btn-danger"
                    >
                      ✕ {t.bulkRevokeSelected} ({selectedDevices.length})
                    </button>
                  )}
                </div>
              </div>

              {personalDevices.length === 0 ? (
                <div role="status" className="dtg-empty-state" style={{ padding: "24px 16px" }}>
                  <div style={{ fontSize: "14px", color: "var(--dtg-text-secondary)" }}>{t.noPersonalDevices}</div>
                </div>
              ) : (
                <div className="dtg-table-wrap">
                  <table aria-label="Personal BYOD Devices Table" className="dtg-table">
                    <thead>
                      <tr>
                        <th scope="col" style={{ width: "44px", textAlign: "center" }}>
                          <input
                            type="checkbox"
                            aria-label="Select all eligible personal devices"
                            onChange={handleSelectAll}
                            checked={
                              approvedByodCount > 0 &&
                              selectedDevices.length === approvedByodCount
                            }
                          />
                        </th>
                        <th scope="col">{t.deviceHeader}</th>
                        <th scope="col">{t.osHeader}</th>
                        <th scope="col">{t.idHeader}</th>
                        <th scope="col">{t.statusHeader}</th>
                        <th scope="col">{t.lastSyncHeader}</th>
                        <th scope="col" style={{ textAlign: "center" }}>
                          {t.actionsHeader}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {personalDevices.map((d, i) => {
                        const isRevokable = d.approval_state === "APPROVED";
                        const isPending = d.approval_state === "PENDING_APPROVAL";
                        const isSelected = selectedDevices.includes(d.device_user_name);
                        const rowClass = isSelected
                          ? "dtg-row-selected"
                          : isPending
                          ? "dtg-row-pending"
                          : "";
                        const badgeClass =
                          d.approval_state === "APPROVED"
                            ? "dtg-badge dtg-badge-approved"
                            : isPending
                            ? "dtg-badge dtg-badge-pending"
                            : "dtg-badge dtg-badge-revoked";

                        return (
                          <tr key={i} className={rowClass}>
                            <td
                              className="dtg-cell-checkbox"
                              data-label="Select"
                              style={{ textAlign: "center" }}
                            >
                              <input
                                type="checkbox"
                                aria-label={`Select device ${d.model}`}
                                checked={isSelected}
                                onChange={() => handleSelectSingle(d.device_user_name)}
                                disabled={!isRevokable}
                              />
                            </td>
                            <td className="dtg-cell-device" data-label={t.deviceHeader}>
                              <div className="dtg-device-cell">
                                <div className="dtg-platform-icon">{renderPlatformIcon(d.device_type)}</div>
                                <div>
                                  <div className="dtg-device-model">{d.model}</div>
                                  <div
                                    className="dtg-device-owner-tag"
                                    style={{ color: "var(--dtg-text-secondary)" }}
                                  >
                                    {t.personalByodLabel}
                                  </div>
                                </div>
                              </div>
                            </td>
                            <td data-label={t.osHeader} style={{ color: "var(--dtg-text-secondary)" }}>
                              {d.os_version} ({d.device_type})
                            </td>
                            <td data-label={t.idHeader}>
                              <span className="dtg-serial-chip">
                                {d.serial_number !== "N/A"
                                  ? `${t.serialImeiPrefix} ${d.serial_number}`
                                  : t.virtualAssetLabel}
                              </span>
                            </td>
                            <td data-label={t.statusHeader}>
                              <span className={badgeClass}>
                                <span className="dtg-badge-dot" />
                                {d.approval_state === "APPROVED"
                                  ? t.approvedStatus
                                  : isPending
                                  ? t.pendingStatus
                                  : t.revokedStatus}
                              </span>
                            </td>
                            <td
                              data-label={t.lastSyncHeader}
                              style={{ color: "var(--dtg-text-secondary)", fontSize: "13px" }}
                            >
                              {formatLastSync(d.last_sync_time)}
                            </td>
                            <td
                              className="dtg-cell-actions"
                              data-label={t.actionsHeader}
                              style={{ textAlign: "center" }}
                            >
                              {d.approval_state === "APPROVED" ? (
                                <button
                                  onClick={() => initiateRevoke([d.device_user_name])}
                                  className="dtg-btn dtg-btn-danger"
                                >
                                  ✕ {t.revokeAction}
                                </button>
                              ) : (
                                <button
                                  onClick={() => handleApprove(d.device_user_name)}
                                  className="dtg-btn dtg-btn-success"
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
                </div>
              )}
            </section>

            {/* Section 2: Company-Owned Devices (Automatic Trust Anchors - Read-Only) */}
            {companyDevices.length > 0 && (
              <section className="dtg-section">
                <div className="dtg-section-header">
                  <div>
                    <h2 className="dtg-section-title">
                      {t.companyDevicesTitle}
                      <span className="dtg-section-count">{companyDevices.length}</span>
                    </h2>
                    <div className="dtg-section-subtitle">{t.companyDevicesSubtitle}</div>
                  </div>
                </div>

                <div className="dtg-table-wrap">
                  <table aria-label="Company-Owned Devices Table" className="dtg-table">
                    <thead>
                      <tr>
                        <th scope="col">{t.deviceHeader}</th>
                        <th scope="col">{t.osHeader}</th>
                        <th scope="col">{t.idHeader}</th>
                        <th scope="col">{t.statusHeader}</th>
                        <th scope="col">{t.lastSyncHeader}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {companyDevices.map((d, i) => (
                        <tr key={i}>
                          <td className="dtg-cell-device" data-label={t.deviceHeader}>
                            <div className="dtg-device-cell">
                              <div className="dtg-platform-icon">{renderPlatformIcon(d.device_type)}</div>
                              <div>
                                <div className="dtg-device-model">{d.model}</div>
                                <div
                                  className="dtg-device-owner-tag"
                                  style={{ color: "var(--dtg-primary)" }}
                                >
                                  {t.companyOwnedLabel}
                                  {d.annotated_user ? ` • ${d.annotated_user}` : ""}
                                </div>
                              </div>
                            </div>
                          </td>
                          <td data-label={t.osHeader} style={{ color: "var(--dtg-text-secondary)" }}>
                            {d.os_version} ({d.device_type})
                          </td>
                          <td data-label={t.idHeader}>
                            <span className="dtg-serial-chip">
                              {d.serial_number !== "N/A"
                                ? `${t.serialImeiPrefix} ${d.serial_number}`
                                : t.virtualAssetLabel}
                            </span>
                          </td>
                          <td data-label={t.statusHeader}>
                            <span className="dtg-badge dtg-badge-company">
                              <span className="dtg-badge-dot" />
                              {t.immutableAnchorLabel}
                            </span>
                          </td>
                          <td
                            data-label={t.lastSyncHeader}
                            style={{ color: "var(--dtg-text-secondary)", fontSize: "13px" }}
                          >
                            {formatLastSync(d.last_sync_time)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}
          </>
        )}
      </main>

      {/* Revocation Confirmation Modal Overlay */}
      {showRevokeModal && (
        <div className="dtg-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="revoke-modal-title">
          <div className="dtg-modal">
            <div
              id="revoke-modal-title"
              style={{
                fontSize: "19px",
                fontWeight: 700,
                color: "var(--dtg-danger)",
                marginBottom: "12px",
                display: "flex",
                alignItems: "center",
                gap: "8px",
              }}
            >
              {t.confirmRevocationTitle}
            </div>
            <p style={{ color: "var(--dtg-text)", fontSize: "14px", lineHeight: 1.5, marginBottom: "14px" }}>
              {t.confirmRevocationBody}
            </p>
            <div
              style={{
                maxHeight: "160px",
                overflowY: "auto",
                backgroundColor: "var(--dtg-surface-subtle)",
                border: "1px solid var(--dtg-border-subtle)",
                padding: "12px",
                borderRadius: "6px",
                marginBottom: "16px",
                fontSize: "13px",
                fontFamily: "monospace",
                color: "#3c4043",
              }}
            >
              {revokeTarget.map((targetName, idx) => {
                const matchingDev = devices.find((d) => d.device_user_name === targetName);
                return (
                  <div key={idx} style={{ marginBottom: "6px" }}>
                    • {matchingDev ? `${matchingDev.model} (${t.serialImeiPrefix} ${matchingDev.serial_number})` : targetName}
                  </div>
                );
              })}
            </div>
            <p style={{ color: "var(--dtg-text-secondary)", fontSize: "13px", marginBottom: "22px", lineHeight: 1.45 }}>
              {t.confirmRevocationWarning}
            </p>
            <div className="dtg-modal-actions">
              <button
                onClick={() => setShowRevokeModal(false)}
                disabled={isRevoking}
                className="dtg-btn dtg-btn-neutral"
              >
                {t.cancelAction}
              </button>
              <button
                onClick={handleConfirmRevoke}
                disabled={isRevoking}
                className="dtg-btn dtg-btn-danger"
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
