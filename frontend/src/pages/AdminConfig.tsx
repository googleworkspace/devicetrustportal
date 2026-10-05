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
import {
  getAdminConfig,
  updateAdminConfig,
  sendClientLog,
  TenantConfig,
  SessionWatchMetricsResponse,
  getSessionWatchMetrics,
  syncSessionWatchInventory,
  attestBrowserSession,
  runLiveLoginSweep,
  getMyDevices,
  DeviceInfo,
} from "../services/api";
import { getTranslator } from "../i18n/translations";

function deriveEnforcementMode(sessionWatch: boolean, caa: boolean): string {
  if (sessionWatch && caa) return "BOTH";
  if (sessionWatch) return "SESSION_WATCH";
  if (caa) return "CAA";
  return "DISABLED";
}

function selectPlatformMatchedDevice(devices: DeviceInfo[], userAgent: string): DeviceInfo | undefined {
  const ua = (userAgent || "").toLowerCase();
  const isCrOS = ua.includes("cros");
  const isMac = ua.includes("macintosh") || ua.includes("mac os x");
  const isWin = ua.includes("windows");

  return devices.find((d) => {
    if (d.approval_state !== "APPROVED" || !d.serial_number || d.serial_number === "N/A") {
      return false;
    }
    const dtype = (d.device_type || "").toUpperCase();
    const osVer = (d.os_version || "").toUpperCase();
    const isDeviceChromeOS = dtype.includes("CHROME") || osVer.includes("CHROME");
    const isDeviceMac = dtype.includes("MAC") || osVer.includes("MAC");
    const isDeviceWin = dtype.includes("WINDOWS") || osVer.includes("WINDOWS");

    if (isCrOS) return isDeviceChromeOS;
    if (isMac) return isDeviceMac;
    if (isWin) return isDeviceWin;
    return !isDeviceChromeOS;
  });
}

interface ToggleSwitchProps {
  id?: string;
  testId: string;
  checked: boolean;
  disabled?: boolean;
  activeColor?: string;
  onToggle: (nextChecked: boolean) => void;
  label: React.ReactNode;
  description?: React.ReactNode;
}

const ToggleSwitch: React.FC<ToggleSwitchProps> = ({
  id,
  testId,
  checked,
  disabled = false,
  activeColor = "#1a73e8",
  onToggle,
  label,
  description,
}) => {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "space-between",
        gap: "16px",
        padding: "14px 16px",
        borderRadius: "8px",
        border: checked ? `1.5px solid ${activeColor}` : "1px solid var(--dtg-border)",
        backgroundColor: "var(--dtg-surface)",
        transition: "border-color 0.2s ease, box-shadow 0.2s ease",
      }}
    >
      <div style={{ flex: 1, fontSize: "13px", lineHeight: 1.5 }}>
        <div style={{ fontWeight: 700, color: "var(--dtg-text)", marginBottom: description ? "3px" : 0 }}>
          {label}
        </div>
        {description && <div style={{ color: "var(--dtg-text-secondary)", fontSize: "12px" }}>{description}</div>}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: "8px", flexShrink: 0, paddingTop: "2px" }}>
        <span
          style={{
            fontSize: "10.5px",
            fontWeight: 700,
            padding: "2px 7px",
            borderRadius: "999px",
            backgroundColor: checked ? activeColor : "#e8eaed",
            color: checked ? "#ffffff" : "#5f6368",
            letterSpacing: "0.03em",
          }}
        >
          {checked ? "ON" : "OFF"}
        </span>
        <button
          id={id}
          type="button"
          role="switch"
          aria-checked={checked}
          data-testid={testId}
          disabled={disabled}
          onClick={() => !disabled && onToggle(!checked)}
          style={{
            position: "relative",
            width: "48px",
            height: "26px",
            borderRadius: "999px",
            border: "none",
            backgroundColor: checked ? activeColor : "#bdc1c6",
            cursor: disabled ? "not-allowed" : "pointer",
            padding: 0,
            transition: "background-color 0.2s ease",
            outline: "none",
            boxShadow: checked ? "0 1px 3px rgba(0, 0, 0, 0.2)" : "inset 0 1px 2px rgba(0, 0, 0, 0.15)",
          }}
        >
          <span
            style={{
              position: "absolute",
              top: "3px",
              left: checked ? "25px" : "3px",
              width: "20px",
              height: "20px",
              borderRadius: "50%",
              backgroundColor: "#ffffff",
              boxShadow: "0 1px 3px rgba(0, 0, 0, 0.3)",
              transition: "left 0.2s ease",
            }}
          />
        </button>
      </div>
    </div>
  );
};

interface PendingConfirmChange {
  title: string;
  summary: string;
  overrides: Partial<{
    sessionWatchEnabled: boolean;
    caaEnforcementEnabled: boolean;
    sessionWatchExemptAdmins: boolean;
    sessionWatchDryRun: boolean;
    portalAdmins: string[];
  }>;
}

export const AdminConfig: React.FC = () => {
  const [config, setConfig] = useState<TenantConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [autoSaveBanner, setAutoSaveBanner] = useState<string>("");
  const [lastSavedAt, setLastSavedAt] = useState<string>("");
  const [error, setError] = useState("");

  const [threshold, setThreshold] = useState(90);
  const [portalAdmins, setPortalAdmins] = useState<string[]>([]);
  const [googleClientId, setGoogleClientId] = useState("");
  const [defaultLocale, setDefaultLocale] = useState("en");
  const [sessionWatchEnabled, setSessionWatchEnabled] = useState(false);
  const [caaEnforcementEnabled, setCaaEnforcementEnabled] = useState(false);
  const [sessionWatchTargetOusInput, setSessionWatchTargetOusInput] = useState("");
  const [sessionWatchTargetGroupsInput, setSessionWatchTargetGroupsInput] = useState("");
  const [sessionWatchExemptAdmins, setSessionWatchExemptAdmins] = useState(false);
  const [sessionWatchDryRun, setSessionWatchDryRun] = useState(false);
  const [sessionWatchOnboardingGraceMinutes, setSessionWatchOnboardingGraceMinutes] = useState(15);
  const [newAdminEmail, setNewAdminEmail] = useState("");
  const [showAddAdminModal, setShowAddAdminModal] = useState(false);
  const [pendingConfirm, setPendingConfirm] = useState<PendingConfirmChange | null>(null);
  const [logFilter, setLogFilter] = useState<"ALL" | "AUDIT_ONLY" | "REVOKED" | "ALLOWED">("ALL");

  // Admin-only Session Watch Operations & Telemetry state
  const [sessionWatchMetrics, setSessionWatchMetrics] = useState<SessionWatchMetricsResponse | null>(null);
  const [opsStatusMessage, setOpsStatusMessage] = useState<string>("");
  const [syncingInventory, setSyncingInventory] = useState<boolean>(false);
  const [attestingSession, setAttestingSession] = useState<boolean>(false);
  const [runningLiveSweep, setRunningLiveSweep] = useState<boolean>(false);

  const userEmail = localStorage.getItem("userEmail") || "";
  const userLocale = localStorage.getItem("userLocale") || defaultLocale || "en";
  const t = getTranslator(userLocale);
  const enforcementMode = deriveEnforcementMode(sessionWatchEnabled, caaEnforcementEnabled);

  const loadMetrics = useCallback(async () => {
    try {
      const m = await getSessionWatchMetrics();
      setSessionWatchMetrics(m);
    } catch {
      // Non-blocking
    }
  }, []);

  useEffect(() => {
    if (!userEmail) {
      setLoading(false);
      setError("Authentication required. Please sign in with Google on the Dashboard.");
      return;
    }

    const load = async () => {
      try {
        const data = await getAdminConfig();
        setConfig(data);
        setThreshold(data.inactivity_threshold_days);
        setPortalAdmins(data.portal_admins || []);
        setGoogleClientId(data.google_client_id || "");
        setDefaultLocale(data.default_locale || "en");
        setSessionWatchEnabled(Boolean(data.session_watch_enabled));
        setCaaEnforcementEnabled(Boolean(data.caa_enforcement_enabled));
        setSessionWatchTargetOusInput((data.session_watch_target_ous || []).join(", "));
        setSessionWatchTargetGroupsInput((data.session_watch_target_groups || []).join(", "));
        setSessionWatchExemptAdmins(Boolean(data.session_watch_exempt_admins));
        setSessionWatchDryRun(Boolean(data.session_watch_dry_run));
        setSessionWatchOnboardingGraceMinutes(data.session_watch_onboarding_grace_minutes || 15);
        setLoading(false);
        loadMetrics();
        sendClientLog("INFO", "ADMIN_CONFIG_LOADED", `Admin config loaded for ${userEmail}`);
      } catch (e: any) {
        const errMsg = `Access Denied: ${e.message || "Workspace Administrator privileges required."}`;
        setError(errMsg);
        setLoading(false);
        sendClientLog("ERROR", "ADMIN_CONFIG_LOAD_ERROR", errMsg, {
          error: e?.message || String(e),
        });
      }
    };
    load();
  }, [userEmail, loadMetrics]);

  const persistConfiguration = async (
    overrides: Partial<{
      sessionWatchEnabled: boolean;
      caaEnforcementEnabled: boolean;
      sessionWatchExemptAdmins: boolean;
      sessionWatchDryRun: boolean;
      portalAdmins: string[];
      threshold: number;
      googleClientId: string;
      defaultLocale: string;
      sessionWatchTargetOusInput: string;
      sessionWatchTargetGroupsInput: string;
      sessionWatchOnboardingGraceMinutes: number;
    }> = {},
    changeSummary: string = "Configuration updated"
  ) => {
    setMessage("");
    setError("");
    setSaving(true);

    const nextSw = overrides.sessionWatchEnabled ?? sessionWatchEnabled;
    const nextCaa = overrides.caaEnforcementEnabled ?? caaEnforcementEnabled;
    const nextExempt = overrides.sessionWatchExemptAdmins ?? sessionWatchExemptAdmins;
    const nextDryRun = overrides.sessionWatchDryRun ?? sessionWatchDryRun;
    const nextAdmins = overrides.portalAdmins ?? portalAdmins;
    const nextThreshold = overrides.threshold ?? threshold;
    const nextClientId = overrides.googleClientId ?? googleClientId;
    const nextLocale = overrides.defaultLocale ?? defaultLocale;
    const nextOusInput = overrides.sessionWatchTargetOusInput ?? sessionWatchTargetOusInput;
    const nextGroupsInput = overrides.sessionWatchTargetGroupsInput ?? sessionWatchTargetGroupsInput;
    const nextGraceMin = overrides.sessionWatchOnboardingGraceMinutes ?? sessionWatchOnboardingGraceMinutes;

    const nextMode = deriveEnforcementMode(nextSw, nextCaa);
    const parsedTargetOus = nextOusInput
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const parsedTargetGroups = nextGroupsInput
      .split(",")
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean);

    const updatedConfig: TenantConfig = {
      customer_id: config?.customer_id || "customers/my_customer",
      inactivity_threshold_days: Number(nextThreshold),
      portal_admins: nextAdmins,
      revocation_action: config?.revocation_action || "BLOCK",
      google_client_id: nextClientId.trim(),
      default_locale: nextLocale,
      trusted_ip_ranges: config?.trusted_ip_ranges || [],
      chaining_allowed_groups: config?.chaining_allowed_groups || [],
      chaining_allowed_ous: config?.chaining_allowed_ous || [],
      enforcement_mode: nextMode,
      session_watch_enabled: nextSw,
      caa_enforcement_enabled: nextCaa,
      session_watch_target_ous: parsedTargetOus,
      session_watch_target_groups: parsedTargetGroups,
      session_watch_exempt_admins: nextExempt,
      session_watch_dry_run: nextDryRun,
      session_watch_onboarding_grace_minutes: Math.max(5, Math.min(120, Number(nextGraceMin) || 15)),
    };

    try {
      await updateAdminConfig(updatedConfig);
      setConfig(updatedConfig);
      setSessionWatchEnabled(nextSw);
      setCaaEnforcementEnabled(nextCaa);
      setSessionWatchExemptAdmins(nextExempt);
      setSessionWatchDryRun(nextDryRun);
      setPortalAdmins(nextAdmins);

      const timeStr = new Date().toLocaleTimeString();
      setLastSavedAt(timeStr);
      const confirmText = `✅ Auto-Saved (${timeStr}): ${changeSummary} — Effective Mode: ${nextMode}${nextDryRun ? " [AUDIT-ONLY DRY RUN]" : ""}`;
      setAutoSaveBanner(confirmText);
      setMessage(t.configSaveSuccess);
      setSaving(false);
      await loadMetrics();
      sendClientLog("INFO", "ADMIN_CONFIG_SAVED", `Admin config auto-saved by ${userEmail}: ${changeSummary}`, {
        inactivity_threshold_days: updatedConfig.inactivity_threshold_days,
        portal_admins_count: updatedConfig.portal_admins.length,
        default_locale: updatedConfig.default_locale,
        enforcement_mode: updatedConfig.enforcement_mode,
        session_watch_enabled: updatedConfig.session_watch_enabled,
        caa_enforcement_enabled: updatedConfig.caa_enforcement_enabled,
        session_watch_target_ous: updatedConfig.session_watch_target_ous,
        session_watch_target_groups: updatedConfig.session_watch_target_groups,
        session_watch_exempt_admins: updatedConfig.session_watch_exempt_admins,
        session_watch_dry_run: updatedConfig.session_watch_dry_run,
      });
    } catch (err: any) {
      const errMsg = `Update failed: ${err.message}`;
      setError(errMsg);
      setSaving(false);
      sendClientLog("ERROR", "ADMIN_CONFIG_SAVE_ERROR", errMsg, {
        error: err?.message || String(err),
      });
    }
  };

  const requestToggleWithConfirmation = (change: PendingConfirmChange) => {
    setPendingConfirm(change);
  };

  const handleConfirmPendingToggle = async () => {
    if (!pendingConfirm) return;
    const toApply = pendingConfirm;
    setPendingConfirm(null);
    await persistConfiguration(toApply.overrides, toApply.summary);
  };

  const handleSyncInventoryCache = async () => {
    setSyncingInventory(true);
    setOpsStatusMessage("");
    try {
      const res = await syncSessionWatchInventory();
      setOpsStatusMessage(
        `Inventory Cache Synced: ${res.inventory_devices_cached} approved serials cached (${res.loaded_count} records processed).`
      );
      await loadMetrics();
    } catch (e: any) {
      setOpsStatusMessage(`Inventory sync failed: ${e.message}`);
    } finally {
      setSyncingInventory(false);
    }
  };

  const handleAttestThisBrowser = async () => {
    if (!userEmail) return;
    setAttestingSession(true);
    setOpsStatusMessage("");
    try {
      const myDevices = await getMyDevices(userEmail);
      const matchedApproved = selectPlatformMatchedDevice(myDevices, navigator.userAgent);
      if (!matchedApproved) {
        setOpsStatusMessage(
          `Attestation Rejected: No APPROVED device in your inventory matches this browser's OS (${navigator.platform || "current platform"}). Approve this device first.`
        );
        return;
      }
      const serialToUse = matchedApproved.serial_number;
      const res = await attestBrowserSession(userEmail, serialToUse);
      setOpsStatusMessage(
        res.status === "ATTESTED"
          ? `Session Attested: ${userEmail} bound to verified serial ${serialToUse} (${res.client_ip}).`
          : `Attestation Rejected: ${res.message || "Serial not in approved inventory."}`
      );
      await loadMetrics();
    } catch (e: any) {
      setOpsStatusMessage(`Attestation failed: ${e.message}`);
    } finally {
      setAttestingSession(false);
    }
  };

  const handleRunLiveLoginSweep = async () => {
    setRunningLiveSweep(true);
    setOpsStatusMessage("");
    try {
      const res = await runLiveLoginSweep(60, true);
      const auditCount = (res as any).audit_would_signout_count || 0;
      setOpsStatusMessage(
        `Live Login & Cloud Identity Sweep Complete: ${res.fetched_login_events} audit event(s), ${res.unapproved_cloud_identity_byod_events || 0} unapproved Cloud Identity BYOD sync(s) (${res.evaluated_count || 0} evaluated, ${res.revoked_count} signed out, ${auditCount} audit-only would-sign-out, ${res.auto_blocked_byod_devices || 0} unapproved BYOD device(s) blocked).`
      );
      await loadMetrics();
    } catch (e: any) {
      setOpsStatusMessage(`Live login sweep failed: ${e.message}`);
    } finally {
      setRunningLiveSweep(false);
    }
  };

  const handleAddAdmin = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!newAdminEmail) return;
    const target = newAdminEmail.toLowerCase().trim();
    const updatedAdmins = portalAdmins.includes(target) ? portalAdmins : [...portalAdmins, target];
    setNewAdminEmail("");
    setShowAddAdminModal(false);
    await persistConfiguration({ portalAdmins: updatedAdmins }, `Added delegated admin ${target}`);
  };

  const handleRemoveAdmin = async (email: string) => {
    const updatedAdmins = portalAdmins.filter((a) => a !== email);
    await persistConfiguration({ portalAdmins: updatedAdmins }, `Removed delegated admin ${email}`);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await persistConfiguration({}, "All configuration settings saved");
  };

  if (loading) {
    return (
      <div className="dtg-shell" style={{ justifyContent: "center", alignItems: "center" }}>
        <div className="dtg-empty-state" style={{ border: "none", boxShadow: "none", background: "transparent" }}>
          <div className="dtg-spinner" />
          <div style={{ color: "var(--dtg-text-secondary)", fontSize: "15px", fontWeight: 500 }}>
            {t.loadingAdminConfig}
          </div>
        </div>
      </div>
    );
  }

  if (error && !config) {
    return (
      <div className="dtg-shell">
        <main className="dtg-main dtg-main-narrow" style={{ paddingTop: "40px" }}>
          <div className="dtg-card">
            <a
              href="#/"
              style={{
                color: "var(--dtg-primary)",
                textDecoration: "none",
                fontWeight: 600,
                fontSize: "14px",
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
              }}
            >
              &larr; {t.returnToDashboard}
            </a>
            <h1 style={{ color: "var(--dtg-danger)", marginTop: "18px", fontSize: "21px", fontWeight: 600 }}>
              {t.accessDeniedTitle}
            </h1>
            <p style={{ color: "var(--dtg-text)", fontSize: "15px", lineHeight: 1.5 }}>{error}</p>
            <div
              style={{
                backgroundColor: "var(--dtg-surface-subtle)",
                padding: "12px 16px",
                borderRadius: "6px",
                border: "1px solid var(--dtg-border-subtle)",
                fontSize: "13px",
                color: "var(--dtg-text-secondary)",
                marginTop: "20px",
              }}
            >
              {t.signedInAs}: <b style={{ color: "var(--dtg-text)" }}>{userEmail || "None"}</b>.{" "}
              {t.accessDeniedSessionNote}
            </div>
          </div>
        </main>
      </div>
    );
  }

  const allRecentActions = sessionWatchMetrics?.recent_actions || [];
  const filteredActions = allRecentActions.filter((act) => {
    if (logFilter === "AUDIT_ONLY") return act.decision === "AUDIT_WOULD_SIGN_OUT";
    if (logFilter === "REVOKED") return act.decision === "REVOKE_SIGN_OUT";
    if (logFilter === "ALLOWED") return act.decision.startsWith("ALLOW") || act.decision.startsWith("SKIP");
    return true;
  });

  return (
    <div className="dtg-shell">
      {/* Google Workspace Top App Bar */}
      <header className="dtg-header">
        <div className="dtg-header-inner">
          <div className="dtg-brand">
            <a
              href="#/"
              className="dtg-btn dtg-btn-neutral"
              style={{ padding: "8px" }}
              aria-label={t.returnToDashboard}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z" />
              </svg>
            </a>
            <div>
              <h1 className="dtg-brand-title">{t.adminTitle}</h1>
              <div className="dtg-brand-subtitle">{t.adminSubHeader}</div>
            </div>
          </div>

          <div className="dtg-header-actions" style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            {lastSavedAt && (
              <span
                data-testid="header-autosave-indicator"
                style={{
                  fontSize: "11.5px",
                  fontWeight: 600,
                  padding: "4px 10px",
                  borderRadius: "999px",
                  backgroundColor: "#e6f4ea",
                  color: "#137333",
                  border: "1px solid #ceead6",
                }}
              >
                ✓ Auto-saved at {lastSavedAt}
              </span>
            )}
            <a href="#/" className="dtg-btn dtg-btn-outline">
              {t.backToPortal}
            </a>
          </div>
        </div>
      </header>

      <main className="dtg-main dtg-main-narrow">
        {autoSaveBanner && (
          <div
            role="status"
            aria-live="polite"
            data-testid="auto-save-confirmation"
            className="dtg-alert dtg-alert-success"
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              gap: "12px",
              marginBottom: "16px",
              fontWeight: 600,
            }}
          >
            <span>{autoSaveBanner}</span>
            <button
              type="button"
              onClick={() => setAutoSaveBanner("")}
              className="dtg-btn dtg-btn-neutral"
              style={{ padding: "3px 8px", fontSize: "11px" }}
            >
              Dismiss
            </button>
          </div>
        )}
        {message && !autoSaveBanner && (
          <div role="status" aria-live="polite" className="dtg-alert dtg-alert-success">
            <span>{message}</span>
          </div>
        )}
        {error && (
          <div role="alert" className="dtg-alert dtg-alert-error">
            <span>{error}</span>
          </div>
        )}

        {/* Admin-Only Session Watch Operations & Telemetry Card */}
        <section
          className="dtg-card"
          data-testid="admin-session-watch-operations"
          style={{
            marginBottom: "24px",
            border: "1px solid rgba(26, 115, 232, 0.35)",
            background: "linear-gradient(135deg, rgba(26, 115, 232, 0.05), rgba(19, 115, 51, 0.04))",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "12px" }}>
            <div style={{ flex: "1 1 360px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "6px", flexWrap: "wrap" }}>
                <span
                  style={{
                    fontSize: "11px",
                    fontWeight: 700,
                    padding: "2px 8px",
                    borderRadius: "999px",
                    backgroundColor: sessionWatchEnabled ? "#1a73e8" : "#5f6368",
                    color: "#fff",
                  }}
                >
                  {sessionWatchEnabled ? "SESSION WATCH ACTIVE" : "SESSION WATCH DISABLED"}
                </span>
                <span
                  style={{
                    fontSize: "11px",
                    fontWeight: 700,
                    padding: "2px 8px",
                    borderRadius: "999px",
                    backgroundColor: caaEnforcementEnabled ? "#137333" : "#5f6368",
                    color: "#fff",
                  }}
                >
                  {caaEnforcementEnabled ? "CAA ENFORCEMENT ACTIVE" : "CAA ENFORCEMENT DISABLED"}
                </span>
                {sessionWatchDryRun && (
                  <span
                    style={{
                      fontSize: "11px",
                      fontWeight: 700,
                      padding: "2px 8px",
                      borderRadius: "999px",
                      backgroundColor: "#e37400",
                      color: "#fff",
                    }}
                  >
                    ⚠️ AUDIT-ONLY (DRY-RUN) MODE
                  </span>
                )}
              </div>
              <h2 style={{ margin: "0 0 4px 0", fontSize: "16px", fontWeight: 700, color: "var(--dtg-text)" }}>
                Session Watch Admin Controls &amp; Live Telemetry
              </h2>
              <p style={{ margin: 0, fontSize: "12.5px", color: "var(--dtg-text-secondary)", lineHeight: 1.5 }}>
                Admin-only diagnostic actions and real-time enforcement metrics. Standard users and admins alike see the unified device approval experience on the main portal view.
              </p>
            </div>

            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" }}>
              <button
                type="button"
                onClick={handleSyncInventoryCache}
                disabled={syncingInventory}
                className="dtg-btn dtg-btn-outline"
                style={{ fontSize: "12px", padding: "6px 12px" }}
                title="Loads all company Chromebooks (Directory API) and APPROVED BYOD serials (Cloud Identity) into the backend SQLite/RAM cache"
              >
                {syncingInventory ? "Syncing Cache..." : "🔄 Sync Inventory Cache"}
              </button>
              <button
                type="button"
                onClick={handleAttestThisBrowser}
                disabled={attestingSession}
                className="dtg-btn dtg-btn-outline"
                style={{ fontSize: "12px", padding: "6px 12px" }}
                title="Verifies your current browser OS against your APPROVED devices and registers an attested session heartbeat"
              >
                {attestingSession ? "Attesting..." : "🛡️ Attest Current Session"}
              </button>
              <button
                type="button"
                onClick={handleRunLiveLoginSweep}
                disabled={runningLiveSweep}
                className="dtg-btn dtg-btn-primary"
                style={{ fontSize: "12px", padding: "6px 12px" }}
                title="Immediately sweeps Cloud Identity deviceUsers and Admin SDK login logs to enforce or audit unapproved sessions"
              >
                {runningLiveSweep ? "Sweeping..." : "⚡ Run Live Login Sweep"}
              </button>
            </div>
          </div>

          {/* Clear 3-Button Explanation Grid */}
          <div
            data-testid="admin-buttons-explanation"
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))",
              gap: "10px",
              marginTop: "14px",
              padding: "10px 12px",
              borderRadius: "8px",
              backgroundColor: "rgba(255, 255, 255, 0.75)",
              border: "1px solid rgba(26, 115, 232, 0.18)",
              fontSize: "11.5px",
              lineHeight: 1.45,
            }}
          >
            <div>
              <b style={{ color: "var(--dtg-text)" }}>🔄 Sync Inventory Cache:</b>{" "}
              <span style={{ color: "var(--dtg-text-secondary)" }}>
                Pulls all active company Chromebooks (Directory API) and <code>APPROVED</code> personal BYOD serials (Cloud Identity API) into the backend&apos;s &lt;1ms SQLite/RAM cache (<i>Cached Approved Serials</i>).
              </span>
            </div>
            <div>
              <b style={{ color: "var(--dtg-text)" }}>🛡️ Attest Current Session:</b>{" "}
              <span style={{ color: "var(--dtg-text-secondary)" }}>
                Checks that this browser&apos;s OS matches an <code>APPROVED</code> device in your inventory and registers a verified session heartbeat (<i>Active Attested Sessions</i>) binding your email, serial, and IP.
              </span>
            </div>
            <div>
              <b style={{ color: "var(--dtg-text)" }}>⚡ Run Live Login Sweep:</b>{" "}
              <span style={{ color: "var(--dtg-text-secondary)" }}>
                Immediately executes an on-demand sweep across Cloud Identity <code>PENDING_APPROVAL</code> / <code>BLOCKED</code> syncs and Admin SDK <code>login</code> events—either terminating unapproved sessions or logging <code>AUDIT_WOULD_SIGN_OUT</code> in Audit-Only mode.
              </span>
            </div>
          </div>

          {sessionWatchMetrics && (
            <div style={{ display: "flex", gap: "18px", flexWrap: "wrap", marginTop: "14px", paddingTop: "12px", borderTop: "1px solid rgba(26, 115, 232, 0.2)", fontSize: "12px" }}>
              <div>
                <span style={{ color: "var(--dtg-text-secondary)" }}>Cached Approved Serials: </span>
                <b>{sessionWatchMetrics.metrics?.inventory_devices_cached ?? 0}</b>
              </div>
              <div>
                <span style={{ color: "var(--dtg-text-secondary)" }}>Active Attested Sessions: </span>
                <b>{sessionWatchMetrics.active_attestations?.length ?? 0}</b>
              </div>
              <div>
                <span style={{ color: "var(--dtg-text-secondary)" }}>Active Onboarding Passes: </span>
                <b>{sessionWatchMetrics.active_onboarding_leases?.length ?? 0}</b>
              </div>
              <div>
                <span style={{ color: "var(--dtg-text-secondary)" }}>Evaluated Logins: </span>
                <b>{sessionWatchMetrics.metrics?.login_events_evaluated ?? 0}</b>
              </div>
              <div>
                <span style={{ color: "var(--dtg-text-secondary)" }}>Audit-Only Detections (Would Sign Out): </span>
                <b
                  data-testid="metric-audit-would-signout"
                  style={{
                    color:
                      (sessionWatchMetrics.metrics?.audit_would_signout ?? 0) > 0 || sessionWatchDryRun
                        ? "#e37400"
                        : "inherit",
                  }}
                >
                  {sessionWatchMetrics.metrics?.audit_would_signout ?? 0}
                </b>
              </div>
              <div>
                <span style={{ color: "var(--dtg-text-secondary)" }}>Sign-Outs Triggered: </span>
                <b style={{ color: (sessionWatchMetrics.metrics?.signouts_executed ?? 0) > 0 ? "var(--dtg-danger)" : "inherit" }}>
                  {sessionWatchMetrics.metrics?.signouts_executed ?? 0}
                </b>
              </div>
            </div>
          )}

          {opsStatusMessage && (
            <div
              role="status"
              style={{
                marginTop: "12px",
                padding: "8px 12px",
                borderRadius: "6px",
                backgroundColor: "var(--dtg-surface)",
                border: "1px solid var(--dtg-border)",
                fontSize: "12px",
                color: "var(--dtg-text)",
              }}
            >
              {opsStatusMessage}
            </div>
          )}

          {/* Live Session Enforcement & Audit-Only Log Viewer */}
          <div
            data-testid="admin-audit-log-table"
            style={{
              marginTop: "14px",
              paddingTop: "12px",
              borderTop: "1px dashed rgba(26, 115, 232, 0.25)",
              fontSize: "11.5px",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px", marginBottom: "8px" }}>
              <div>
                <div style={{ fontWeight: 700, color: "var(--dtg-text)", fontSize: "12.5px" }}>
                  📋 Live Session Enforcement &amp; Audit-Only Log ({filteredActions.length} shown)
                </div>
                <div style={{ color: "var(--dtg-text-secondary)", fontSize: "11px" }}>
                  When <b>Audit-Only (Dry-Run) Mode</b> is ON, unapproved device logins appear right here as <code>AUDIT_WOULD_SIGN_OUT</code> and in Google Cloud Logging (Logs Explorer).
                </div>
              </div>

              <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                {(
                  [
                    { key: "ALL", label: `All (${allRecentActions.length})` },
                    {
                      key: "AUDIT_ONLY",
                      label: `⚠️ Audit-Only (${allRecentActions.filter((a) => a.decision === "AUDIT_WOULD_SIGN_OUT").length})`,
                    },
                    {
                      key: "REVOKED",
                      label: `🚫 Signed Out (${allRecentActions.filter((a) => a.decision === "REVOKE_SIGN_OUT").length})`,
                    },
                    {
                      key: "ALLOWED",
                      label: `✅ Allowed (${allRecentActions.filter((a) => a.decision.startsWith("ALLOW") || a.decision.startsWith("SKIP")).length})`,
                    },
                  ] as const
                ).map((tab) => (
                  <button
                    key={tab.key}
                    type="button"
                    onClick={() => setLogFilter(tab.key)}
                    style={{
                      fontSize: "11px",
                      fontWeight: logFilter === tab.key ? 700 : 500,
                      padding: "3px 8px",
                      borderRadius: "999px",
                      border: logFilter === tab.key ? "1px solid #1a73e8" : "1px solid var(--dtg-border)",
                      backgroundColor: logFilter === tab.key ? "#e8f0fe" : "var(--dtg-surface)",
                      color: logFilter === tab.key ? "#1967d2" : "var(--dtg-text-secondary)",
                      cursor: "pointer",
                    }}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
            </div>

            {filteredActions.length === 0 ? (
              <div
                style={{
                  padding: "10px 12px",
                  borderRadius: "6px",
                  backgroundColor: "var(--dtg-surface)",
                  border: "1px solid var(--dtg-border-subtle)",
                  color: "var(--dtg-text-secondary)",
                }}
              >
                No session enforcement or audit events matching filter <b>{logFilter}</b> yet. Click <b>⚡ Run Live Login Sweep</b> above to evaluate current domain sessions.
              </div>
            ) : (
              <div style={{ display: "grid", gap: "6px", maxHeight: "260px", overflowY: "auto" }}>
                {filteredActions.slice(0, 25).map((act, idx) => {
                  const isRevoke = act.decision === "REVOKE_SIGN_OUT";
                  const isAudit = act.decision === "AUDIT_WOULD_SIGN_OUT";
                  const badgeBg = isRevoke
                    ? "rgba(217, 48, 37, 0.12)"
                    : isAudit
                    ? "rgba(227, 116, 0, 0.15)"
                    : "rgba(19, 115, 51, 0.12)";
                  const badgeColor = isRevoke ? "#c5221f" : isAudit ? "#b06000" : "#137333";

                  return (
                    <div
                      key={idx}
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        gap: "8px",
                        flexWrap: "wrap",
                        padding: "7px 10px",
                        borderRadius: "6px",
                        backgroundColor: "var(--dtg-surface)",
                        border: isAudit
                          ? "1px solid rgba(227, 116, 0, 0.4)"
                          : isRevoke
                          ? "1px solid rgba(217, 48, 37, 0.3)"
                          : "1px solid var(--dtg-border-subtle)",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                        <span
                          style={{
                            fontWeight: 700,
                            fontSize: "10.5px",
                            padding: "2px 6px",
                            borderRadius: "4px",
                            backgroundColor: badgeBg,
                            color: badgeColor,
                          }}
                        >
                          {isAudit ? "⚠️ AUDIT_WOULD_SIGN_OUT" : isRevoke ? "🚫 REVOKE_SIGN_OUT" : act.decision}
                        </span>
                        <b style={{ color: "var(--dtg-text)" }}>{act.user_email}</b>
                        <span style={{ color: "var(--dtg-text-secondary)" }}>{act.reason}</span>
                      </div>
                      <span style={{ color: "var(--dtg-text-secondary)", fontFamily: "monospace", fontSize: "11px" }}>
                        {act.timestamp_iso ? new Date(act.timestamp_iso).toLocaleTimeString() : ""}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Cloud Logging Query Helper for Audit-Only Mode */}
            <div
              style={{
                marginTop: "10px",
                padding: "8px 10px",
                borderRadius: "6px",
                backgroundColor: "rgba(26, 115, 232, 0.04)",
                border: "1px solid rgba(26, 115, 232, 0.15)",
                fontSize: "11px",
                color: "var(--dtg-text-secondary)",
              }}
            >
              <b>☁️ Google Cloud Logging (30-Day Retention):</b> Every <code>AUDIT_WOULD_SIGN_OUT</code> and <code>REVOKE_SIGN_OUT</code> event is also streamed as structured JSON to Cloud Run <code>stdout</code>. Query in <b>GCP Console &gt; Logs Explorer</b> with:{" "}
              <code style={{ userSelect: "all", color: "var(--dtg-text)" }}>
                resource.type=&quot;cloud_run_revision&quot; jsonPayload.component=&quot;devicetrustportal.session_guard&quot; jsonPayload.decision=&quot;AUDIT_WOULD_SIGN_OUT&quot;
              </code>
            </div>
          </div>
        </section>

        <form onSubmit={handleSubmit} className="dtg-card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "8px", marginBottom: "6px" }}>
            <h2 style={{ margin: 0, fontSize: "18px", fontWeight: 600, color: "var(--dtg-text)" }}>
              {t.generalSecurityPolicies}
            </h2>
            <span style={{ fontSize: "11.5px", color: "#137333", fontWeight: 600 }}>
              ⚡ Toggle switches confirm &amp; auto-save immediately
            </span>
          </div>
          <p style={{ fontSize: "13px", color: "var(--dtg-text-secondary)", margin: "0 0 24px 0" }}>
            {t.generalSecurityPoliciesDesc}
          </p>

          {/* Domain Enforcement Mode Toggles (Disabled by Default) */}
          <div
            style={{
              marginBottom: "24px",
              padding: "18px",
              borderRadius: "8px",
              border:
                sessionWatchEnabled || caaEnforcementEnabled
                  ? "1.5px solid #1a73e8"
                  : "1px solid var(--dtg-border)",
              backgroundColor:
                sessionWatchEnabled || caaEnforcementEnabled
                  ? "rgba(26, 115, 232, 0.05)"
                  : "var(--dtg-surface-subtle)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px", marginBottom: "12px" }}>
              <div style={{ fontWeight: 700, fontSize: "15px", color: "var(--dtg-text)" }}>
                Domain Enforcement Controls (Disabled by Default on New Installs)
              </div>
              <span
                data-testid="active-enforcement-mode-pill"
                style={{
                  fontSize: "11px",
                  fontWeight: 700,
                  padding: "3px 10px",
                  borderRadius: "999px",
                  backgroundColor:
                    enforcementMode === "DISABLED"
                      ? "#5f6368"
                      : enforcementMode === "BOTH"
                      ? "#0d652d"
                      : "#1a73e8",
                  color: "#fff",
                }}
              >
                Effective Mode: {enforcementMode}
              </span>
            </div>

            {!sessionWatchEnabled && !caaEnforcementEnabled && (
              <div
                style={{
                  marginBottom: "14px",
                  padding: "10px 12px",
                  borderRadius: "6px",
                  backgroundColor: "rgba(249, 171, 0, 0.12)",
                  border: "1px solid rgba(249, 171, 0, 0.4)",
                  fontSize: "12px",
                  color: "var(--dtg-text)",
                }}
              >
                <b>New Installation Standby:</b> Both Session Management and Context-Aware Access monitoring are disabled by default so you can verify your device inventory first. Flip either toggle switch below to confirm and auto-save enforcement.
              </div>
            )}

            <div style={{ display: "grid", gap: "14px" }}>
              {/* Toggle 1: Session Management for Education Fundamentals */}
              <ToggleSwitch
                testId="toggle-session-watch"
                checked={sessionWatchEnabled}
                disabled={saving}
                activeColor="#1a73e8"
                onToggle={(nextVal) =>
                  requestToggleWithConfirmation({
                    title: `${nextVal ? "Enable" : "Disable"} Session Management (Education Fundamentals)?`,
                    summary: `Session Management (Education Fundamentals) turned ${nextVal ? "ON" : "OFF"}`,
                    overrides: { sessionWatchEnabled: nextVal },
                  })
                }
                label={
                  <>
                    ⚡ Enable Session Management &amp; <code>users.signOut</code> Circuit Breaker (Education Fundamentals)
                  </>
                }
                description={
                  <>
                    <b>Disabled by default on new installs.</b> When toggled ON, enforces device trust without requiring Context-Aware Access licenses—or supplements CAA by terminating Google account sessions (<code>admin.directory.users.signOut</code> + OAuth token grant revocation) and auto-blocking unapproved personal devices (e.g. unapproved Mac/Windows laptops in <code>PENDING_APPROVAL</code> or re-authenticating <code>BLOCKED</code> devices) within seconds.
                  </>
                }
              />

              {/* Toggle 2: CAA Access for Education Standard & Plus */}
              <ToggleSwitch
                testId="toggle-caa-enforcement"
                checked={caaEnforcementEnabled}
                disabled={saving}
                activeColor="#137333"
                onToggle={(nextVal) =>
                  requestToggleWithConfirmation({
                    title: `${nextVal ? "Enable" : "Disable"} Context-Aware Access Integration (Standard & Plus)?`,
                    summary: `Context-Aware Access (CAA) Integration turned ${nextVal ? "ON" : "OFF"}`,
                    overrides: { caaEnforcementEnabled: nextVal },
                  })
                }
                label={
                  <>
                    🛡️ Enable Context-Aware Access (CAA) Integration (Education Standard &amp; Plus)
                  </>
                }
                description={
                  <>
                    <b>Disabled by default on new installs.</b> Designed for Google Workspace for Education Standard, Education Plus, and Enterprise tiers. Pairs self-service Cloud Identity device approval with Google Admin Console Context-Aware Access CEL rules (<code>device.is_corp_owned_device == true || device.is_admin_approved_device == true</code>) to block Gmail, Drive, Docs, and Classroom on unapproved devices at the application edge.
                  </>
                }
              />
            </div>

            {/* Clear Architectural Explanation Box */}
            <div
              style={{
                marginTop: "14px",
                padding: "12px 14px",
                borderRadius: "6px",
                backgroundColor: "var(--dtg-surface)",
                border: "1px solid var(--dtg-border-subtle)",
                fontSize: "12px",
                color: "var(--dtg-text-secondary)",
                lineHeight: 1.55,
              }}
            >
              <div style={{ fontWeight: 700, color: "var(--dtg-text)", marginBottom: "4px" }}>
                ℹ️ How the 3-Layer Enforcement Pipeline &amp; CAA Work Together
              </div>
              <ul style={{ margin: 0, paddingLeft: "18px" }}>
                <li>
                  <b>Why CAA blocks apps while <code>accounts.google.com</code> stays signed in:</b> Context-Aware Access blocks Workspace apps (Gmail, Drive, Docs) at the application edge, but Google allows initial <code>accounts.google.com</code> login so Chrome Profile Reporting / Endpoint Verification can register the device in Cloud Identity.
                </li>
                <li>
                  <b>Layer 1 — Inline Portal Check (&lt; 0.5s) &amp; 8s Heartbeat:</b> Opening the portal on an unapproved device without an active 15-minute Onboarding Grace Pass immediately triggers <code>GET /api/session-watch/session-status</code>, executing <code>users.signOut</code>, revoking the portal OAuth grant, and returning <code>HTTP 401</code> to clear the browser session.
                </li>
                <li>
                  <b>Layer 2 — Sub-10s Cloud Identity <code>lastSyncTime</code> Polling (~2–10s):</b> Because Chrome Profile Reporting updates <code>DeviceUser.lastSyncTime</code> in ~1.7s on sign-in, the 1-minute Cloud Scheduler job runs 5 rapid 10-second sub-polls across both <code>PENDING_APPROVAL</code> and re-logged-in <code>BLOCKED</code> BYOD devices (plus Admin SDK login events) to boot unapproved sessions even if the user never opens the portal.
                </li>
                <li>
                  <b>Enable Either or Both:</b> On new installs, both toggles start OFF. Toggle ON <b>Session Management</b> for Fundamentals, <b>CAA Integration</b> for Standard/Plus edge blocking, or <b>Both</b> for edge app blocking + immediate Google session termination.
                </li>
              </ul>
            </div>

            <div
              style={{
                marginTop: "16px",
                paddingTop: "16px",
                borderTop: "1px solid var(--dtg-border)",
                display: "grid",
                gap: "14px",
              }}
            >
              <div style={{ fontWeight: 700, fontSize: "13px", color: "#1967d2", textTransform: "uppercase", letterSpacing: "0.03em" }}>
                Session Watch Rollout Scoping &amp; Onboarding Safeguards
              </div>

              {/* Toggle 3: Audit-Only (Dry-Run) Mode */}
              <ToggleSwitch
                testId="toggle-dry-run"
                checked={sessionWatchDryRun}
                disabled={saving}
                activeColor="#e37400"
                onToggle={(nextVal) =>
                  requestToggleWithConfirmation({
                    title: `${nextVal ? "Enable" : "Disable"} Audit-Only (Dry-Run) Mode?`,
                    summary: `Audit-Only (Dry-Run) Mode turned ${nextVal ? "ON (no users will be signed out)" : "OFF (live users.signOut enforcement active)"}`,
                    overrides: { sessionWatchDryRun: nextVal },
                  })
                }
                label={
                  <>
                    ⚠️ Audit-Only (Dry-Run) Mode (<code>AUDIT_WOULD_SIGN_OUT</code>)
                  </>
                }
                description={
                  <>
                    Evaluate all login events and Cloud Identity device syncs, recording <code>AUDIT_WOULD_SIGN_OUT</code> in the <b>Live Session Enforcement &amp; Audit-Only Log</b> above and in <b>Google Cloud Logging</b> without calling <code>users.signOut</code> or blocking devices.
                  </>
                }
              />

              {/* Toggle 4: Admin Safe-Harbor Exemption */}
              <ToggleSwitch
                testId="toggle-exempt-admins"
                checked={sessionWatchExemptAdmins}
                disabled={saving}
                activeColor="#1a73e8"
                onToggle={(nextVal) =>
                  requestToggleWithConfirmation({
                    title: `${nextVal ? "Enable" : "Disable"} Admin Safe-Harbor Exemption?`,
                    summary: `Admin Safe-Harbor Exemption turned ${nextVal ? "ON" : "OFF"}`,
                    overrides: { sessionWatchExemptAdmins: nextVal },
                  })
                }
                label={<>🛡️ Admin Safe-Harbor Exemption</>}
                description={
                  <>
                    Exempt Workspace Super Admins and Portal Admins from automated <code>users.signOut</code> sweeps to prevent administrative lockout. (Leave <b>OFF</b> when testing unapproved-device sign-out with your own admin account).
                  </>
                }
              />

              <div>
                <label
                  htmlFor="session-watch-target-ous"
                  style={{ display: "block", fontWeight: 600, marginBottom: "4px", fontSize: "13px", color: "var(--dtg-text)" }}
                >
                  Target Organizational Units (OUs) for Session Watch Rollout:
                </label>
                <input
                  id="session-watch-target-ous"
                  type="text"
                  placeholder="/Students, /Staff/Pilot (leave blank to enforce across all OUs)"
                  value={sessionWatchTargetOusInput}
                  onChange={(e) => setSessionWatchTargetOusInput(e.target.value)}
                  onBlur={() =>
                    persistConfiguration(
                      { sessionWatchTargetOusInput },
                      `Updated Target OUs (${sessionWatchTargetOusInput || "All OUs"})`
                    )
                  }
                  className="dtg-input"
                />
                <span style={{ fontSize: "11.5px", color: "var(--dtg-text-secondary)", display: "block", marginTop: "4px" }}>
                  Hierarchical prefix match (e.g. <code>/Students</code> includes <code>/Students/HighSchool</code>). Auto-saves when you leave the field.
                </span>
              </div>

              <div>
                <label
                  htmlFor="session-watch-target-groups"
                  style={{ display: "block", fontWeight: 600, marginBottom: "4px", fontSize: "13px", color: "var(--dtg-text)" }}
                >
                  Target Google Groups for Session Watch Rollout:
                </label>
                <input
                  id="session-watch-target-groups"
                  type="text"
                  placeholder="session-watch-pilot@gwfe.org, byod-enforced@gwfe.org (leave blank for all)"
                  value={sessionWatchTargetGroupsInput}
                  onChange={(e) => setSessionWatchTargetGroupsInput(e.target.value)}
                  onBlur={() =>
                    persistConfiguration(
                      { sessionWatchTargetGroupsInput },
                      `Updated Target Groups (${sessionWatchTargetGroupsInput || "All Groups"})`
                    )
                  }
                  className="dtg-input"
                />
                <span style={{ fontSize: "11.5px", color: "var(--dtg-text-secondary)", display: "block", marginTop: "4px" }}>
                  Comma-separated Google Group emails. Auto-saves when you leave the field.
                </span>
              </div>

              <div>
                <label
                  htmlFor="session-watch-onboarding-grace"
                  style={{ display: "block", fontWeight: 600, marginBottom: "4px", fontSize: "13px", color: "var(--dtg-text)" }}
                >
                  Personal Device Onboarding Grace Pass Duration (Minutes):
                </label>
                <input
                  id="session-watch-onboarding-grace"
                  type="number"
                  min={5}
                  max={120}
                  value={sessionWatchOnboardingGraceMinutes}
                  onChange={(e) => setSessionWatchOnboardingGraceMinutes(Number(e.target.value))}
                  onBlur={() =>
                    persistConfiguration(
                      { sessionWatchOnboardingGraceMinutes },
                      `Updated Onboarding Grace Pass to ${sessionWatchOnboardingGraceMinutes}m`
                    )
                  }
                  className="dtg-input"
                />
                <span style={{ fontSize: "11.5px", color: "var(--dtg-text-secondary)", display: "block", marginTop: "4px" }}>
                  Duration of the temporary grace pass when a user clicks <b>+ Add Personal Device</b> or generates a Trust Chaining pairing code.
                </span>
              </div>
            </div>
          </div>

          <div style={{ marginBottom: "22px" }}>
            <label
              htmlFor="inactivity-threshold"
              style={{ display: "block", fontWeight: 600, marginBottom: "6px", color: "var(--dtg-text)", fontSize: "14px" }}
            >
              {t.inactivityThresholdLabel}
            </label>
            <input
              id="inactivity-threshold"
              type="number"
              min={1}
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
              onBlur={() =>
                persistConfiguration({ threshold }, `Updated Inactivity Threshold to ${threshold} days`)
              }
              className="dtg-input"
            />
            <span style={{ fontSize: "12px", color: "var(--dtg-text-secondary)", display: "block", marginTop: "5px" }}>
              {t.inactivityThresholdHint}
            </span>
          </div>

          <div style={{ marginBottom: "22px" }}>
            <label
              htmlFor="google-client-id-input"
              style={{ display: "block", fontWeight: 600, marginBottom: "6px", color: "var(--dtg-text)", fontSize: "14px" }}
            >
              Google OAuth 2.0 Web Client ID:
            </label>
            <input
              id="google-client-id-input"
              type="text"
              placeholder="1234567890-abcdefg.apps.googleusercontent.com"
              value={googleClientId}
              onChange={(e) => setGoogleClientId(e.target.value)}
              onBlur={() =>
                persistConfiguration({ googleClientId }, "Updated Google OAuth 2.0 Web Client ID")
              }
              className="dtg-input"
            />
            <span style={{ fontSize: "12px", color: "var(--dtg-text-secondary)", display: "block", marginTop: "5px" }}>
              OAuth 2.0 Web Application Client ID used for Google Sign-In on the portal.
            </span>
          </div>

          <div style={{ marginBottom: "28px" }}>
            <label
              htmlFor="default-locale-select"
              style={{ display: "block", fontWeight: 600, marginBottom: "6px", color: "var(--dtg-text)", fontSize: "14px" }}
            >
              {t.defaultLocaleLabel}
            </label>
            <select
              id="default-locale-select"
              value={defaultLocale}
              onChange={(e) => {
                const nextLoc = e.target.value;
                setDefaultLocale(nextLoc);
                persistConfiguration({ defaultLocale: nextLoc }, `Updated Default Portal Language to ${nextLoc}`);
              }}
              className="dtg-select"
              style={{ width: "100%", padding: "10px 12px", fontSize: "14px" }}
            >
              <option value="en">English (en) — Default International</option>
              <option value="es">Español (es) — Spanish Regionalization</option>
              <option value="fr">Français (fr) — French Regionalization</option>
              <option value="ja">日本語 (ja) — Japanese Regionalization</option>
              <option value="de">Deutsch (de) — German Regionalization</option>
              <option value="pt">Português (Brasil) (pt-BR) — Brazilian Portuguese Regionalization</option>
              <option value="zh">简体中文 (zh) — Chinese Simplified Regionalization</option>
              <option value="it">Italiano (it) — Italian Regionalization</option>
              <option value="ko">한국어 (ko) — Korean Regionalization</option>
              <option value="ar">العربية (ar) — Arabic Regionalization</option>
              <option value="hi">हिन्दी (hi) — Hindi Regionalization</option>
              <option value="nl">Nederlands (nl) — Dutch Regionalization</option>
              <option value="pl">Polski (pl) — Polish Regionalization</option>
              <option value="sv">Svenska (sv) — Swedish Regionalization</option>
              <option value="tr">Türkçe (tr) — Turkish Regionalization</option>
            </select>
            <span style={{ fontSize: "12px", color: "var(--dtg-text-secondary)", display: "block", marginTop: "5px" }}>
              {t.defaultLocaleHint}
            </span>
          </div>

          <hr style={{ border: "none", borderTop: "1px solid var(--dtg-border-subtle)", margin: "28px 0" }} />

          <h2 style={{ margin: "0 0 6px 0", fontSize: "18px", fontWeight: 600, color: "var(--dtg-text)" }}>
            {t.delegatedAccessTitle}
          </h2>
          <p style={{ fontSize: "13px", color: "var(--dtg-text-secondary)", margin: "0 0 20px 0" }}>
            {t.delegatedAccessDesc}
          </p>

          <div style={{ marginBottom: "28px" }}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "12px",
                flexWrap: "wrap",
                gap: "10px",
              }}
            >
              <label style={{ display: "block", fontWeight: 600, color: "var(--dtg-text)", fontSize: "14px" }}>
                {t.authorizedAdminsLabel}
              </label>
              <button
                type="button"
                onClick={() => setShowAddAdminModal(true)}
                className="dtg-btn dtg-btn-outline"
              >
                {t.addAdminButton}
              </button>
            </div>

            {portalAdmins.length === 0 ? (
              <div
                style={{
                  padding: "14px 16px",
                  backgroundColor: "var(--dtg-surface-subtle)",
                  color: "var(--dtg-text-secondary)",
                  fontSize: "13px",
                  borderRadius: "6px",
                  border: "1px solid var(--dtg-border-subtle)",
                }}
              >
                {t.noDelegatedAdmins}
              </div>
            ) : (
              <div
                style={{
                  border: "1px solid var(--dtg-border)",
                  borderRadius: "8px",
                  backgroundColor: "var(--dtg-surface)",
                  overflow: "hidden",
                }}
              >
                {portalAdmins.map((email, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: "12px 16px",
                      borderBottom: idx < portalAdmins.length - 1 ? "1px solid var(--dtg-border-subtle)" : "none",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      flexWrap: "wrap",
                      gap: "10px",
                    }}
                  >
                    <span style={{ fontFamily: "monospace", fontSize: "14px", color: "var(--dtg-text)", wordBreak: "break-all" }}>
                      {email}
                    </span>
                    <button
                      type="button"
                      aria-label={`${t.removeAdminButton} ${email}`}
                      onClick={() => handleRemoveAdmin(email)}
                      className="dtg-btn dtg-btn-danger-outline"
                    >
                      {t.removeAdminButton}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <button
            type="submit"
            disabled={saving}
            className="dtg-btn dtg-btn-primary"
            style={{ width: "100%", padding: "12px 24px", fontSize: "14px" }}
          >
            {saving ? t.savingConfigsButton : t.saveConfigsButton}
          </button>
        </form>
      </main>

      {/* Confirmation Modal for Toggle Switch Auto-Save */}
      {pendingConfirm && (
        <div
          className="dtg-modal-backdrop"
          role="dialog"
          aria-modal="true"
          data-testid="confirm-toggle-modal"
          aria-labelledby="confirm-toggle-modal-title"
        >
          <div className="dtg-modal" style={{ maxWidth: "460px" }}>
            <h3
              id="confirm-toggle-modal-title"
              style={{ margin: "0 0 10px 0", fontSize: "17px", fontWeight: 700, color: "var(--dtg-text)" }}
            >
              {pendingConfirm.title}
            </h3>
            <p style={{ fontSize: "13px", color: "var(--dtg-text-secondary)", margin: "0 0 18px 0", lineHeight: 1.55 }}>
              <b>Change Summary:</b> {pendingConfirm.summary}.<br />
              Clicking <b>Confirm &amp; Auto-Save</b> will immediately persist this configuration to Secret Manager and apply it across your domain.
            </p>
            <div className="dtg-modal-actions">
              <button
                type="button"
                onClick={() => setPendingConfirm(null)}
                className="dtg-btn dtg-btn-neutral"
              >
                {t.cancelAction}
              </button>
              <button
                type="button"
                data-testid="confirm-autosave-btn"
                onClick={handleConfirmPendingToggle}
                className="dtg-btn dtg-btn-primary"
              >
                ✓ Confirm &amp; Auto-Save
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add Authorized Administrator Modal Overlay */}
      {showAddAdminModal && (
        <div className="dtg-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="add-admin-modal-title">
          <div className="dtg-modal" style={{ maxWidth: "450px" }}>
            <h3
              id="add-admin-modal-title"
              style={{ margin: "0 0 10px 0", fontSize: "18px", fontWeight: 600, color: "var(--dtg-text)" }}
            >
              {t.addAdminModalTitle}
            </h3>
            <p style={{ fontSize: "13px", color: "var(--dtg-text-secondary)", margin: "0 0 18px 0", lineHeight: 1.5 }}>
              {t.addAdminModalDesc}
            </p>

            <form onSubmit={handleAddAdmin}>
              <div style={{ marginBottom: "22px" }}>
                <label
                  htmlFor="modal-admin-email"
                  style={{ display: "block", fontWeight: 600, marginBottom: "6px", color: "var(--dtg-text)", fontSize: "13px" }}
                >
                  {t.emailAddressLabel}
                </label>
                <input
                  id="modal-admin-email"
                  type="email"
                  required
                  placeholder="admin@yourdomain.com"
                  value={newAdminEmail}
                  onChange={(e) => setNewAdminEmail(e.target.value)}
                  className="dtg-input"
                />
              </div>

              <div className="dtg-modal-actions">
                <button
                  type="button"
                  onClick={() => {
                    setNewAdminEmail("");
                    setShowAddAdminModal(false);
                  }}
                  className="dtg-btn dtg-btn-neutral"
                >
                  {t.cancelAction}
                </button>
                <button type="submit" className="dtg-btn dtg-btn-primary">
                  {t.addAdminButton}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
