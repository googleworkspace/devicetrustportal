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
  const [newAdminEmail, setNewAdminEmail] = useState("");
  const [showAddAdminModal, setShowAddAdminModal] = useState(false);

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

        // Load Switch 1
        setEnableNetworkApproval(data.enable_network_approval || false);
        setTrustedIps((data.trusted_ip_ranges || []).join(", "));
        setNetworkOus((data.network_approval_allowed_ous || []).join(", "));
        setNetworkGroups((data.network_approval_allowed_groups || []).join(", "));

        // Load Switch 2
        setEnableTrustChaining(data.enable_trust_chaining || false);
        setChainingOus((data.chaining_allowed_ous || []).join(", "));
        setChainingGroups((data.chaining_allowed_groups || []).join(", "));
        setChainingDeniedOus((data.chaining_denied_ous || []).join(", "));
        setChainingDeniedGroups((data.chaining_denied_groups || []).join(", "));

        // Load Switch 3
        setEnableSessionGuard(data.enable_session_guard || false);
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

    const updatedConfig: TenantConfig = {
      customer_id: config?.customer_id || "customers/my_customer",
      inactivity_threshold_days: Number(threshold),
      portal_admins: portalAdmins,
      revocation_action: config?.revocation_action || "BLOCK",
      google_client_id: googleClientId.trim(),
      default_locale: defaultLocale,
      trusted_ip_ranges: splitList(trustedIps),
      enable_network_approval: enableNetworkApproval,
      network_approval_allowed_ous: splitList(networkOus),
      network_approval_allowed_groups: splitList(networkGroups),
      enable_trust_chaining: enableTrustChaining,
      chaining_allowed_ous: splitList(chainingOus),
      chaining_allowed_groups: splitList(chainingGroups),
      chaining_denied_ous: splitList(chainingDeniedOus),
      chaining_denied_groups: splitList(chainingDeniedGroups),
      enable_session_guard: enableSessionGuard || sessionGuardMode !== "DISABLED",
      session_guard_mode: sessionGuardMode,
      session_guard_exempt_ous: splitList(sessionGuardExemptOus),
      session_guard_exempt_groups: splitList(sessionGuardExemptGroups),
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

          {/* Switch 1: Network-Gated Campus Approval */}
          <h2 style={{ margin: "0 0 6px 0", fontSize: "18px", fontWeight: 600, color: "var(--dtg-text)" }}>
            Network-Gated Campus Self-Approval
          </h2>
          <p style={{ fontSize: "13px", color: "var(--dtg-text-secondary)", margin: "0 0 18px 0", lineHeight: 1.5 }}>
            Allows users connecting from authorized campus Wi-Fi / IP ranges to self-approve their personal or BYOD devices.
            <b> Security Notice:</b> To prevent unauthorized students or guests from registering rogue devices, scope this feature to specific Staff OUs or Groups.
          </p>

          <div style={{ marginBottom: "20px", display: "flex", alignItems: "center", gap: "10px" }}>
            <input
              id="enable-network-approval-checkbox"
              type="checkbox"
              checked={enableNetworkApproval}
              onChange={(e) => setEnableNetworkApproval(e.target.checked)}
              style={{ width: "18px", height: "18px", cursor: "pointer" }}
            />
            <label htmlFor="enable-network-approval-checkbox" style={{ fontWeight: 600, fontSize: "14px", color: "var(--dtg-text)", cursor: "pointer" }}>
              Enable Network-Gated Device Approval (Campus Wi-Fi)
            </label>
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

          <div style={{ marginBottom: "20px", display: "flex", alignItems: "center", gap: "10px" }}>
            <input
              id="enable-trust-chaining-checkbox"
              type="checkbox"
              checked={enableTrustChaining}
              onChange={(e) => setEnableTrustChaining(e.target.checked)}
              style={{ width: "18px", height: "18px", cursor: "pointer" }}
            />
            <label htmlFor="enable-trust-chaining-checkbox" style={{ fontWeight: 600, fontSize: "14px", color: "var(--dtg-text)", cursor: "pointer" }}>
              Enable Trust Chaining (Pairing Codes)
            </label>
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
                  className="dtg-input"
                />
              </div>
            </div>
          )}

          <hr style={{ border: "none", borderTop: "1px solid var(--dtg-border-subtle)", margin: "28px 0" }} />

          {/* Switch 3: Session Guard */}
          <h2 style={{ margin: "0 0 6px 0", fontSize: "18px", fontWeight: 600, color: "var(--dtg-text)" }}>
            Session Guard (Education Fundamentals Zero-Trust)
          </h2>
          <p style={{ fontSize: "13px", color: "var(--dtg-text-secondary)", margin: "0 0 18px 0", lineHeight: 1.5 }}>
            Autonomous session watch & circuit breaker for Education Fundamentals domains without Context-Aware Access (CAA).
            Monitors login audits and token refreshes, revoking sessions via <code>users.signOut</code> when unapproved or unattested devices connect.
          </p>

          <div style={{ marginBottom: "20px" }}>
            <label style={{ display: "block", fontWeight: 600, marginBottom: "8px", color: "var(--dtg-text)", fontSize: "14px" }}>
              Enforcement Mode:
            </label>
            <div style={{ display: "flex", gap: "14px", flexWrap: "wrap" }}>
              <label style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer", fontSize: "13px" }}>
                <input
                  type="radio"
                  name="session_guard_mode"
                  value="DISABLED"
                  checked={sessionGuardMode === "DISABLED"}
                  onChange={() => {
                    setSessionGuardMode("DISABLED");
                    setEnableSessionGuard(false);
                  }}
                />
                <span>Disabled (Off)</span>
              </label>

              <label style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer", fontSize: "13px" }}>
                <input
                  type="radio"
                  name="session_guard_mode"
                  value="AUDIT_SIMULATION"
                  checked={sessionGuardMode === "AUDIT_SIMULATION"}
                  onChange={() => {
                    setSessionGuardMode("AUDIT_SIMULATION");
                    setEnableSessionGuard(true);
                  }}
                />
                <span style={{ color: "var(--dtg-primary)", fontWeight: 600 }}>Audit / Simulation (Dry-Run Logs Only)</span>
              </label>

              <label style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer", fontSize: "13px" }}>
                <input
                  type="radio"
                  name="session_guard_mode"
                  value="ENFORCE_ACTIVE"
                  checked={sessionGuardMode === "ENFORCE_ACTIVE"}
                  onChange={() => {
                    setSessionGuardMode("ENFORCE_ACTIVE");
                    setEnableSessionGuard(true);
                  }}
                />
                <span style={{ color: "var(--dtg-danger)", fontWeight: 600 }}>Active Enforcement (Revoke via users.signOut)</span>
              </label>
            </div>
          </div>

          {sessionGuardMode !== "DISABLED" && (
            <div style={{ backgroundColor: "var(--dtg-surface-subtle)", padding: "16px", borderRadius: "8px", border: "1px solid var(--dtg-border-subtle)", marginBottom: "28px" }}>
              <div style={{ marginBottom: "16px" }}>
                <label style={{ display: "block", fontWeight: 600, marginBottom: "6px", color: "var(--dtg-text)", fontSize: "13px" }}>
                  Exempt Organizational Units (OUs):
                </label>
                <input
                  type="text"
                  placeholder="e.g. /Admins, /Staff"
                  value={sessionGuardExemptOus}
                  onChange={(e) => setSessionGuardExemptOus(e.target.value)}
                  className="dtg-input"
                />
                <span style={{ fontSize: "12px", color: "var(--dtg-text-secondary)", display: "block", marginTop: "4px" }}>
                  Users in exempt OUs will never be automatically signed out, even if logging in from personal devices.
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
                  className="dtg-input"
                />
              </div>
            </div>
          )}

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
