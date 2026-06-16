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

import React from "react";
import { GoogleOAuthProvider, GoogleLogin } from "@react-oauth/google";

interface Props {
  onLoginSuccess: (email: string, token: string) => void;
}

export const GoogleLoginButton: React.FC<Props> = ({ onLoginSuccess }) => {
  const clientId = process.env.REACT_APP_GOOGLE_CLIENT_ID || "1234567890-mockclient.apps.googleusercontent.com";

  return (
    <GoogleOAuthProvider clientId={clientId}>
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
                  onLoginSuccess(email, token);
                }
              } catch (e) {
                console.error("Failed to parse Google ID token payload", e);
                onLoginSuccess("oauth-user@example.com", token);
              }
            }
          }}
          onError={() => {
            console.error("Google Sign-In Failed");
          }}
          useOneTap
        />
      </div>
    </GoogleOAuthProvider>
  );
};
