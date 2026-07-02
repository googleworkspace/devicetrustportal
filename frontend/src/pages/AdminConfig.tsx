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
  const [revocationAction, setRevocationAction] = useState("DELETE");
  const [googleClientId, setGoogleClientId] = useState("");
  const [defaultLocale, setDefaultLocale] = useState("en");
  const [newAdminEmail, setNewAdminEmail] = useState("");

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
        setRevocationAction(data.revocation_action || "DELETE");
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

  const handleAddAdmin = () => {
    if (!newAdminEmail) return;
    const target = newAdminEmail.toLowerCase().trim();
    if (!portalAdmins.includes(target)) {
      setPortalAdmins([...portalAdmins, target]);
    }
    setNewAdminEmail("");
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
      revocation_action: revocationAction,
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
    return <div style={{ padding: "20px", fontFamily: "sans-serif" }}>Loading admin configurations...</div>;
  }

  if (error && !config) {
    return (
      <div style={{ padding: "20px", fontFamily: "sans-serif", maxWidth: "600px", margin: "0 auto" }}>
        <a href="#/" style={{ color: "#1a73e8", textDecoration: "none", fontWeight: "bold" }}>&larr; Back to Dashboard</a>
        <h1 style={{ color: "#d93025", marginTop: "20px" }}>Access Denied</h1>
        <p style={{ color: "#555" }}>
          {error}
        </p>
        <p style={{ fontSize: "14px", color: "#777" }}>
          Active Session: <b>{userEmail || "None"}</b>. Only authorized Google Workspace Super Administrators or delegated Portal Admins may manage tenant configurations.
        </p>
      </div>
    );
  }

  return (
    <div style={{ padding: "20px", fontFamily: "sans-serif", maxWidth: "800px", margin: "0 auto" }}>
      <a href="#/" style={{ color: "#1a73e8", textDecoration: "none", fontWeight: "bold" }}>&larr; Back to Dashboard</a>
      <h1 style={{ marginTop: "20px" }}>Admin Configurations</h1>
      <p style={{ color: "#555" }}>
        Dynamically manage tenant-wide security thresholds and delegated administrative access.
      </p>

      {message && <div role="status" aria-live="polite" style={{ padding: "14px 16px", backgroundColor: "#e6f4ea", color: "#137333", border: "1px solid #ceead6", borderRadius: "6px", marginBottom: "20px", fontWeight: 500 }}>{message}</div>}
      {error && <div role="alert" style={{ padding: "14px 16px", backgroundColor: "#fce8e6", color: "#c5221f", border: "1px solid #fad2cf", borderRadius: "6px", marginBottom: "20px", fontWeight: 500 }}>{error}</div>}

      <form onSubmit={handleSubmit} style={{ border: "1px solid #dadce0", padding: "28px", borderRadius: "8px", backgroundColor: "#ffffff", boxShadow: "0 1px 2px 0 rgba(60,64,67,0.3)" }}>
        <div style={{ marginBottom: "24px" }}>
          <label htmlFor="inactivity-threshold" style={{ display: "block", fontWeight: 500, marginBottom: "6px", color: "#202124" }}>Inactivity Threshold (Days):</label>
          <input
            id="inactivity-threshold"
            type="number"
            value={threshold}
            onChange={(e) => setThreshold(Number(e.target.value))}
            style={{ padding: "10px 12px", width: "100%", boxSizing: "border-box", fontSize: "15px", borderRadius: "4px", border: "1px solid #dadce0" }}
          />
          <span style={{ fontSize: "12px", color: "#5f6368", display: "block", marginTop: "4px" }}>Automated cron revocation triggers for BYOD devices idle longer than this window.</span>
        </div>

        <div style={{ marginBottom: "24px" }}>
          <label htmlFor="revocation-action" style={{ display: "block", fontWeight: 500, marginBottom: "6px", color: "#202124" }}>Revocation Action Behavior:</label>
          <select
            id="revocation-action"
            value={revocationAction}
            onChange={(e) => setRevocationAction(e.target.value)}
            style={{ padding: "10px 12px", width: "100%", boxSizing: "border-box", fontSize: "15px", borderRadius: "4px", border: "1px solid #dadce0", backgroundColor: "#fff", cursor: "pointer" }}
          >
            <option value="DELETE">DELETE API (Purge DeviceUser binding) — Recommended when 'Require Admin Approval' is ON</option>
            <option value="BLOCK">BLOCK API (Mark state as BLOCKED) — Explicitly blocks access without purging binding</option>
          </select>
          <span style={{ fontSize: "12px", color: "#5f6368", display: "block", marginTop: "4px" }}>
            Configures the backend action performed when unapproving devices or running inactivity cleanup. Using DELETE alongside Workspace Admin Console's 'Require Admin Approval' ensures new connections enter PENDING_APPROVAL.
          </span>
        </div>

        <div style={{ marginBottom: "24px" }}>
          <label htmlFor="oauth-client-id" style={{ display: "block", fontWeight: 500, marginBottom: "6px", color: "#202124" }}>Google OAuth 2.0 Client ID:</label>
          <input
            id="oauth-client-id"
            type="text"
            placeholder="1234567890-abcdef.apps.googleusercontent.com"
            value={googleClientId}
            onChange={(e) => setGoogleClientId(e.target.value)}
            style={{ padding: "10px 12px", width: "100%", boxSizing: "border-box", fontSize: "14px", fontFamily: "monospace", borderRadius: "4px", border: "1px solid #dadce0" }}
          />
          <span style={{ fontSize: "12px", color: "#5f6368", display: "block", marginTop: "4px" }}>
            Dynamically powers Google Sign-In across the frontend portal without requiring container recompilation or builds.
          </span>
        </div>

        <div style={{ marginBottom: "24px" }}>
          <label htmlFor="default-locale-select" style={{ display: "block", fontWeight: 500, marginBottom: "6px", color: "#202124" }}>Default Tenant UI Language (Localization Fallback):</label>
          <select
            id="default-locale-select"
            value={defaultLocale}
            onChange={(e) => setDefaultLocale(e.target.value)}
            style={{ padding: "10px 12px", width: "100%", boxSizing: "border-box", fontSize: "15px", borderRadius: "4px", border: "1px solid #dadce0", backgroundColor: "#fff", cursor: "pointer" }}
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

        {/* Delegated Portal Administrators List Manager */}
        <div style={{ marginBottom: "30px" }}>
          <label htmlFor="new-admin-email" style={{ display: "block", fontWeight: 500, marginBottom: "6px", color: "#202124" }}>Authorized Portal Administrators (Emails):</label>
          <p style={{ fontSize: "13px", color: "#5f6368", marginBottom: "12px", marginTop: 0 }}>
            Delegate access to manage these configurations to specific IT helpdesk or security staff without granting full Workspace Super Admin privileges.
          </p>
          
          <div style={{ display: "flex", gap: "10px", marginBottom: "16px" }}>
            <input
              id="new-admin-email"
              type="email"
              placeholder="helpdesk@example.com"
              value={newAdminEmail}
              onChange={(e) => setNewAdminEmail(e.target.value)}
              style={{ padding: "10px 12px", flexGrow: 1, fontSize: "14px", boxSizing: "border-box", borderRadius: "4px", border: "1px solid #dadce0" }}
            />
            <button
              type="button"
              onClick={handleAddAdmin}
              style={{ padding: "10px 20px", backgroundColor: "#137333", color: "white", border: "none", borderRadius: "4px", cursor: "pointer", fontWeight: 500, fontSize: "14px" }}
            >
              Add Admin
            </button>
          </div>

          {portalAdmins.length === 0 ? (
            <div style={{ padding: "12px", backgroundColor: "#f1f3f4", color: "#5f6368", fontSize: "13px", borderRadius: "4px", fontStyle: "italic" }}>
              No delegated portal administrators configured. Only Workspace Super Administrators have access.
            </div>
          ) : (
            <div style={{ border: "1px solid #e9ecef", borderRadius: "6px", backgroundColor: "#fff", overflow: "hidden" }}>
              {portalAdmins.map((email, idx) => (
                <div key={idx} style={{ padding: "10px 15px", borderBottom: idx < portalAdmins.length - 1 ? "1px solid #eee" : "none", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontFamily: "monospace", fontSize: "14px", color: "#202124" }}>{email}</span>
                  <button
                    type="button"
                    aria-label={`Remove administrator ${email}`}
                    onClick={() => handleRemoveAdmin(email)}
                    style={{ padding: "6px 10px", backgroundColor: "#fce8e6", color: "#c5221f", border: "1px solid #fad2cf", borderRadius: "4px", cursor: "pointer", fontSize: "12px", fontWeight: 500 }}
                  >
                    ✕ Remove
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        <button
          type="submit"
          style={{ padding: "14px 24px", backgroundColor: "#1a73e8", color: "white", border: "none", borderRadius: "6px", fontWeight: 500, cursor: "pointer", fontSize: "15px", width: "100%", boxShadow: "0 1px 2px 0 rgba(60,64,67,0.3)" }}
        >
          Save Configurations
        </button>
      </form>
    </div>
  );
};
