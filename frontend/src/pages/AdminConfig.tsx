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

export const AdminConfig: React.FC = () => {
  const [config, setConfig] = useState<TenantConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
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

  // Admin-only Session Watch Operations & Telemetry state (moved from Dashboard)
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
      setOpsStatusMessage(
        `Live Login & Cloud Identity Sweep Complete: ${res.fetched_login_events} audit event(s), ${res.unapproved_cloud_identity_byod_events || 0} unapproved Cloud Identity BYOD sync(s) (${res.evaluated_count || 0} evaluated, ${res.revoked_count} signed out, ${res.auto_blocked_byod_devices || 0} unapproved BYOD device(s) blocked).`
      );
      await loadMetrics();
    } catch (e: any) {
      setOpsStatusMessage(`Live login sweep failed: ${e.message}`);
    } finally {
      setRunningLiveSweep(false);
    }
  };

  const handleAddAdmin = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!newAdminEmail) return;
    const target = newAdminEmail.toLowerCase().trim();
    if (!portalAdmins.includes(target)) {
      setPortalAdmins([...portalAdmins, target]);
    }
    setNewAdminEmail("");
    setShowAddAdminModal(false);
  };

  const handleRemoveAdmin = (email: string) => {
    setPortalAdmins(portalAdmins.filter((a) => a !== email));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage("");
    setError("");
    setSaving(true);

    const parsedTargetOus = sessionWatchTargetOusInput
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const parsedTargetGroups = sessionWatchTargetGroupsInput
      .split(",")
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean);

    const updatedConfig: TenantConfig = {
      customer_id: config?.customer_id || "customers/my_customer",
      inactivity_threshold_days: Number(threshold),
      portal_admins: portalAdmins,
      revocation_action: config?.revocation_action || "BLOCK",
      google_client_id: googleClientId.trim(),
      default_locale: defaultLocale,
      trusted_ip_ranges: config?.trusted_ip_ranges || [],
      chaining_allowed_groups: config?.chaining_allowed_groups || [],
      chaining_allowed_ous: config?.chaining_allowed_ous || [],
      enforcement_mode: enforcementMode,
      session_watch_enabled: sessionWatchEnabled,
      caa_enforcement_enabled: caaEnforcementEnabled,
      session_watch_target_ous: parsedTargetOus,
      session_watch_target_groups: parsedTargetGroups,
      session_watch_exempt_admins: sessionWatchExemptAdmins,
      session_watch_dry_run: sessionWatchDryRun,
      session_watch_onboarding_grace_minutes: Math.max(5, Math.min(120, Number(sessionWatchOnboardingGraceMinutes) || 15)),
    };

    try {
      await updateAdminConfig(updatedConfig);
      setConfig(updatedConfig);
      setMessage(t.configSaveSuccess);
      setSaving(false);
      await loadMetrics();
      sendClientLog("INFO", "ADMIN_CONFIG_SAVED", `Admin config updated by ${userEmail}`, {
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

          <div className="dtg-header-actions">
            <a href="#/" className="dtg-btn dtg-btn-outline">
              {t.backToPortal}
            </a>
          </div>
        </div>
      </header>

      <main className="dtg-main dtg-main-narrow">
        {message && (
          <div role="status" aria-live="polite" className="dtg-alert dtg-alert-success">
            <span>{message}</span>
          </div>
        )}
        {error && (
          <div role="alert" className="dtg-alert dtg-alert-error">
            <span>{error}</span>
          </div>
        )}

        {/* Admin-Only Session Watch Operations & Telemetry Card (Moved from Dashboard) */}
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
              >
                {syncingInventory ? "Syncing Cache..." : "🔄 Sync Inventory Cache"}
              </button>
              <button
                type="button"
                onClick={handleAttestThisBrowser}
                disabled={attestingSession}
                className="dtg-btn dtg-btn-outline"
                style={{ fontSize: "12px", padding: "6px 12px" }}
              >
                {attestingSession ? "Attesting..." : "🛡️ Attest Current Session"}
              </button>
              <button
                type="button"
                onClick={handleRunLiveLoginSweep}
                disabled={runningLiveSweep}
                className="dtg-btn dtg-btn-primary"
                style={{ fontSize: "12px", padding: "6px 12px" }}
              >
                {runningLiveSweep ? "Sweeping..." : "⚡ Run Live Login Sweep"}
              </button>
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
        </section>

        <form onSubmit={handleSubmit} className="dtg-card">
          <h2 style={{ margin: "0 0 6px 0", fontSize: "18px", fontWeight: 600, color: "var(--dtg-text)" }}>
            {t.generalSecurityPolicies}
          </h2>
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
                Domain Enforcement Controls (Disabled by Default)
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

            <div style={{ display: "grid", gap: "14px" }}>
              {/* Toggle 1: Session Management for Education Fundamentals */}
              <label
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "12px",
                  padding: "12px 14px",
                  borderRadius: "8px",
                  border: sessionWatchEnabled ? "1.5px solid #1a73e8" : "1px solid var(--dtg-border)",
                  backgroundColor: "var(--dtg-surface)",
                  cursor: "pointer",
                }}
              >
                <input
                  type="checkbox"
                  data-testid="toggle-session-watch"
                  checked={sessionWatchEnabled}
                  onChange={(e) => setSessionWatchEnabled(e.target.checked)}
                  style={{ marginTop: "3px", width: "16px", height: "16px" }}
                />
                <div style={{ fontSize: "13px", lineHeight: 1.5 }}>
                  <div style={{ fontWeight: 700, color: "var(--dtg-text)", marginBottom: "2px" }}>
                    ⚡ Enable Session Management &amp; <code>users.signOut</code> Circuit Breaker (Education Fundamentals)
                  </div>
                  <div style={{ color: "var(--dtg-text-secondary)", fontSize: "12px" }}>
                    <b>Disabled by default.</b> When enabled, enforces device trust without requiring Context-Aware Access licenses—or supplements CAA by actively terminating Google account sessions (<code>admin.directory.users.signOut</code>) and auto-blocking unapproved personal devices (e.g. unapproved Mac/Windows laptops in <code>PENDING_APPROVAL</code>) when they sign in or sync via Chrome Profile Reporting.
                  </div>
                </div>
              </label>

              {/* Toggle 2: CAA Access for Education Standard & Plus */}
              <label
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "12px",
                  padding: "12px 14px",
                  borderRadius: "8px",
                  border: caaEnforcementEnabled ? "1.5px solid #137333" : "1px solid var(--dtg-border)",
                  backgroundColor: "var(--dtg-surface)",
                  cursor: "pointer",
                }}
              >
                <input
                  type="checkbox"
                  data-testid="toggle-caa-enforcement"
                  checked={caaEnforcementEnabled}
                  onChange={(e) => setCaaEnforcementEnabled(e.target.checked)}
                  style={{ marginTop: "3px", width: "16px", height: "16px" }}
                />
                <div style={{ fontSize: "13px", lineHeight: 1.5 }}>
                  <div style={{ fontWeight: 700, color: "var(--dtg-text)", marginBottom: "2px" }}>
                    🛡️ Enable Context-Aware Access (CAA) Integration (Education Standard &amp; Plus)
                  </div>
                  <div style={{ color: "var(--dtg-text-secondary)", fontSize: "12px" }}>
                    <b>Disabled by default.</b> Designed for Google Workspace for Education Standard, Education Plus, and Enterprise tiers. Pairs self-service Cloud Identity device approval with Google Admin Console Context-Aware Access CEL rules (<code>device.is_corp_owned_device == true || device.is_admin_approved_device == true</code>) to block Gmail, Drive, Docs, and Classroom on unapproved devices at the application edge.
                  </div>
                </div>
              </label>
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
                ℹ️ How Enforcement Modes Work Together
              </div>
              <ul style={{ margin: 0, paddingLeft: "18px" }}>
                <li>
                  <b>Why CAA blocks apps while <code>accounts.google.com</code> stays signed in:</b> Context-Aware Access blocks Workspace apps (Gmail, Drive, Docs) at the application edge, but Google must allow initial <code>accounts.google.com</code> login so Chrome Profile Reporting / Endpoint Verification can register the device in Cloud Identity and so the user can open this portal to request approval.
                </li>
                <li>
                  <b>How Session Management closes the account sign-in gap:</b> Enabling <b>Session Management</b> runs a 2-minute sweep across both Admin SDK Login Audit logs and live Cloud Identity <code>PENDING_APPROVAL</code> BYOD syncs. If a user signs in on an unapproved Mac or Windows PC without an active 15-minute Onboarding Grace Pass, Session Watch calls <code>users.signOut</code> to terminate the Google session and transitions the unapproved device to <code>BLOCKED</code>.
                </li>
                <li>
                  <b>Enable Either or Both:</b> Education Fundamentals domains enable <b>Session Management</b>. Education Standard &amp; Plus domains can enable <b>CAA Integration</b> alone (edge app blocking) or enable <b>both</b> together for immediate edge app blocking + automated account sign-out.
                </li>
              </ul>
            </div>

            {sessionWatchEnabled && (
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
                    className="dtg-input"
                  />
                  <span style={{ fontSize: "11.5px", color: "var(--dtg-text-secondary)", display: "block", marginTop: "4px" }}>
                    Hierarchical prefix match (e.g. <code>/Students</code> includes <code>/Students/HighSchool</code>). Leave blank for all domain OUs.
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
                    className="dtg-input"
                  />
                  <span style={{ fontSize: "11.5px", color: "var(--dtg-text-secondary)", display: "block", marginTop: "4px" }}>
                    Comma-separated Google Group emails. If both OUs and Groups are specified, users matching either are in scope.
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
                    className="dtg-input"
                  />
                  <span style={{ fontSize: "11.5px", color: "var(--dtg-text-secondary)", display: "block", marginTop: "4px" }}>
                    Duration of the temporary grace pass when a user clicks <b>+ Add Personal Device</b> or generates a Trust Chaining pairing code.
                  </span>
                </div>

                <label
                  style={{
                    display: "flex",
                    alignItems: "flex-start",
                    gap: "10px",
                    fontSize: "13px",
                    color: "var(--dtg-text)",
                    cursor: "pointer",
                  }}
                >
                  <input
                    type="checkbox"
                    checked={sessionWatchExemptAdmins}
                    onChange={(e) => setSessionWatchExemptAdmins(e.target.checked)}
                    style={{ marginTop: "3px" }}
                  />
                  <span>
                    <b>Admin Safe-Harbor Exemption (Recommended):</b> Exempt Workspace Super Admins and Portal Admins from automated <code>users.signOut</code> sweeps to prevent administrative lockout.
                  </span>
                </label>

                <label
                  style={{
                    display: "flex",
                    alignItems: "flex-start",
                    gap: "10px",
                    fontSize: "13px",
                    color: "var(--dtg-text)",
                    cursor: "pointer",
                  }}
                >
                  <input
                    type="checkbox"
                    checked={sessionWatchDryRun}
                    onChange={(e) => setSessionWatchDryRun(e.target.checked)}
                    style={{ marginTop: "3px" }}
                  />
                  <span>
                    <b>Audit-Only (Dry-Run) Mode:</b> Evaluate all login events and record <code>AUDIT_WOULD_SIGN_OUT</code> in telemetry without calling <code>users.signOut</code>.
                  </span>
                </label>
              </div>
            )}
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
              onChange={(e) => setDefaultLocale(e.target.value)}
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
