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
import { getAdminConfig, updateAdminConfig, TenantConfig } from "../services/api";
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
        setLoading(false);
      } catch (e: any) {
        setError(`Access Denied: ${e.message || "Workspace Administrator privileges required."}`);
        setLoading(false);
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
      customer_id: "customers/my_customer",
      inactivity_threshold_days: Number(threshold),
      portal_admins: portalAdmins,
      revocation_action: "BLOCK",
      google_client_id: googleClientId.trim(),
      default_locale: defaultLocale,
    };

    try {
      await updateAdminConfig(updatedConfig);
      setMessage(t.configSaveSuccess);
      setSaving(false);
    } catch (err: any) {
      setError(`Update failed: ${err.message}`);
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div style={{ backgroundColor: "#f8f9fa", minHeight: "100vh", display: "flex", justifyContent: "center", alignItems: "center", fontFamily: "'Google Sans', Roboto, Arial, sans-serif" }}>
        <div style={{ textAlign: "center", color: "#5f6368", fontSize: "15px", fontWeight: 500 }}>
          {t.loadingAdminConfig}
        </div>
      </div>
    );
  }

  if (error && !config) {
    return (
      <div style={{ backgroundColor: "#f8f9fa", minHeight: "100vh", fontFamily: "'Google Sans', Roboto, Arial, sans-serif", padding: "40px 20px" }}>
        <div style={{ maxWidth: "600px", margin: "0 auto", backgroundColor: "#ffffff", padding: "32px", borderRadius: "8px", border: "1px solid #dadce0", boxShadow: "0 1px 2px 0 rgba(60,64,67,0.3)" }}>
          <a href="#/" style={{ color: "#1a73e8", textDecoration: "none", fontWeight: 500, fontSize: "14px", display: "inline-flex", alignItems: "center", gap: "6px" }}>
            &larr; {t.returnToDashboard}
          </a>
          <h1 style={{ color: "#d93025", marginTop: "20px", fontSize: "22px", fontWeight: 500 }}>{t.accessDeniedTitle}</h1>
          <p style={{ color: "#202124", fontSize: "15px", lineHeight: "1.5" }}>
            {error}
          </p>
          <div style={{ backgroundColor: "#f8f9fa", padding: "12px 16px", borderRadius: "6px", border: "1px solid #dadce0", fontSize: "13px", color: "#5f6368", marginTop: "20px" }}>
            {t.signedInAs}: <b style={{ color: "#202124" }}>{userEmail || "None"}</b>. {t.accessDeniedSessionNote}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ backgroundColor: "#f8f9fa", minHeight: "100vh", fontFamily: "'Google Sans', Roboto, Arial, sans-serif", color: "#202124" }}>
      {/* Google Cloud Console Top App Bar */}
      <header style={{ backgroundColor: "#ffffff", borderBottom: "1px solid #dadce0", padding: "12px 24px", display: "flex", justifyContent: "space-between", alignItems: "center", position: "sticky", top: 0, zIndex: 1000, boxShadow: "0 1px 2px 0 rgba(60,64,67,0.1)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <a href="#/" style={{ color: "#5f6368", textDecoration: "none", display: "flex", alignItems: "center" }} aria-label={t.returnToDashboard}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
              <path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/>
            </svg>
          </a>
          <div>
            <h1 style={{ margin: 0, fontSize: "18px", fontWeight: 500, letterSpacing: "-0.2px", color: "#202124" }}>{t.adminTitle}</h1>
            <div style={{ fontSize: "12px", color: "#5f6368", marginTop: "2px" }}>{t.adminSubHeader}</div>
          </div>
        </div>
        
        <a href="#/" style={{ padding: "6px 14px", backgroundColor: "#ffffff", color: "#1a73e8", border: "1px solid #dadce0", textDecoration: "none", borderRadius: "4px", fontWeight: 500, fontSize: "13px" }}>
          {t.backToPortal}
        </a>
      </header>

      <main style={{ padding: "28px 24px", maxWidth: "850px", margin: "0 auto" }}>
        {message && <div role="status" aria-live="polite" style={{ padding: "14px 16px", backgroundColor: "#e6f4ea", color: "#137333", border: "1px solid #ceead6", borderRadius: "6px", marginBottom: "20px", fontWeight: 500 }}>{message}</div>}
        {error && <div role="alert" style={{ padding: "14px 16px", backgroundColor: "#fce8e6", color: "#c5221f", border: "1px solid #fad2cf", borderRadius: "6px", marginBottom: "20px", fontWeight: 500 }}>{error}</div>}

        <form onSubmit={handleSubmit} style={{ border: "1px solid #dadce0", padding: "32px", borderRadius: "8px", backgroundColor: "#ffffff", boxShadow: "0 1px 2px 0 rgba(60,64,67,0.3)" }}>
          <h2 style={{ margin: "0 0 8px 0", fontSize: "18px", fontWeight: 500, color: "#202124" }}>{t.generalSecurityPolicies}</h2>
          <p style={{ fontSize: "13px", color: "#5f6368", margin: "0 0 24px 0" }}>{t.generalSecurityPoliciesDesc}</p>

          <div style={{ marginBottom: "24px" }}>
            <label htmlFor="inactivity-threshold" style={{ display: "block", fontWeight: 500, marginBottom: "6px", color: "#202124", fontSize: "14px" }}>{t.inactivityThresholdLabel}</label>
            <input
              id="inactivity-threshold"
              type="number"
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
              style={{ padding: "10px 12px", width: "100%", boxSizing: "border-box", fontSize: "15px", borderRadius: "4px", border: "1px solid #dadce0", color: "#202124" }}
            />
            <span style={{ fontSize: "12px", color: "#5f6368", display: "block", marginTop: "4px" }}>{t.inactivityThresholdHint}</span>
          </div>

          <div style={{ marginBottom: "32px" }}>
            <label htmlFor="default-locale-select" style={{ display: "block", fontWeight: 500, marginBottom: "6px", color: "#202124", fontSize: "14px" }}>{t.defaultLocaleLabel}</label>
            <select
              id="default-locale-select"
              value={defaultLocale}
              onChange={(e) => setDefaultLocale(e.target.value)}
              style={{ padding: "10px 12px", width: "100%", boxSizing: "border-box", fontSize: "14px", borderRadius: "4px", border: "1px solid #dadce0", backgroundColor: "#fff", color: "#202124", cursor: "pointer" }}
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
            <span style={{ fontSize: "12px", color: "#5f6368", display: "block", marginTop: "4px" }}>
              {t.defaultLocaleHint}
            </span>
          </div>

          <hr style={{ border: "none", borderTop: "1px solid #dadce0", margin: "32px 0" }} />

          <h2 style={{ margin: "0 0 8px 0", fontSize: "18px", fontWeight: 500, color: "#202124" }}>{t.delegatedAccessTitle}</h2>
          <p style={{ fontSize: "13px", color: "#5f6368", margin: "0 0 20px 0" }}>{t.delegatedAccessDesc}</p>

          <div style={{ marginBottom: "32px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
              <label style={{ display: "block", fontWeight: 500, color: "#202124", fontSize: "14px" }}>{t.authorizedAdminsLabel}</label>
              <button
                type="button"
                onClick={() => setShowAddAdminModal(true)}
                style={{ padding: "6px 14px", backgroundColor: "#ffffff", color: "#1a73e8", border: "1px solid #dadce0", borderRadius: "4px", cursor: "pointer", fontWeight: 500, fontSize: "13px", display: "inline-flex", alignItems: "center", gap: "6px", boxShadow: "0 1px 2px 0 rgba(60,64,67,0.1)" }}
              >
                {t.addAdminButton}
              </button>
            </div>

            {portalAdmins.length === 0 ? (
              <div style={{ padding: "14px", backgroundColor: "#f8f9fa", color: "#5f6368", fontSize: "13px", borderRadius: "4px", border: "1px solid #dadce0" }}>
                {t.noDelegatedAdmins}
              </div>
            ) : (
              <div style={{ border: "1px solid #dadce0", borderRadius: "6px", backgroundColor: "#fff", overflow: "hidden" }}>
                {portalAdmins.map((email, idx) => (
                  <div key={idx} style={{ padding: "12px 16px", borderBottom: idx < portalAdmins.length - 1 ? "1px solid #dadce0" : "none", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontFamily: "monospace", fontSize: "14px", color: "#202124" }}>{email}</span>
                    <button
                      type="button"
                      aria-label={`${t.removeAdminButton} ${email}`}
                      onClick={() => handleRemoveAdmin(email)}
                      style={{ padding: "6px 12px", backgroundColor: "#ffffff", color: "#d93025", border: "1px solid #dadce0", borderRadius: "4px", cursor: "pointer", fontSize: "12px", fontWeight: 500 }}
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
            style={{ padding: "12px 24px", backgroundColor: "#1a73e8", color: "white", border: "none", borderRadius: "4px", fontWeight: 500, cursor: saving ? "not-allowed" : "pointer", fontSize: "14px", width: "100%", boxShadow: "0 1px 2px 0 rgba(60,64,67,0.3)", opacity: saving ? 0.7 : 1 }}
          >
            {saving ? t.savingConfigsButton : t.saveConfigsButton}
          </button>
        </form>
      </main>

      {/* Add Authorized Administrator Modal Overlay */}
      {showAddAdminModal && (
        <div style={{ position: "fixed", top: 0, left: 0, width: "100vw", height: "100vh", backgroundColor: "rgba(0,0,0,0.5)", display: "flex", justifyContent: "center", alignItems: "center", zIndex: 9999 }}>
          <div style={{ backgroundColor: "#fff", padding: "28px", borderRadius: "8px", maxWidth: "450px", width: "90%", boxShadow: "0 4px 15px rgba(0,0,0,0.2)" }}>
            <h3 style={{ margin: "0 0 12px 0", fontSize: "18px", fontWeight: 500, color: "#202124" }}>{t.addAdminModalTitle}</h3>
            <p style={{ fontSize: "13px", color: "#5f6368", margin: "0 0 20px 0", lineHeight: "1.5" }}>
              {t.addAdminModalDesc}
            </p>
            
            <form onSubmit={handleAddAdmin}>
              <div style={{ marginBottom: "24px" }}>
                <label htmlFor="modal-admin-email" style={{ display: "block", fontWeight: 500, marginBottom: "6px", color: "#202124", fontSize: "13px" }}>{t.emailAddressLabel}</label>
                <input
                  id="modal-admin-email"
                  type="email"
                  required
                  placeholder="admin@yourdomain.com"
                  value={newAdminEmail}
                  onChange={(e) => setNewAdminEmail(e.target.value)}
                  style={{ padding: "10px 12px", width: "100%", boxSizing: "border-box", fontSize: "14px", borderRadius: "4px", border: "1px solid #dadce0", color: "#202124" }}
                />
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "12px" }}>
                <button
                  type="button"
                  onClick={() => {
                    setNewAdminEmail("");
                    setShowAddAdminModal(false);
                  }}
                  style={{ padding: "8px 16px", backgroundColor: "#ffffff", color: "#3c4043", border: "1px solid #dadce0", borderRadius: "4px", cursor: "pointer", fontWeight: 500, fontSize: "13px" }}
                >
                  {t.cancelAction}
                </button>
                <button
                  type="submit"
                  style={{ padding: "8px 16px", backgroundColor: "#1a73e8", color: "white", border: "none", borderRadius: "4px", cursor: "pointer", fontWeight: 500, fontSize: "13px" }}
                >
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
