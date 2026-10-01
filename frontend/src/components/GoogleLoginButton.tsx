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
import { GoogleOAuthProvider, GoogleLogin } from "@react-oauth/google";
import { getPublicConfig, sendClientLog } from "../services/api";

interface Props {
  onLoginSuccess: (email: string, token: string) => void;
}

export const GoogleLoginButton: React.FC<Props> = ({ onLoginSuccess }) => {
  const [clientId, setClientId] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    getPublicConfig()
      .then((data) => {
        if (data && data.google_client_id && data.google_client_id !== "INITIAL_DEPLOY_PENDING") {
          setClientId(data.google_client_id);
        } else {
          const envId = process.env.REACT_APP_GOOGLE_CLIENT_ID || "";
          if (envId && envId !== "INITIAL_DEPLOY_PENDING") {
            setClientId(envId);
          } else {
            sendClientLog("ERROR", "OAUTH_CLIENT_ID_MISSING", "No Google OAuth 2.0 Client ID configured in /api/config/public or environment");
          }
        }
      })
      .catch((err) => {
        console.warn("Could not load dynamic OAuth config:", err);
        sendClientLog("WARNING", "OAUTH_PUBLIC_CONFIG_ERROR", "Failed to fetch /api/config/public", {
          error: err?.message || String(err),
        });
        const envId = process.env.REACT_APP_GOOGLE_CLIENT_ID || "";
        if (envId && envId !== "INITIAL_DEPLOY_PENDING") {
          setClientId(envId);
        }
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div style={{ padding: "12px", color: "#5f6368", fontStyle: "italic", fontSize: "14px" }}>
        Initializing Google Sign-In SDK...
      </div>
    );
  }

  if (!clientId) {
    return (
      <div style={{ padding: "12px 16px", backgroundColor: "#fce8e6", color: "#c5221f", border: "1px solid #fad2cf", borderRadius: "6px", fontSize: "13px", marginTop: "15px", marginBottom: "15px" }}>
        Google OAuth 2.0 Client ID is not configured (`GOOGLE_CLIENT_ID`). Please complete Phase 2/3 of `deploy.sh` or set `GOOGLE_CLIENT_ID` in your service environment.
      </div>
    );
  }

  return (
    <GoogleOAuthProvider key={clientId} clientId={clientId}>
      <div style={{ marginTop: "15px", marginBottom: "15px" }}>
        <GoogleLogin
          onSuccess={(credentialResponse) => {
            const token = credentialResponse.credential;
            if (token) {
              localStorage.setItem("googleIdToken", token);
              // Parse email from JWT payload (middle part)
              try {
                const payload = JSON.parse(atob(token.split(".")[1]));
                const email = payload.email;
                if (email) {
                  localStorage.setItem("userEmail", email);
                  sendClientLog("INFO", "OAUTH_SIGNIN_SUCCESS", `User signed in with Google as ${email}`, {
                    email,
                    hd: payload.hd || null,
                    aud_prefix: typeof payload.aud === "string" ? payload.aud.slice(0, 16) : null,
                  });
                  onLoginSuccess(email, token);
                }
              } catch (e: any) {
                console.error("Failed to parse Google ID token payload", e);
                sendClientLog("ERROR", "OAUTH_TOKEN_PARSE_ERROR", "Failed to parse Google ID token payload", {
                  error: e?.message || String(e),
                });
              }
            }
          }}
          onError={() => {
            console.error("Google Sign-In Failed");
            sendClientLog("ERROR", "OAUTH_SIGNIN_ERROR", "Google Sign-In widget reported an authentication failure");
          }}
          useOneTap
        />
      </div>
    </GoogleOAuthProvider>
  );
};
