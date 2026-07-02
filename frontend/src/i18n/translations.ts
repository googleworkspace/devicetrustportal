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

export interface TranslationDictionary {
  portalTitle: string;
  subtitle: string;
  myDevicesTab: string;
  adminConfigTab: string;
  googleAuthTitle: string;
  googleAuthSubtitle: string;
  signInPrompt: string;
  signOut: string;
  signedInAs: string;
  myHardwareAssetsTitle: string;
  bulkRevokeSelected: string;
  loadingDevices: string;
  noApprovedDevices: string;
  deviceHeader: string;
  osHeader: string;
  idHeader: string;
  statusHeader: string;
  lastSyncHeader: string;
  actionsHeader: string;
  approveAction: string;
  revokeAction: string;
  approvedStatus: string;
  pendingStatus: string;
  revokedStatus: string;
  companyOwnedLabel: string;
  personalByodLabel: string;
  virtualAssetLabel: string;
  immutableAnchorLabel: string;
  serialImeiPrefix: string;
  confirmRevocationTitle: string;
  confirmRevocationBody: string;
  confirmRevocationWarning: string;
  cancelAction: string;
  yesRevokeAction: string;
  revokingAction: string;
}

export const translations: Record<string, TranslationDictionary> = {
  en: {
    portalTitle: "Device Trust Gateway Portal",
    subtitle: "Self-Service Google Workspace BYOD & Endpoint Verification Approval",
    myDevicesTab: "My Approved Devices",
    adminConfigTab: "Admin Configurations",
    googleAuthTitle: "Google Workspace Authentication",
    googleAuthSubtitle: "Sign in with your Google Workspace account to authorize live device approvals and manage configurations.",
    signInPrompt: "Please sign in with your Google Workspace corporate account to manage device access:",
    signOut: "Sign Out",
    signedInAs: "Active Session",
    myHardwareAssetsTitle: "My Hardware Assets",
    bulkRevokeSelected: "Bulk Revoke Selected",
    loadingDevices: "Retrieving your registered devices...",
    noApprovedDevices: "No Registered Hardware Assets Discovered",
    deviceHeader: "Hardware Model",
    osHeader: "Operating System",
    idHeader: "Identifier",
    statusHeader: "Approval State",
    lastSyncHeader: "Last Sync",
    actionsHeader: "Action",
    approveAction: "Approve",
    revokeAction: "Revoke",
    approvedStatus: "APPROVED",
    pendingStatus: "PENDING APPROVAL",
    revokedStatus: "REVOKED / UNAPPROVED",
    companyOwnedLabel: "🏢 Company Owned Asset",
    personalByodLabel: "👤 Personal BYOD",
    virtualAssetLabel: "Virtual Asset / EV Cert",
    immutableAnchorLabel: "🔒 Immutable Anchor",
    serialImeiPrefix: "Serial/IMEI:",
    confirmRevocationTitle: "⚠️ Confirm Access Revocation",
    confirmRevocationBody: "Are you absolutely sure you want to revoke approval for the selected device(s)?",
    confirmRevocationWarning: "This action will unapprove the device binding in Cloud Identity. Resources gated by Context-Aware Access policies will be immediately blocked.",
    cancelAction: "Cancel",
    yesRevokeAction: "Yes, Revoke Access",
    revokingAction: "Revoking Access...",
  },
  es: {
    portalTitle: "Portal de Confianza de Dispositivos",
    subtitle: "Aprobación de BYOD de Google Workspace y Verificación de Extremos",
    myDevicesTab: "Mis Dispositivos Aprobados",
    adminConfigTab: "Configuración de Administrador",
    googleAuthTitle: "Autenticación de Google Workspace",
    googleAuthSubtitle: "Inicie sesión con su cuenta de Google Workspace para autorizar aprobaciones y administrar configuraciones.",
    signInPrompt: "Inicie sesión con su cuenta corporativa de Google Workspace para administrar el acceso:",
    signOut: "Cerrar Sesión",
    signedInAs: "Sesión Activa",
    myHardwareAssetsTitle: "Mis Activos de Hardware",
    bulkRevokeSelected: "Revocación Masiva Seleccionada",
    loadingDevices: "Recuperando sus dispositivos registrados...",
    noApprovedDevices: "No se encontraron activos de hardware registrados",
    deviceHeader: "Modelo de Hardware",
    osHeader: "Sistema Operativo",
    idHeader: "Identificador",
    statusHeader: "Estado de Aprobación",
    lastSyncHeader: "Última Sincronización",
    actionsHeader: "Acción",
    approveAction: "Aprobar",
    revokeAction: "Revocar",
    approvedStatus: "APROBADO",
    pendingStatus: "PENDIENTE DE APROBACIÓN",
    revokedStatus: "REVOCADO / NO APROBADO",
    companyOwnedLabel: "🏢 Activo Corporativo",
    personalByodLabel: "👤 Personal (BYOD)",
    virtualAssetLabel: "Activo Virtual / Certificado EV",
    immutableAnchorLabel: "🔒 Ancla Inmutable",
    serialImeiPrefix: "Serie/IMEI:",
    confirmRevocationTitle: "⚠️ Confirmar Revocación de Acceso",
    confirmRevocationBody: "¿Está seguro de que desea revocar la aprobación para el dispositivo seleccionado?",
    confirmRevocationWarning: "Esta acción desaprobará el dispositivo en Cloud Identity. El acceso a recursos protegidos por Context-Aware Access se bloqueará de inmediato.",
    cancelAction: "Cancelar",
    yesRevokeAction: "Sí, Revocar Acceso",
    revokingAction: "Revocando Acceso...",
  },
  fr: {
    portalTitle: "Portail de Confiance des Appareils",
    subtitle: "Approbation BYOD Google Workspace et Vérification des Termineaux",
    myDevicesTab: "Mes Appareils Approuvés",
    adminConfigTab: "Configurations Administrateur",
    googleAuthTitle: "Authentification Google Workspace",
    googleAuthSubtitle: "Connectez-vous avec votre compte professionnel Google Workspace pour gérer l'accès des appareils.",
    signInPrompt: "Veuillez vous connecter avec votre compte professionnel Google Workspace :",
    signOut: "Déconnexion",
    signedInAs: "Session Active",
    myHardwareAssetsTitle: "Mes Actifs Matériels",
    bulkRevokeSelected: "Révocation Groupée de la Sélection",
    loadingDevices: "Récupération de vos appareils enregistrés...",
    noApprovedDevices: "Aucun actif matériel enregistré trouvé",
    deviceHeader: "Modèle Matériel",
    osHeader: "Système d'Exploitation",
    idHeader: "Identifiant",
    statusHeader: "État d'Approbation",
    lastSyncHeader: "Dernière Synchro",
    actionsHeader: "Action",
    approveAction: "Approuver",
    revokeAction: "Révoquer",
    approvedStatus: "APPROUVÉ",
    pendingStatus: "EN ATTENTE D'APPROBATION",
    revokedStatus: "RÉVOQUÉ / NON APPROUVÉ",
    companyOwnedLabel: "🏢 Actif de l'Entreprise",
    personalByodLabel: "👤 Personnel (BYOD)",
    virtualAssetLabel: "Actif Virtuel / Certificat EV",
    immutableAnchorLabel: "🔒 Ancre Immuable",
    serialImeiPrefix: "Série/IMEI:",
    confirmRevocationTitle: "⚠️ Confirmer la Révocation d'Accès",
    confirmRevocationBody: "Êtes-vous sûr de vouloir révoquer l'approbation pour l'appareil sélectionné ?",
    confirmRevocationWarning: "Cette action annulera l'approbation dans Cloud Identity. L'accès aux ressources protégées sera immédiatement bloqué.",
    cancelAction: "Annuler",
    yesRevokeAction: "Oui, Révoquer l'Accès",
    revokingAction: "Révocation en cours...",
  },
  ja: {
    portalTitle: "デバイストラスト ゲートウェイ ポータル",
    subtitle: "Google Workspace BYOD セルフサービス端末承認ポータル",
    myDevicesTab: "承認済みデバイス一覧",
    adminConfigTab: "管理者設定",
    googleAuthTitle: "Google Workspace 認証",
    googleAuthSubtitle: "Google Workspace アカウントでログインして、デバイスの承認や設定を管理してください。",
    signInPrompt: "企業用 Google Workspace アカウントでログインしてアクセスを管理してください:",
    signOut: "ログアウト",
    signedInAs: "ログイン中のアカウント",
    myHardwareAssetsTitle: "登録端末・ハードウェア一覧",
    bulkRevokeSelected: "選択した端末を一括取消",
    loadingDevices: "登録済み端末情報を取得しています...",
    noApprovedDevices: "承認済みのハードウェアアセットが見つかりません",
    deviceHeader: "ハードウェアモデル",
    osHeader: "OS / プラットフォーム",
    idHeader: "識別子 / シリアル",
    statusHeader: "承認ステータス",
    lastSyncHeader: "最終同期日時",
    actionsHeader: "操作",
    approveAction: "承認する",
    revokeAction: "信頼を取消",
    approvedStatus: "承認済み",
    pendingStatus: "承認待ち",
    revokedStatus: "取消済み / 未承認",
    companyOwnedLabel: "🏢 会社支給端末",
    personalByodLabel: "👤 個人所有 (BYOD)",
    virtualAssetLabel: "仮想端末 / EV 証明書",
    immutableAnchorLabel: "🔒 保護されたアセット",
    serialImeiPrefix: "シリアル / IMEI:",
    confirmRevocationTitle: "⚠️ アクセス権 (信頼) 取消の確認",
    confirmRevocationBody: "選択した端末のアクセス承認 (信頼ステータス) を本当に解除してよろしいですか？",
    confirmRevocationWarning: "この操作を実行すると Cloud Identity 上で端末承認が解除され、コンテキストアウェア アクセスで保護された企業リソースへの接続が直ちに遮断されます。",
    cancelAction: "キャンセル",
    yesRevokeAction: "はい、信頼を取消 (アクセス遮断)",
    revokingAction: "アクセス権を解除中...",
  },
};

export const getTranslator = (locale: string): TranslationDictionary => {
  const normalized = locale.toLowerCase().slice(0, 2);
  return translations[normalized] || translations["en"];
};
