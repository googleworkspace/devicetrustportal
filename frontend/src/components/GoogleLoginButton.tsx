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
