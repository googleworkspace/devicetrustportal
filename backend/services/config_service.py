# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import json
from typing import List
from pydantic import BaseModel, Field, model_validator
from dotenv import load_dotenv, set_key
from backend.services.cloud_identity import resolve_dwd_key_path

load_dotenv()

class TenantConfig(BaseModel):
    customer_id: str = Field(default="customers/my_customer", description="Google Workspace Customer Resource Name")
    inactivity_threshold_days: int = Field(default=90, description="Days of inactivity before automated revocation")
    portal_admins: List[str] = Field(default=[], description="List of user emails authorized to access Admin Config UI")
    revocation_action: str = Field(default="BLOCK", description="Action when revoking a device: 'DELETE' or 'BLOCK'")
    google_client_id: str = Field(default="", description="Google OAuth 2.0 Client ID for frontend Google Sign-In")
    default_locale: str = Field(default="en", description="Default UI language code fallback for end users (e.g., 'en', 'es', 'fr', 'ja')")
    trusted_ip_ranges: List[str] = Field(default=[], description="Trusted campus CIDR ranges for network-gated approvals")
    enable_network_approval: bool = Field(default=False, description="Master admin switch: Enable self-service device approval when connected to campus trusted Wi-Fi / IP ranges")
    network_approval_allowed_ous: List[str] = Field(default=[], description="Organizational Units authorized for network-gated device approval")
    network_approval_allowed_groups: List[str] = Field(default=[], description="Google Groups authorized for network-gated device approval")
    enable_trust_chaining: bool = Field(default=False, description="Master admin switch: Enable trust chaining pairing codes from approved devices")
    chaining_allowed_groups: List[str] = Field(default=[], description="Google Groups authorized to perform trust chaining")
    chaining_allowed_ous: List[str] = Field(default=[], description="Organizational Units authorized to perform trust chaining")
    chaining_denied_groups: List[str] = Field(default=[], description="Google Groups explicitly denied from trust chaining (overrides allow)")
    chaining_denied_ous: List[str] = Field(default=[], description="Organizational Units explicitly denied from trust chaining (overrides allow)")
    enforcement_mode: str = Field(
        default="DISABLED",
        description="Enforcement architecture mode: 'DISABLED' (default), 'SESSION_WATCH' (Education Fundamentals), 'CAA' (Education Standard/Plus), 'COOKIE_SENTINEL', or 'BOTH'",
    )
    session_watch_enabled: bool = Field(
        default=False,
        description="Enable CAA-Free Session Management & unapproved-device users.signOut circuit breaker for Education Fundamentals domains (Disabled by default)",
    )
    cookie_threat_detection_enabled: bool = Field(
        default=False,
        description="Enable Stolen Cookie & Token Threat Detection (Admin SDK 'token' stream + Cloud Hosting ASN & Foreign IP Pivot Sentinel, independent of unapproved-device session check)",
    )
    session_guard_watch_token_stream: bool = Field(
        default=False,
        description="Monitor Admin SDK 'token' audit stream to detect mid-session OAuth pivots on foreign IPs",
    )
    session_guard_block_hosting_asns: bool = Field(
        default=False,
        description="Automatically trigger users.signOut when token/session activity originates from datacenter/cloud hosting ASNs (Cloudflare, Latitude.sh, AWS, etc.)",
    )
    enable_session_guard: bool = Field(
        default=False,
        description="Master admin switch: Enable automated session monitoring and token revocation",
    )
    session_guard_mode: str = Field(
        default="DISABLED",
        description="Session Guard enforcement mode: 'DISABLED', 'AUDIT_SIMULATION', or 'ENFORCE_ACTIVE'",
    )
    session_guard_exempt_ous: List[str] = Field(
        default=[],
        description="Organizational Units exempt from automated session revocation",
    )
    session_guard_exempt_groups: List[str] = Field(
        default=[],
        description="Google Groups exempt from automated session revocation",
    )
    caa_enforcement_enabled: bool = Field(
        default=False,
        description="Enable Context-Aware Access (CAA) device approval integration for Education Standard & Plus domains (Disabled by default)",
    )
    session_watch_target_ous: List[str] = Field(
        default=[],
        description="Organizational Units scoped for CAA-Free Session Watch enforcement (e.g. ['/Students']). If empty and target_groups is empty, all non-exempt users are evaluated.",
    )
    session_watch_target_groups: List[str] = Field(
        default=[],
        description="Google Groups scoped for CAA-Free Session Watch enforcement (e.g. ['session-watch-pilot@gwfe.org'])",
    )
    cookie_threat_target_ous: List[str] = Field(
        default=[],
        description="Organizational Units scoped for Stolen Cookie & Token Threat Detection (e.g. ['/Staff', '/Students']). If empty and cookie_threat_target_groups is empty, all non-exempt users are evaluated.",
    )
    cookie_threat_target_groups: List[str] = Field(
        default=[],
        description="Google Groups scoped for Stolen Cookie & Token Threat Detection (e.g. ['cookie-sentinel-pilot@gwfe.org'])",
    )
    session_watch_exempt_admins: bool = Field(
        default=False,
        description="Optional Admin Safe-Harbor: exempt Workspace Super Admins and Portal Admins from users.signOut circuit breaker",
    )
    session_watch_dry_run: bool = Field(
        default=False,
        description="Audit-Only (Dry Run) mode: records AUDIT_WOULD_SIGN_OUT without executing users.signOut",
    )
    session_watch_onboarding_grace_minutes: int = Field(
        default=15,
        description="Minutes of onboarding grace lease granted when a user opens the portal to enroll or approve a personal device",
    )

    @model_validator(mode="after")
    def _sync_session_guard_aliases(self) -> "TenantConfig":
        if self.session_guard_mode == "AUDIT_SIMULATION":
            self.session_watch_dry_run = True
            self.enable_session_guard = True
            self.session_watch_enabled = True
        elif self.session_guard_mode == "ENFORCE_ACTIVE":
            self.enable_session_guard = True
            self.session_watch_enabled = True
        elif self.session_watch_enabled != self.enable_session_guard:
            merged_sw = bool(self.session_watch_enabled or self.enable_session_guard)
            self.session_watch_enabled = merged_sw
            self.enable_session_guard = merged_sw

        if (
            self.cookie_threat_detection_enabled
            or self.session_guard_watch_token_stream
            or self.session_guard_block_hosting_asns
        ):
            self.cookie_threat_detection_enabled = True
            self.session_guard_watch_token_stream = True
            self.session_guard_block_hosting_asns = True

        if self.session_watch_enabled and self.session_guard_mode == "DISABLED":
            self.session_guard_mode = (
                "AUDIT_SIMULATION" if self.session_watch_dry_run else "ENFORCE_ACTIVE"
            )

        if self.enforcement_mode == "DISABLED" and (
            self.session_watch_enabled
            or self.caa_enforcement_enabled
            or self.cookie_threat_detection_enabled
        ):
            self.enforcement_mode = _derive_enforcement_mode(
                self.session_watch_enabled,
                self.caa_enforcement_enabled,
                self.cookie_threat_detection_enabled,
            )
        return self


def _derive_enforcement_mode(
    session_watch_enabled: bool,
    caa_enforcement_enabled: bool,
    cookie_threat_detection_enabled: bool = False,
) -> str:
    if session_watch_enabled and caa_enforcement_enabled:
        return "BOTH"
    if session_watch_enabled:
        return "SESSION_WATCH"
    if caa_enforcement_enabled:
        return "CAA"
    if cookie_threat_detection_enabled:
        return "COOKIE_SENTINEL"
    return "DISABLED"


class ConfigService:
    def __init__(self):
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.secret_name = os.getenv("SECRET_NAME", "device_trust_gateway_config")
        self.use_secret_manager = os.getenv("USE_SECRET_MANAGER", "false").lower() == "true"
        
        if self.use_secret_manager:
            try:
                resolved_key = resolve_dwd_key_path()
                if not resolved_key and os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
                    os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
                from google.cloud import secretmanager
                self.sm_client = secretmanager.SecretManagerServiceClient()
            except Exception as e:
                print(f"Warning: Failed to initialize Secret Manager client: {e}. Falling back to .env")
                self.use_secret_manager = False

    def get_tenant_config(self) -> TenantConfig:
        env_admin = os.getenv("WORKSPACE_ADMIN_EMAIL", "").lower().strip()
        env_client_id = os.getenv("GOOGLE_CLIENT_ID", "") or os.getenv("REACT_APP_GOOGLE_CLIENT_ID", "")
        
        if self.use_secret_manager and self.project_id:
            try:
                name = f"projects/{self.project_id}/secrets/{self.secret_name}/versions/latest"
                response = self.sm_client.access_secret_version(request={"name": name})
                payload = response.payload.data.decode("UTF-8")
                data = json.loads(payload)
                sw_enabled = bool(data.get("session_watch_enabled", False))
                cookie_enabled = bool(
                    data.get("cookie_threat_detection_enabled", False)
                    or data.get("session_guard_watch_token_stream", False)
                    or data.get("session_guard_block_hosting_asns", False)
                )
                caa_enabled = bool(data.get("caa_enforcement_enabled", False))
                data["session_watch_enabled"] = sw_enabled
                data["cookie_threat_detection_enabled"] = cookie_enabled
                data["session_guard_watch_token_stream"] = cookie_enabled
                data["session_guard_block_hosting_asns"] = cookie_enabled
                data["enable_session_guard"] = bool(sw_enabled or cookie_enabled or data.get("enable_session_guard", False))
                data["caa_enforcement_enabled"] = caa_enabled
                data["enforcement_mode"] = _derive_enforcement_mode(sw_enabled, caa_enabled, cookie_enabled)
                config = TenantConfig(**data)
                if env_admin and env_admin not in [a.lower().strip() for a in config.portal_admins]:
                    config.portal_admins.append(env_admin)
                if not getattr(config, "google_client_id", "") and env_client_id:
                    config.google_client_id = env_client_id
                return config
            except Exception as e:
                print(f"Error reading from Secret Manager: {e}. Falling back to local config.")

        local_admins = json.loads(os.getenv("TENANT_PORTAL_ADMINS", '[]'))
        if env_admin and env_admin not in [a.lower().strip() for a in local_admins]:
            local_admins.append(env_admin)

        sw_enabled_env = os.getenv("TENANT_SESSION_WATCH_ENABLED", "false").lower() == "true"
        cookie_enabled_env = (
            os.getenv("TENANT_COOKIE_THREAT_DETECTION_ENABLED", "false").lower() == "true"
            or os.getenv("TENANT_SESSION_GUARD_WATCH_TOKEN_STREAM", "false").lower() == "true"
            or os.getenv("TENANT_SESSION_GUARD_BLOCK_HOSTING_ASNS", "false").lower() == "true"
        )
        enable_guard_env = (
            sw_enabled_env
            or cookie_enabled_env
            or os.getenv("TENANT_ENABLE_SESSION_GUARD", "false").lower() == "true"
        )
        caa_enabled_env = os.getenv("TENANT_CAA_ENFORCEMENT_ENABLED", "false").lower() == "true"
        derived_mode = _derive_enforcement_mode(sw_enabled_env, caa_enabled_env, cookie_enabled_env)
        exempt_admins_env = os.getenv("TENANT_SESSION_WATCH_EXEMPT_ADMINS", "false").lower() == "true"
        dry_run_env = os.getenv("TENANT_SESSION_WATCH_DRY_RUN", "false").lower() == "true"
        guard_mode_env = os.getenv("TENANT_SESSION_GUARD_MODE", "DISABLED").upper()

        return TenantConfig(
            customer_id=os.getenv("TENANT_CUSTOMER_ID", "customers/my_customer"),
            inactivity_threshold_days=int(os.getenv("TENANT_INACTIVITY_THRESHOLD", 90)),
            portal_admins=local_admins,
            revocation_action=os.getenv("TENANT_REVOCATION_ACTION", "BLOCK"),
            google_client_id=os.getenv("TENANT_GOOGLE_CLIENT_ID", "") or env_client_id,
            default_locale=os.getenv("TENANT_DEFAULT_LOCALE", "en"),
            trusted_ip_ranges=json.loads(os.getenv("TENANT_TRUSTED_IPS", '[]')),
            enable_network_approval=os.getenv("TENANT_ENABLE_NETWORK_APPROVAL", "false").lower() == "true",
            network_approval_allowed_ous=json.loads(os.getenv("TENANT_NETWORK_APPROVAL_OUS", '[]')),
            network_approval_allowed_groups=json.loads(os.getenv("TENANT_NETWORK_APPROVAL_GROUPS", '[]')),
            enable_trust_chaining=os.getenv("TENANT_ENABLE_TRUST_CHAINING", "false").lower() == "true",
            chaining_allowed_groups=json.loads(os.getenv("TENANT_CHAINING_GROUPS", '[]')),
            chaining_allowed_ous=json.loads(os.getenv("TENANT_CHAINING_OUS", '[]')),
            chaining_denied_groups=json.loads(os.getenv("TENANT_CHAINING_DENIED_GROUPS", '[]')),
            chaining_denied_ous=json.loads(os.getenv("TENANT_CHAINING_DENIED_OUS", '[]')),
            enforcement_mode=derived_mode,
            session_watch_enabled=sw_enabled_env,
            cookie_threat_detection_enabled=cookie_enabled_env,
            session_guard_watch_token_stream=cookie_enabled_env,
            session_guard_block_hosting_asns=cookie_enabled_env,
            enable_session_guard=enable_guard_env,
            session_guard_mode=guard_mode_env,
            session_guard_exempt_ous=json.loads(os.getenv("TENANT_SESSION_GUARD_EXEMPT_OUS", '[]')),
            session_guard_exempt_groups=json.loads(os.getenv("TENANT_SESSION_GUARD_EXEMPT_GROUPS", '[]')),
            caa_enforcement_enabled=caa_enabled_env,
            session_watch_target_ous=json.loads(os.getenv("TENANT_SESSION_WATCH_TARGET_OUS", '[]')),
            session_watch_target_groups=json.loads(os.getenv("TENANT_SESSION_WATCH_TARGET_GROUPS", '[]')),
            cookie_threat_target_ous=json.loads(os.getenv("TENANT_COOKIE_THREAT_TARGET_OUS", '[]')),
            cookie_threat_target_groups=json.loads(os.getenv("TENANT_COOKIE_THREAT_TARGET_GROUPS", '[]')),
            session_watch_exempt_admins=exempt_admins_env,
            session_watch_dry_run=dry_run_env,
            session_watch_onboarding_grace_minutes=int(os.getenv("TENANT_SESSION_WATCH_GRACE_MINUTES", 15)),
        )

    def update_tenant_config(self, config: TenantConfig) -> bool:
        sw_flag = bool(config.session_watch_enabled)
        cookie_flag = bool(
            config.cookie_threat_detection_enabled
            or config.session_guard_watch_token_stream
            or config.session_guard_block_hosting_asns
        )
        config.session_watch_enabled = sw_flag
        config.cookie_threat_detection_enabled = cookie_flag
        config.session_guard_watch_token_stream = cookie_flag
        config.session_guard_block_hosting_asns = cookie_flag
        config.enable_session_guard = bool(sw_flag or cookie_flag)
        if sw_flag or cookie_flag:
            config.session_guard_mode = (
                "AUDIT_SIMULATION" if config.session_watch_dry_run else "ENFORCE_ACTIVE"
            )
        else:
            config.session_guard_mode = "DISABLED"
        config.enforcement_mode = _derive_enforcement_mode(
            sw_flag, bool(config.caa_enforcement_enabled), cookie_flag
        )
        config_dict = config.model_dump()
        config_json = json.dumps(config_dict)

        if self.use_secret_manager and self.project_id:
            try:
                parent = f"projects/{self.project_id}/secrets/{self.secret_name}"
                self.sm_client.add_secret_version(
                    request={"parent": parent, "payload": {"data": config_json.encode("UTF-8")}}
                )
                return True
            except Exception as e:
                print(f"Error updating Secret Manager: {e}. Falling back to local .env update.")

        dotenv_path = os.path.join(os.getcwd(), ".env")
        if not os.path.exists(dotenv_path):
            with open(dotenv_path, "w", encoding="utf-8") as f:
                f.write("# Device Trust Gateway Configuration\n")

        set_key(dotenv_path, "TENANT_CUSTOMER_ID", config.customer_id)
        set_key(dotenv_path, "TENANT_INACTIVITY_THRESHOLD", str(config.inactivity_threshold_days))
        set_key(dotenv_path, "TENANT_PORTAL_ADMINS", json.dumps(config.portal_admins))
        set_key(dotenv_path, "TENANT_REVOCATION_ACTION", config.revocation_action)
        set_key(dotenv_path, "TENANT_GOOGLE_CLIENT_ID", config.google_client_id)
        set_key(dotenv_path, "TENANT_DEFAULT_LOCALE", config.default_locale)
        set_key(dotenv_path, "TENANT_TRUSTED_IPS", json.dumps(config.trusted_ip_ranges))
        set_key(dotenv_path, "TENANT_ENABLE_NETWORK_APPROVAL", str(config.enable_network_approval).lower())
        set_key(dotenv_path, "TENANT_NETWORK_APPROVAL_OUS", json.dumps(config.network_approval_allowed_ous))
        set_key(dotenv_path, "TENANT_NETWORK_APPROVAL_GROUPS", json.dumps(config.network_approval_allowed_groups))
        set_key(dotenv_path, "TENANT_ENABLE_TRUST_CHAINING", str(config.enable_trust_chaining).lower())
        set_key(dotenv_path, "TENANT_CHAINING_GROUPS", json.dumps(config.chaining_allowed_groups))
        set_key(dotenv_path, "TENANT_CHAINING_OUS", json.dumps(config.chaining_allowed_ous))
        set_key(dotenv_path, "TENANT_CHAINING_DENIED_GROUPS", json.dumps(config.chaining_denied_groups))
        set_key(dotenv_path, "TENANT_CHAINING_DENIED_OUS", json.dumps(config.chaining_denied_ous))
        set_key(dotenv_path, "TENANT_ENFORCEMENT_MODE", config.enforcement_mode)
        set_key(dotenv_path, "TENANT_SESSION_WATCH_ENABLED", "true" if config.session_watch_enabled else "false")
        set_key(dotenv_path, "TENANT_COOKIE_THREAT_DETECTION_ENABLED", "true" if config.cookie_threat_detection_enabled else "false")
        set_key(dotenv_path, "TENANT_SESSION_GUARD_WATCH_TOKEN_STREAM", "true" if config.session_guard_watch_token_stream else "false")
        set_key(dotenv_path, "TENANT_SESSION_GUARD_BLOCK_HOSTING_ASNS", "true" if config.session_guard_block_hosting_asns else "false")
        set_key(dotenv_path, "TENANT_ENABLE_SESSION_GUARD", "true" if config.enable_session_guard else "false")
        set_key(dotenv_path, "TENANT_SESSION_GUARD_MODE", config.session_guard_mode)
        set_key(dotenv_path, "TENANT_SESSION_GUARD_EXEMPT_OUS", json.dumps(config.session_guard_exempt_ous))
        set_key(dotenv_path, "TENANT_SESSION_GUARD_EXEMPT_GROUPS", json.dumps(config.session_guard_exempt_groups))
        set_key(dotenv_path, "TENANT_CAA_ENFORCEMENT_ENABLED", "true" if config.caa_enforcement_enabled else "false")
        set_key(dotenv_path, "TENANT_SESSION_WATCH_TARGET_OUS", json.dumps(config.session_watch_target_ous))
        set_key(dotenv_path, "TENANT_SESSION_WATCH_TARGET_GROUPS", json.dumps(config.session_watch_target_groups))
        set_key(dotenv_path, "TENANT_COOKIE_THREAT_TARGET_OUS", json.dumps(config.cookie_threat_target_ous))
        set_key(dotenv_path, "TENANT_COOKIE_THREAT_TARGET_GROUPS", json.dumps(config.cookie_threat_target_groups))
        set_key(dotenv_path, "TENANT_SESSION_WATCH_EXEMPT_ADMINS", "true" if config.session_watch_exempt_admins else "false")
        set_key(dotenv_path, "TENANT_SESSION_WATCH_DRY_RUN", "true" if config.session_watch_dry_run else "false")
        set_key(dotenv_path, "TENANT_SESSION_WATCH_GRACE_MINUTES", str(config.session_watch_onboarding_grace_minutes))
        
        load_dotenv(dotenv_path, override=True)
        return True

config_service = ConfigService()

