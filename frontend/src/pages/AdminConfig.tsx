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

export const AdminConfig: React.FC = () => {
  const [config, setConfig] = useState<TenantConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const [threshold, setThreshold] = useState(90);
  const [portalAdmins, setPortalAdmins] = useState<string[]>([]);
  const [googleClientId, setGoogleClientId] = useState("");
  const [defaultLocale, setDefaultLocale] = useState("en");
  const [newAdminEmail, setNewAdminEmail] = useState("");
  const [showAddAdminModal, setShowAddAdminModal] = useState(false);

  const userEmail = localStorage.getItem("userEmail") || "";

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
      setMessage("Configuration successfully updated in GCP Secret Manager / local .env!");
    } catch (err: any) {
      setError(`Update failed: ${err.message}`);
    }
  };

  if (loading) {
    return (
      <div style={{ backgroundColor: "#f8f9fa", minHeight: "100vh", display: "flex", justifyContent: "center", alignItems: "center", fontFamily: "'Google Sans', Roboto, Arial, sans-serif" }}>
        <div style={{ textAlign: "center", color: "#5f6368", fontSize: "15px", fontWeight: 500 }}>Loading Google Workspace Admin configurations...</div>
      </div>
    );
  }

  if (error && !config) {
    return (
      <div style={{ backgroundColor: "#f8f9fa", minHeight: "100vh", fontFamily: "'Google Sans', Roboto, Arial, sans-serif", padding: "40px 20px" }}>
        <div style={{ maxWidth: "600px", margin: "0 auto", backgroundColor: "#ffffff", padding: "32px", borderRadius: "8px", border: "1px solid #dadce0", boxShadow: "0 1px 2px 0 rgba(60,64,67,0.3)" }}>
          <a href="#/" style={{ color: "#1a73e8", textDecoration: "none", fontWeight: 500, fontSize: "14px", display: "inline-flex", alignItems: "center", gap: "6px" }}>
            &larr; Return to Dashboard
          </a>
          <h1 style={{ color: "#d93025", marginTop: "20px", fontSize: "22px", fontWeight: 500 }}>Access Denied</h1>
          <p style={{ color: "#202124", fontSize: "15px", lineHeight: "1.5" }}>
            {error}
          </p>
          <div style={{ backgroundColor: "#f8f9fa", padding: "12px 16px", borderRadius: "6px", border: "1px solid #dadce0", fontSize: "13px", color: "#5f6368", marginTop: "20px" }}>
            Active Session: <b style={{ color: "#202124" }}>{userEmail || "None"}</b>. Only authorized Google Workspace Super Administrators or delegated Portal Admins may manage tenant configurations.
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
          <a href="#/" style={{ color: "#5f6368", textDecoration: "none", display: "flex", alignItems: "center" }} aria-label="Return to Dashboard">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
              <path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/>
            </svg>
          </a>
          <div>
            <h1 style={{ margin: 0, fontSize: "18px", fontWeight: 500, letterSpacing: "-0.2px", color: "#202124" }}>Google Workspace Tenant Settings</h1>
            <div style={{ fontSize: "12px", color: "#5f6368", marginTop: "2px" }}>Device Trust Gateway Administration</div>
          </div>
        </div>
        
        <a href="#/" style={{ padding: "6px 14px", backgroundColor: "#ffffff", color: "#1a73e8", border: "1px solid #dadce0", textDecoration: "none", borderRadius: "4px", fontWeight: 500, fontSize: "13px" }}>
          Back to Portal
        </a>
      </header>

      <main style={{ padding: "28px 24px", maxWidth: "850px", margin: "0 auto" }}>
        {message && <div role="status" aria-live="polite" style={{ padding: "14px 16px", backgroundColor: "#e6f4ea", color: "#137333", border: "1px solid #ceead6", borderRadius: "6px", marginBottom: "20px", fontWeight: 500 }}>{message}</div>}
        {error && <div role="alert" style={{ padding: "14px 16px", backgroundColor: "#fce8e6", color: "#c5221f", border: "1px solid #fad2cf", borderRadius: "6px", marginBottom: "20px", fontWeight: 500 }}>{error}</div>}

        <form onSubmit={handleSubmit} style={{ border: "1px solid #dadce0", padding: "32px", borderRadius: "8px", backgroundColor: "#ffffff", boxShadow: "0 1px 2px 0 rgba(60,64,67,0.3)" }}>
          <h2 style={{ margin: "0 0 8px 0", fontSize: "18px", fontWeight: 500, color: "#202124" }}>General Security Policies</h2>
          <p style={{ fontSize: "13px", color: "#5f6368", margin: "0 0 24px 0" }}>Configure automated cleanup thresholds and client integration credentials.</p>

          <div style={{ marginBottom: "24px" }}>
            <label htmlFor="inactivity-threshold" style={{ display: "block", fontWeight: 500, marginBottom: "6px", color: "#202124", fontSize: "14px" }}>Inactivity Threshold (Days):</label>
            <input
              id="inactivity-threshold"
              type="number"
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
              style={{ padding: "10px 12px", width: "100%", boxSizing: "border-box", fontSize: "15px", borderRadius: "4px", border: "1px solid #dadce0", color: "#202124" }}
            />
            <span style={{ fontSize: "12px", color: "#5f6368", display: "block", marginTop: "4px" }}>Automated cron revocation triggers for BYOD devices idle longer than this window.</span>
          </div>

          <div style={{ marginBottom: "32px" }}>
            <label htmlFor="default-locale-select" style={{ display: "block", fontWeight: 500, marginBottom: "6px", color: "#202124", fontSize: "14px" }}>Default Tenant UI Language (Localization Fallback):</label>
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
            </select>
            <span style={{ fontSize: "12px", color: "#5f6368", display: "block", marginTop: "4px" }}>
              Sets the default fallback language for end users accessing the portal when their browser language is unsupported or unset.
            </span>
          </div>

          <hr style={{ border: "none", borderTop: "1px solid #dadce0", margin: "32px 0" }} />

          <h2 style={{ margin: "0 0 8px 0", fontSize: "18px", fontWeight: 500, color: "#202124" }}>Delegated Access Management</h2>
          <p style={{ fontSize: "13px", color: "#5f6368", margin: "0 0 20px 0" }}>Delegate portal configuration access without granting full Workspace Super Admin privileges.</p>

          <div style={{ marginBottom: "32px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
              <label style={{ display: "block", fontWeight: 500, color: "#202124", fontSize: "14px" }}>Authorized Portal Administrators (Emails):</label>
              <button
                type="button"
                onClick={() => setShowAddAdminModal(true)}
                style={{ padding: "6px 14px", backgroundColor: "#ffffff", color: "#1a73e8", border: "1px solid #dadce0", borderRadius: "4px", cursor: "pointer", fontWeight: 500, fontSize: "13px", display: "inline-flex", alignItems: "center", gap: "6px", boxShadow: "0 1px 2px 0 rgba(60,64,67,0.1)" }}
              >
                + Add Administrator
              </button>
            </div>

            {portalAdmins.length === 0 ? (
              <div style={{ padding: "14px", backgroundColor: "#f8f9fa", color: "#5f6368", fontSize: "13px", borderRadius: "4px", border: "1px solid #dadce0" }}>
                No delegated portal administrators configured. Only Workspace Super Administrators have access.
              </div>
            ) : (
              <div style={{ border: "1px solid #dadce0", borderRadius: "6px", backgroundColor: "#fff", overflow: "hidden" }}>
                {portalAdmins.map((email, idx) => (
                  <div key={idx} style={{ padding: "12px 16px", borderBottom: idx < portalAdmins.length - 1 ? "1px solid #dadce0" : "none", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontFamily: "monospace", fontSize: "14px", color: "#202124" }}>{email}</span>
                    <button
                      type="button"
                      aria-label={`Remove administrator ${email}`}
                      onClick={() => handleRemoveAdmin(email)}
                      style={{ padding: "6px 12px", backgroundColor: "#ffffff", color: "#d93025", border: "1px solid #dadce0", borderRadius: "4px", cursor: "pointer", fontSize: "12px", fontWeight: 500 }}
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <button
            type="submit"
            style={{ padding: "12px 24px", backgroundColor: "#1a73e8", color: "white", border: "none", borderRadius: "4px", fontWeight: 500, cursor: "pointer", fontSize: "14px", width: "100%", boxShadow: "0 1px 2px 0 rgba(60,64,67,0.3)" }}
          >
            Save Configurations
          </button>
        </form>
      </main>

      {/* Add Authorized Administrator Modal Overlay */}
      {showAddAdminModal && (
        <div style={{ position: "fixed", top: 0, left: 0, width: "100vw", height: "100vh", backgroundColor: "rgba(0,0,0,0.5)", display: "flex", justifyContent: "center", alignItems: "center", zIndex: 9999 }}>
          <div style={{ backgroundColor: "#fff", padding: "28px", borderRadius: "8px", maxWidth: "450px", width: "90%", boxShadow: "0 4px 15px rgba(0,0,0,0.2)" }}>
            <h3 style={{ margin: "0 0 12px 0", fontSize: "18px", fontWeight: 500, color: "#202124" }}>Add Portal Administrator</h3>
            <p style={{ fontSize: "13px", color: "#5f6368", margin: "0 0 20px 0", lineHeight: "1.5" }}>
              Enter the Google Workspace corporate email address to grant delegated configuration access.
            </p>
            
            <form onSubmit={handleAddAdmin}>
              <div style={{ marginBottom: "24px" }}>
                <label htmlFor="modal-admin-email" style={{ display: "block", fontWeight: 500, marginBottom: "6px", color: "#202124", fontSize: "13px" }}>Email Address:</label>
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
                  Cancel
                </button>
                <button
                  type="submit"
                  style={{ padding: "8px 16px", backgroundColor: "#1a73e8", color: "white", border: "none", borderRadius: "4px", cursor: "pointer", fontWeight: 500, fontSize: "13px" }}
                >
                  Add Administrator
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
