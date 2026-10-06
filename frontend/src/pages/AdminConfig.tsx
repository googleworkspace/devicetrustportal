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

import React, { useState, useEffect } from "react";
import {
  getAdminConfig,
  updateAdminConfig,
  sendClientLog,
  TenantConfig,
} from "../services/api";
import { getTranslator } from "../i18n/translations";

function deriveEnforcementMode(
  sessionWatch: boolean,
  cookieThreat: boolean = false
): string {
  if (sessionWatch) return "SESSION_WATCH";
  if (cookieThreat) return "COOKIE_SENTINEL";
  return "DISABLED";
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
  activeColor = "#137333",
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
        backgroundColor: checked ? "rgba(19, 115, 51, 0.04)" : "var(--dtg-surface)",
        transition: "border-color 0.2s ease, background-color 0.2s ease, box-shadow 0.2s ease",
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
    cookieThreatDetectionEnabled: boolean;
    sessionWatchExemptAdmins: boolean;
    sessionWatchDryRun: boolean;
    enableNetworkApproval: boolean;
    enableTrustChaining: boolean;
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
  const [uiLocale, setUiLocale] = useState(() => localStorage.getItem("userLocale") || "en");
  const [sessionWatchEnabled, setSessionWatchEnabled] = useState(false);
  const [cookieThreatDetectionEnabled, setCookieThreatDetectionEnabled] = useState(false);
  const [sessionWatchTargetOusInput, setSessionWatchTargetOusInput] = useState("");
  const [sessionWatchTargetGroupsInput, setSessionWatchTargetGroupsInput] = useState("");
  const [sessionWatchExemptAdmins, setSessionWatchExemptAdmins] = useState(false);
  const [sessionWatchDryRun, setSessionWatchDryRun] = useState(false);
  const [sessionWatchOnboardingGraceMinutes, setSessionWatchOnboardingGraceMinutes] = useState(15);
  const [newAdminEmail, setNewAdminEmail] = useState("");
  const [showAddAdminModal, setShowAddAdminModal] = useState(false);
  const [pendingConfirm, setPendingConfirm] = useState<PendingConfirmChange | null>(null);

  // Switch 1: Network-Gated Campus Approval
  const [enableNetworkApproval, setEnableNetworkApproval] = useState(false);
  const [trustedIps, setTrustedIps] = useState("");
  const [networkOus, setNetworkOus] = useState("");
  const [networkGroups, setNetworkGroups] = useState("");

  // Switch 2: Trust Chaining
  const [enableTrustChaining, setEnableTrustChaining] = useState(false);
  const [chainingOus, setChainingOus] = useState("");
  const [chainingGroups, setChainingGroups] = useState("");
  const [chainingDeniedOus, setChainingDeniedOus] = useState("");
  const [chainingDeniedGroups, setChainingDeniedGroups] = useState("");

  // Switch 3: Session Guard (Education Fundamentals Zero-Trust)
  const [enableSessionGuard, setEnableSessionGuard] = useState(false);
  const [sessionGuardMode, setSessionGuardMode] = useState("DISABLED");
  const [sessionGuardExemptOus, setSessionGuardExemptOus] = useState("");
  const [sessionGuardExemptGroups, setSessionGuardExemptGroups] = useState("");

  const splitList = (str: string): string[] => {
    return str.split(/[\n,]+/).map((s) => s.trim()).filter(Boolean);
  };

  const userEmail = localStorage.getItem("userEmail") || "";
  const t = getTranslator(uiLocale || defaultLocale || "en");
  const enforcementMode = deriveEnforcementMode(
    sessionWatchEnabled,
    cookieThreatDetectionEnabled
  );

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
        const resolvedDefaultLocale = data.default_locale || "en";
        setDefaultLocale(resolvedDefaultLocale);
        if (sessionStorage.getItem("userLocaleOverride") !== "true") {
          setUiLocale(resolvedDefaultLocale);
          localStorage.setItem("userLocale", resolvedDefaultLocale);
        }
        setSessionWatchEnabled(Boolean(data.session_watch_enabled));
        setCookieThreatDetectionEnabled(Boolean(data.cookie_threat_detection_enabled));
        setSessionWatchTargetOusInput((data.session_watch_target_ous || []).join(", "));
        setSessionWatchTargetGroupsInput((data.session_watch_target_groups || []).join(", "));
        setSessionWatchExemptAdmins(Boolean(data.session_watch_exempt_admins));
        setSessionWatchDryRun(Boolean(data.session_watch_dry_run));
        setSessionWatchOnboardingGraceMinutes(data.session_watch_onboarding_grace_minutes || 15);

        // Load Switch 1
        setEnableNetworkApproval(Boolean(data.enable_network_approval));
        setTrustedIps((data.trusted_ip_ranges || []).join(", "));
        setNetworkOus((data.network_approval_allowed_ous || []).join(", "));
        setNetworkGroups((data.network_approval_allowed_groups || []).join(", "));

        // Load Switch 2
        setEnableTrustChaining(Boolean(data.enable_trust_chaining));
        setChainingOus((data.chaining_allowed_ous || []).join(", "));
        setChainingGroups((data.chaining_allowed_groups || []).join(", "));
        setChainingDeniedOus((data.chaining_denied_ous || []).join(", "));
        setChainingDeniedGroups((data.chaining_denied_groups || []).join(", "));

        // Load Switch 3
        setEnableSessionGuard(Boolean(data.enable_session_guard));
        setSessionGuardMode(data.session_guard_mode || (data.enable_session_guard ? "ENFORCE_ACTIVE" : "DISABLED"));
        setSessionGuardExemptOus((data.session_guard_exempt_ous || []).join(", "));
        setSessionGuardExemptGroups((data.session_guard_exempt_groups || []).join(", "));

        setLoading(false);
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
  }, [userEmail]);

  const persistConfiguration = async (
    overrides: Partial<{
      sessionWatchEnabled: boolean;
      cookieThreatDetectionEnabled: boolean;
      sessionWatchExemptAdmins: boolean;
      sessionWatchDryRun: boolean;
      enableNetworkApproval: boolean;
      enableTrustChaining: boolean;
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
    const nextCookieThreat = overrides.cookieThreatDetectionEnabled ?? cookieThreatDetectionEnabled;
    const nextExempt = overrides.sessionWatchExemptAdmins ?? sessionWatchExemptAdmins;
    const nextDryRun = overrides.sessionWatchDryRun ?? sessionWatchDryRun;
    const nextNetApp = overrides.enableNetworkApproval ?? enableNetworkApproval;
    const nextChain = overrides.enableTrustChaining ?? enableTrustChaining;
    const nextAdmins = overrides.portalAdmins ?? portalAdmins;
    const nextThreshold = overrides.threshold ?? threshold;
    const nextClientId = overrides.googleClientId ?? googleClientId;
    const nextLocale = overrides.defaultLocale ?? defaultLocale;
    const nextOusInput = overrides.sessionWatchTargetOusInput ?? sessionWatchTargetOusInput;
    const nextGroupsInput = overrides.sessionWatchTargetGroupsInput ?? sessionWatchTargetGroupsInput;
    const nextGraceMin = overrides.sessionWatchOnboardingGraceMinutes ?? sessionWatchOnboardingGraceMinutes;

    const nextMode = deriveEnforcementMode(nextSw, nextCookieThreat);
    const parsedTargetOus = nextOusInput
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const parsedTargetGroups = nextGroupsInput
      .split(",")
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean);
    const nextGuardActive = Boolean(nextSw || nextCookieThreat || enableSessionGuard);
    const nextGuardMode = nextGuardActive
      ? nextDryRun
        ? "AUDIT_SIMULATION"
        : "ENFORCE_ACTIVE"
      : "DISABLED";

    const updatedConfig: TenantConfig = {
      customer_id: config?.customer_id || "customers/my_customer",
      inactivity_threshold_days: Number(nextThreshold),
      portal_admins: nextAdmins,
      revocation_action: config?.revocation_action || "BLOCK",
      google_client_id: nextClientId.trim(),
      default_locale: nextLocale,
      trusted_ip_ranges: splitList(trustedIps),
      enable_network_approval: nextNetApp,
      network_approval_allowed_ous: splitList(networkOus),
      network_approval_allowed_groups: splitList(networkGroups),
      enable_trust_chaining: nextChain,
      chaining_allowed_ous: splitList(chainingOus),
      chaining_allowed_groups: splitList(chainingGroups),
      chaining_denied_ous: splitList(chainingDeniedOus),
      chaining_denied_groups: splitList(chainingDeniedGroups),
      enable_session_guard: nextGuardActive,
      session_guard_mode: nextGuardMode,
      session_guard_exempt_ous: splitList(sessionGuardExemptOus),
      session_guard_exempt_groups: splitList(sessionGuardExemptGroups),
      enforcement_mode: nextMode,
      session_watch_enabled: nextSw,
      cookie_threat_detection_enabled: nextCookieThreat,
      caa_enforcement_enabled: false,
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
      setCookieThreatDetectionEnabled(nextCookieThreat);
      setSessionWatchExemptAdmins(nextExempt);
      setSessionWatchDryRun(nextDryRun);
      setEnableNetworkApproval(nextNetApp);
      setEnableTrustChaining(nextChain);
      setEnableSessionGuard(nextGuardActive);
      setSessionGuardMode(nextGuardMode);
      setPortalAdmins(nextAdmins);

      const timeStr = new Date().toLocaleTimeString();
      setLastSavedAt(timeStr);
      const tNext = getTranslator(nextLocale);
      const confirmText = `✅ ${tNext.autoSavedHeaderBadge} (${timeStr}): ${changeSummary} — ${tNext.effectiveModeLabel} ${nextMode}${nextDryRun ? ` [${tNext.auditOnlyBadge}]` : ""}`;
      setAutoSaveBanner(confirmText);
      setMessage(tNext.configSaveSuccess);
      setSaving(false);
      sendClientLog("INFO", "ADMIN_CONFIG_SAVED", `Admin config auto-saved by ${userEmail}: ${changeSummary}`, {
        inactivity_threshold_days: updatedConfig.inactivity_threshold_days,
        portal_admins_count: updatedConfig.portal_admins.length,
        default_locale: updatedConfig.default_locale,
        enforcement_mode: updatedConfig.enforcement_mode,
        session_watch_enabled: updatedConfig.session_watch_enabled,
        cookie_threat_detection_enabled: updatedConfig.cookie_threat_detection_enabled,
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

  const activeLang = uiLocale || defaultLocale || "en";

  return (
    <div className="dtg-shell" lang={activeLang} dir={activeLang === "ar" ? "rtl" : "ltr"}>
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

          <div className="dtg-header-actions" style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
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
                {t.autoSavedHeaderBadge} {lastSavedAt}
              </span>
            )}
            <select
              aria-label="Language Selector"
              value={activeLang}
              onChange={(e) => {
                const nextLoc = e.target.value;
                setUiLocale(nextLoc);
                localStorage.setItem("userLocale", nextLoc);
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
              {t.dismissButton}
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

        <form onSubmit={handleSubmit} className="dtg-card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "8px", marginBottom: "6px" }}>
            <h2 style={{ margin: 0, fontSize: "18px", fontWeight: 600, color: "var(--dtg-text)" }}>
              {t.generalSecurityPolicies}
            </h2>
            <span style={{ fontSize: "11.5px", color: "#137333", fontWeight: 600 }}>
              {t.toggleAutoSaveHint}
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
                sessionWatchEnabled || cookieThreatDetectionEnabled
                  ? "1.5px solid #137333"
                  : "1px solid var(--dtg-border)",
              backgroundColor:
                sessionWatchEnabled || cookieThreatDetectionEnabled
                  ? "rgba(19, 115, 51, 0.04)"
                  : "var(--dtg-surface-subtle)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px", marginBottom: "12px" }}>
              <div style={{ fontWeight: 700, fontSize: "15px", color: "var(--dtg-text)" }}>
                {t.domainEnforcementTitle}
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
                      : "#137333",
                  color: "#fff",
                }}
              >
                {t.effectiveModeLabel} {enforcementMode}
              </span>
            </div>

            {!sessionWatchEnabled && !cookieThreatDetectionEnabled && (
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
                {t.newInstallStandbyBanner}
              </div>
            )}

            <div style={{ display: "grid", gap: "14px" }}>
              {/* Toggle 1: Session Management for Education Fundamentals */}
              <ToggleSwitch
                testId="toggle-session-watch"
                checked={sessionWatchEnabled}
                disabled={saving}
                activeColor="#137333"
                onToggle={(nextVal) =>
                  requestToggleWithConfirmation({
                    title: `${nextVal ? "Enable" : "Disable"} Session Management (Education Fundamentals)?`,
                    summary: `Session Management (Education Fundamentals) turned ${nextVal ? "ON" : "OFF"}`,
                    overrides: { sessionWatchEnabled: nextVal },
                  })
                }
                label={t.toggleSessionWatchLabel}
                description={t.toggleSessionWatchDesc}
              />

              {/* Toggle 2: Stolen Cookie & Token Threat Detection (Cloud Hosting ASN & Foreign IP Sentinel) */}
              <ToggleSwitch
                testId="toggle-cookie-threat-detection"
                checked={cookieThreatDetectionEnabled}
                disabled={saving}
                activeColor="#137333"
                onToggle={(nextVal) =>
                  requestToggleWithConfirmation({
                    title: `${nextVal ? "Enable" : "Disable"} Stolen Cookie & Token Threat Detection?`,
                    summary: `Stolen Cookie & Token Threat Detection turned ${nextVal ? "ON" : "OFF"}`,
                    overrides: { cookieThreatDetectionEnabled: nextVal },
                  })
                }
                label={t.toggleCookieThreatLabel}
                description={t.toggleCookieThreatDesc}
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
                {t.pipelineBoxTitle}
              </div>
              <ul style={{ margin: 0, paddingLeft: "18px" }}>
                <li>{t.pipelineBullet1}</li>
                <li>{t.pipelineBullet2}</li>
                <li>{t.pipelineBullet3}</li>
                <li>{t.pipelineBullet4}</li>
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
              <div style={{ fontWeight: 700, fontSize: "13px", color: "#137333", textTransform: "uppercase", letterSpacing: "0.03em" }}>
                {t.rolloutScopingTitle}
              </div>

              {/* Toggle 3: Audit-Only (Dry-Run) Mode */}
              <ToggleSwitch
                testId="toggle-dry-run"
                checked={sessionWatchDryRun}
                disabled={saving}
                activeColor="#137333"
                onToggle={(nextVal) =>
                  requestToggleWithConfirmation({
                    title: `${nextVal ? "Enable" : "Disable"} Audit-Only (Dry-Run) Mode?`,
                    summary: `Audit-Only (Dry-Run) Mode turned ${nextVal ? "ON (no users will be signed out)" : "OFF (live users.signOut enforcement active)"}`,
                    overrides: { sessionWatchDryRun: nextVal },
                  })
                }
                label={t.toggleDryRunLabel}
                description={t.toggleDryRunDesc}
              />

              {/* Cloud Logging Query Helper for Audit-Only & Enforcement Logs */}
              <div
                data-testid="cloud-logging-helper"
                style={{
                  padding: "10px 12px",
                  borderRadius: "6px",
                  backgroundColor: "rgba(19, 115, 51, 0.04)",
                  border: "1px solid rgba(19, 115, 51, 0.25)",
                  fontSize: "11.5px",
                  color: "var(--dtg-text-secondary)",
                  lineHeight: 1.5,
                }}
              >
                <b style={{ color: "var(--dtg-text)" }}>{t.cloudLoggingHelperTitle}</b> {t.cloudLoggingHelperDesc}{" "}
                <code
                  style={{
                    userSelect: "all",
                    color: "var(--dtg-text)",
                    display: "block",
                    marginTop: "6px",
                    padding: "6px 8px",
                    borderRadius: "4px",
                    backgroundColor: "var(--dtg-surface)",
                    border: "1px solid var(--dtg-border-subtle)",
                    fontFamily: "monospace",
                    fontSize: "11px",
                  }}
                >
                  resource.type=&quot;cloud_run_revision&quot; jsonPayload.component=&quot;devicetrustportal.session_guard&quot; jsonPayload.decision=&quot;AUDIT_WOULD_SIGN_OUT&quot;
                </code>
              </div>

              {/* Toggle 4: Admin Safe-Harbor Exemption */}
              <ToggleSwitch
                testId="toggle-exempt-admins"
                checked={sessionWatchExemptAdmins}
                disabled={saving}
                activeColor="#137333"
                onToggle={(nextVal) =>
                  requestToggleWithConfirmation({
                    title: `${nextVal ? "Enable" : "Disable"} Admin Safe-Harbor Exemption?`,
                    summary: `Admin Safe-Harbor Exemption turned ${nextVal ? "ON" : "OFF"}`,
                    overrides: { sessionWatchExemptAdmins: nextVal },
                  })
                }
                label={t.toggleExemptAdminsLabel}
                description={t.toggleExemptAdminsDesc}
              />

              <div>
                <label
                  htmlFor="session-watch-target-ous"
                  style={{ display: "block", fontWeight: 600, marginBottom: "4px", fontSize: "13px", color: "var(--dtg-text)" }}
                >
                  {t.targetOusLabel}
                </label>
                <input
                  id="session-watch-target-ous"
                  type="text"
                  placeholder={t.targetOusPlaceholder}
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
                  {t.targetOusHint}
                </span>
              </div>

              <div>
                <label
                  htmlFor="session-watch-target-groups"
                  style={{ display: "block", fontWeight: 600, marginBottom: "4px", fontSize: "13px", color: "var(--dtg-text)" }}
                >
                  {t.targetGroupsLabel}
                </label>
                <input
                  id="session-watch-target-groups"
                  type="text"
                  placeholder={t.targetGroupsPlaceholder}
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
                  {t.targetGroupsHint}
                </span>
              </div>

              <div>
                <label
                  htmlFor="session-watch-onboarding-grace"
                  style={{ display: "block", fontWeight: 600, marginBottom: "4px", fontSize: "13px", color: "var(--dtg-text)" }}
                >
                  {t.onboardingGraceLabel}
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
                  {t.onboardingGraceHint}
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
              {t.googleClientIdLabel}
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
              {t.googleClientIdHint}
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
              data-testid="default-locale-select"
              value={defaultLocale}
              onChange={(e) => {
                const nextLoc = e.target.value;
                setDefaultLocale(nextLoc);
                setUiLocale(nextLoc);
                localStorage.setItem("userLocale", nextLoc);
                sessionStorage.removeItem("userLocaleOverride");
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

          {/* Switch 1: Network-Gated Campus Approval */}
          <h2 style={{ margin: "0 0 6px 0", fontSize: "18px", fontWeight: 600, color: "var(--dtg-text)" }}>
            Network-Gated Campus Self-Approval
          </h2>
          <p style={{ fontSize: "13px", color: "var(--dtg-text-secondary)", margin: "0 0 18px 0", lineHeight: 1.5 }}>
            Allows users connecting from authorized campus Wi-Fi / IP ranges to self-approve their personal or BYOD devices.
            <b> Security Notice:</b> To prevent unauthorized students or guests from registering rogue devices, scope this feature to specific Staff OUs or Groups.
          </p>

          <div style={{ marginBottom: "20px" }}>
            <ToggleSwitch
              id="enable-network-approval-checkbox"
              testId="toggle-network-approval"
              checked={enableNetworkApproval}
              disabled={saving}
              activeColor="#137333"
              onToggle={(nextVal) =>
                requestToggleWithConfirmation({
                  title: `${nextVal ? "Enable" : "Disable"} Network-Gated Device Approval (Campus Wi-Fi)?`,
                  summary: `Network-Gated Device Approval turned ${nextVal ? "ON" : "OFF"}`,
                  overrides: { enableNetworkApproval: nextVal },
                })
              }
              label="Enable Network-Gated Device Approval (Campus Wi-Fi)"
              description="Master switch: Allow authorized staff/OUs on campus CIDR ranges to self-approve devices."
            />
          </div>

          {enableNetworkApproval && (
            <div style={{ backgroundColor: "var(--dtg-surface-subtle)", padding: "16px", borderRadius: "8px", border: "1px solid var(--dtg-border-subtle)", marginBottom: "28px" }}>
              <div style={{ marginBottom: "16px" }}>
                <label style={{ display: "block", fontWeight: 600, marginBottom: "6px", color: "var(--dtg-text)", fontSize: "13px" }}>
                  Trusted Campus IP / CIDR Ranges:
                </label>
                <input
                  type="text"
                  placeholder="e.g. 192.168.1.0/24, 10.0.0.0/16"
                  value={trustedIps}
                  onChange={(e) => setTrustedIps(e.target.value)}
                  onBlur={() => persistConfiguration({}, "Updated Trusted Campus IP / CIDR Ranges")}
                  className="dtg-input"
                />
                <span style={{ fontSize: "12px", color: "var(--dtg-text-secondary)", display: "block", marginTop: "4px" }}>
                  Comma-separated CIDR subnets representing internal campus Wi-Fi or wired egress.
                </span>
              </div>

              <div style={{ marginBottom: "16px" }}>
                <label style={{ display: "block", fontWeight: 600, marginBottom: "6px", color: "var(--dtg-text)", fontSize: "13px" }}>
                  Authorized Organizational Units (OUs):
                </label>
                <input
                  type="text"
                  placeholder="e.g. /Staff, /Staff/HighSchool (Leave blank for all OUs)"
                  value={networkOus}
                  onChange={(e) => setNetworkOus(e.target.value)}
                  onBlur={() => persistConfiguration({}, "Updated Network Approval Authorized OUs")}
                  className="dtg-input"
                />
                <span style={{ fontSize: "12px", color: "var(--dtg-text-secondary)", display: "block", marginTop: "4px" }}>
                  Hierarchical OU matching: e.g. <code>/Staff</code> matches all sub-OUs under Staff.
                </span>
              </div>

              <div>
                <label style={{ display: "block", fontWeight: 600, marginBottom: "6px", color: "var(--dtg-text)", fontSize: "13px" }}>
                  Authorized Google Groups:
                </label>
                <input
                  type="text"
                  placeholder="e.g. teachers@domain.org, tech-team@domain.org"
                  value={networkGroups}
                  onChange={(e) => setNetworkGroups(e.target.value)}
                  onBlur={() => persistConfiguration({}, "Updated Network Approval Authorized Groups")}
                  className="dtg-input"
                />
              </div>
            </div>
          )}

          <hr style={{ border: "none", borderTop: "1px solid var(--dtg-border-subtle)", margin: "28px 0" }} />

          {/* Switch 2: Device Trust Chaining */}
          <h2 style={{ margin: "0 0 6px 0", fontSize: "18px", fontWeight: 600, color: "var(--dtg-text)" }}>
            Device Trust Chaining
          </h2>
          <p style={{ fontSize: "13px", color: "var(--dtg-text-secondary)", margin: "0 0 18px 0", lineHeight: 1.5 }}>
            Allows a user on an already-approved device (e.g. their managed Chromebook) to generate a secure 6-digit pairing code to authorize a secondary device without IT intervention.
          </p>

          <div style={{ marginBottom: "20px" }}>
            <ToggleSwitch
              id="enable-trust-chaining-checkbox"
              testId="toggle-trust-chaining"
              checked={enableTrustChaining}
              disabled={saving}
              activeColor="#137333"
              onToggle={(nextVal) =>
                requestToggleWithConfirmation({
                  title: `${nextVal ? "Enable" : "Disable"} Device Trust Chaining (Pairing Codes)?`,
                  summary: `Device Trust Chaining turned ${nextVal ? "ON" : "OFF"}`,
                  overrides: { enableTrustChaining: nextVal },
                })
              }
              label="Enable Trust Chaining (Pairing Codes)"
              description="Master switch: Allow authorized OUs/Groups to generate 6-digit pairing codes (with explicit deny-list precedence)."
            />
          </div>

          {enableTrustChaining && (
            <div style={{ backgroundColor: "var(--dtg-surface-subtle)", padding: "16px", borderRadius: "8px", border: "1px solid var(--dtg-border-subtle)", marginBottom: "28px" }}>
              <div style={{ marginBottom: "16px" }}>
                <label style={{ display: "block", fontWeight: 600, marginBottom: "6px", color: "var(--dtg-text)", fontSize: "13px" }}>
                  Authorized OUs:
                </label>
                <input
                  type="text"
                  placeholder="e.g. /Staff, /Faculty"
                  value={chainingOus}
                  onChange={(e) => setChainingOus(e.target.value)}
                  onBlur={() => persistConfiguration({}, "Updated Trust Chaining Authorized OUs")}
                  className="dtg-input"
                />
              </div>

              <div style={{ marginBottom: "16px" }}>
                <label style={{ display: "block", fontWeight: 600, marginBottom: "6px", color: "var(--dtg-text)", fontSize: "13px" }}>
                  Authorized Google Groups:
                </label>
                <input
                  type="text"
                  placeholder="e.g. staff@domain.org"
                  value={chainingGroups}
                  onChange={(e) => setChainingGroups(e.target.value)}
                  onBlur={() => persistConfiguration({}, "Updated Trust Chaining Authorized Groups")}
                  className="dtg-input"
                />
              </div>

              <div style={{ marginBottom: "16px" }}>
                <label style={{ display: "block", fontWeight: 600, marginBottom: "6px", color: "var(--dtg-danger)", fontSize: "13px" }}>
                  Denied OUs (Overrides Allowed):
                </label>
                <input
                  type="text"
                  placeholder="e.g. /Students, /Contractors"
                  value={chainingDeniedOus}
                  onChange={(e) => setChainingDeniedOus(e.target.value)}
                  onBlur={() => persistConfiguration({}, "Updated Trust Chaining Denied OUs")}
                  className="dtg-input"
                />
              </div>

              <div>
                <label style={{ display: "block", fontWeight: 600, marginBottom: "6px", color: "var(--dtg-danger)", fontSize: "13px" }}>
                  Denied Google Groups (Overrides Allowed):
                </label>
                <input
                  type="text"
                  placeholder="e.g. student-assistants@domain.org"
                  value={chainingDeniedGroups}
                  onChange={(e) => setChainingDeniedGroups(e.target.value)}
                  onBlur={() => persistConfiguration({}, "Updated Trust Chaining Denied Groups")}
                  className="dtg-input"
                />
              </div>
            </div>
          )}

          <hr style={{ border: "none", borderTop: "1px solid var(--dtg-border-subtle)", margin: "28px 0" }} />

          {/* Switch 3: Session Guard OU & Group Exemptions */}
          <h2 style={{ margin: "0 0 6px 0", fontSize: "18px", fontWeight: 600, color: "var(--dtg-text)" }}>
            Session Guard Exemptions (Hierarchical OU & Group Safe-Harbor)
          </h2>
          <p style={{ fontSize: "13px", color: "var(--dtg-text-secondary)", margin: "0 0 18px 0", lineHeight: 1.5 }}>
            Users in exempt Organizational Units or Google Groups will never be automatically signed out by Session Management or Stolen Cookie Threat Detection.
          </p>

          <div style={{ backgroundColor: "var(--dtg-surface-subtle)", padding: "16px", borderRadius: "8px", border: "1px solid var(--dtg-border-subtle)", marginBottom: "28px" }}>
            <div style={{ marginBottom: "16px" }}>
              <label style={{ display: "block", fontWeight: 600, marginBottom: "6px", color: "var(--dtg-text)", fontSize: "13px" }}>
                Exempt Organizational Units (OUs):
              </label>
              <input
                type="text"
                placeholder="e.g. /Admins, /Staff/Leadership"
                value={sessionGuardExemptOus}
                onChange={(e) => setSessionGuardExemptOus(e.target.value)}
                onBlur={() => persistConfiguration({}, "Updated Session Guard Exempt OUs")}
                className="dtg-input"
              />
              <span style={{ fontSize: "12px", color: "var(--dtg-text-secondary)", display: "block", marginTop: "4px" }}>
                Users in exempt OUs (including child OUs) will never be automatically signed out.
              </span>
            </div>

            <div>
              <label style={{ display: "block", fontWeight: 600, marginBottom: "6px", color: "var(--dtg-text)", fontSize: "13px" }}>
                Exempt Google Groups:
              </label>
              <input
                type="text"
                placeholder="e.g. emergency-responders@domain.org, super-admins@domain.org"
                value={sessionGuardExemptGroups}
                onChange={(e) => setSessionGuardExemptGroups(e.target.value)}
                onBlur={() => persistConfiguration({}, "Updated Session Guard Exempt Groups")}
                className="dtg-input"
              />
            </div>
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
              <b>{t.confirmChangeSummaryLabel}</b> {pendingConfirm.summary}.<br />
              {t.confirmModalBody}
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
                {t.confirmAutoSaveBtn}
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
