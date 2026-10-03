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
import { getAdminConfig, updateAdminConfig, sendClientLog, TenantConfig } from "../services/api";
import { getTranslator } from "../i18n/translations";

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
  const [enforcementMode, setEnforcementMode] = useState("SESSION_WATCH");
  const [sessionWatchTargetOusInput, setSessionWatchTargetOusInput] = useState("");
  const [sessionWatchTargetGroupsInput, setSessionWatchTargetGroupsInput] = useState("");
  const [sessionWatchExemptAdmins, setSessionWatchExemptAdmins] = useState(true);
  const [sessionWatchDryRun, setSessionWatchDryRun] = useState(false);
  const [sessionWatchOnboardingGraceMinutes, setSessionWatchOnboardingGraceMinutes] = useState(15);
  const [newAdminEmail, setNewAdminEmail] = useState("");
  const [showAddAdminModal, setShowAddAdminModal] = useState(false);

  const userEmail = localStorage.getItem("userEmail") || "";
  const userLocale = localStorage.getItem("userLocale") || defaultLocale || "en";
  const t = getTranslator(userLocale);

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
        setEnforcementMode(data.enforcement_mode || "SESSION_WATCH");
        setSessionWatchTargetOusInput((data.session_watch_target_ous || []).join(", "));
        setSessionWatchTargetGroupsInput((data.session_watch_target_groups || []).join(", "));
        setSessionWatchExemptAdmins(data.session_watch_exempt_admins !== false);
        setSessionWatchDryRun(Boolean(data.session_watch_dry_run));
        setSessionWatchOnboardingGraceMinutes(data.session_watch_onboarding_grace_minutes || 15);
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
      sendClientLog("INFO", "ADMIN_CONFIG_SAVED", `Admin config updated by ${userEmail}`, {
        inactivity_threshold_days: updatedConfig.inactivity_threshold_days,
        portal_admins_count: updatedConfig.portal_admins.length,
        default_locale: updatedConfig.default_locale,
        enforcement_mode: updatedConfig.enforcement_mode,
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

        <form onSubmit={handleSubmit} className="dtg-card">
          <h2 style={{ margin: "0 0 6px 0", fontSize: "18px", fontWeight: 600, color: "var(--dtg-text)" }}>
            {t.generalSecurityPolicies}
          </h2>
          <p style={{ fontSize: "13px", color: "var(--dtg-text-secondary)", margin: "0 0 24px 0" }}>
            {t.generalSecurityPoliciesDesc}
          </p>

          <div
            style={{
              marginBottom: "24px",
              padding: "16px",
              borderRadius: "8px",
              border:
                enforcementMode === "SESSION_WATCH"
                  ? "1.5px solid #1a73e8"
                  : "1px solid var(--dtg-border)",
              backgroundColor:
                enforcementMode === "SESSION_WATCH"
                  ? "rgba(26, 115, 232, 0.06)"
                  : "var(--dtg-surface-subtle)",
            }}
          >
            <label
              htmlFor="enforcement-mode-select"
              style={{
                display: "block",
                fontWeight: 600,
                marginBottom: "6px",
                color: "var(--dtg-text)",
                fontSize: "14px",
              }}
            >
              Enforcement Architecture Variation:
            </label>
            <select
              id="enforcement-mode-select"
              value={enforcementMode}
              onChange={(e) => setEnforcementMode(e.target.value)}
              className="dtg-select"
              style={{ width: "100%", padding: "10px 12px", fontSize: "14px", marginBottom: "8px" }}
            >
              <option value="SESSION_WATCH">
                ⚡ CAA-Free Session Watch &amp; users.signOut Circuit Breaker (Education Fundamentals)
              </option>
              <option value="CAA">
                🛡️ Standard Context-Aware Access (Enterprise Plus / Endpoint Verification)
              </option>
            </select>
            <span style={{ fontSize: "12px", color: "var(--dtg-text-secondary)", display: "block", lineHeight: 1.5 }}>
              {enforcementMode === "SESSION_WATCH" ? (
                <>
                  <b>CAA-Free Mode Active (poc/fundamentals-session-watch):</b> Does not require Context-Aware Access licenses. Enforces approved devices via O(1) inventory cache, Chrome extension attestation (<code>/api/session-watch/attest</code>), Admin SDK Reports API login sweeps (<code>admin.reports.audit.readonly</code>), and automated <code>users.signOut</code> circuit breaker (<code>admin.directory.user.security</code>).
                </>
              ) : (
                <>
                  <b>Standard CAA Mode Active:</b> Uses Google Workspace Context-Aware Access CEL rules (<code>device.is_corp_owned_device || device.is_admin_approved_device</code>) to block unapproved devices inline at login.
                </>
              )}
            </span>

            {enforcementMode === "SESSION_WATCH" && (
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
                    Duration of the temporary grace pass when a user clicks <b>+ Add Personal Device</b>, generates a pairing code, or has a pending BYOD device awaiting approval.
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
