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
  signInPrompt: string;
  signOut: string;
  signedInAs: string;
  loadingDevices: string;
  noApprovedDevices: string;
  deviceHeader: string;
  statusHeader: string;
  actionsHeader: string;
  approveAction: string;
  revokeAction: string;
  approvedStatus: string;
  pendingStatus: string;
  revokedStatus: string;
}

export const translations: Record<string, TranslationDictionary> = {
  en: {
    portalTitle: "Device Trust Gateway Portal",
    subtitle: "Self-Service Google Workspace BYOD & Endpoint Verification Approval",
    myDevicesTab: "My Approved Devices",
    adminConfigTab: "Admin Configurations",
    signInPrompt: "Please sign in with your Google Workspace corporate account to manage device access:",
    signOut: "Sign Out",
    signedInAs: "Signed in as:",
    loadingDevices: "Loading your registered device fleet...",
    noApprovedDevices: "No registered or approved devices found for this account.",
    deviceHeader: "Device Identifier / Name",
    statusHeader: "Trust State",
    actionsHeader: "Self-Service Action",
    approveAction: "Approve Device",
    revokeAction: "Revoke Trust",
    approvedStatus: "APPROVED",
    pendingStatus: "PENDING APPROVAL",
    revokedStatus: "REVOKED / UNAPPROVED",
  },
  es: {
    portalTitle: "Portal de Confianza de Dispositivos",
    subtitle: "Aprobación de BYOD de Google Workspace y Verificación de Extremos",
    myDevicesTab: "Mis Dispositivos Aprobados",
    adminConfigTab: "Configuraciones de Administrador",
    signInPrompt: "Inicie sesión con su cuenta corporativa de Google Workspace para administrar el acceso:",
    signOut: "Cerrar Sesión",
    signedInAs: "Conectado como:",
    loadingDevices: "Cargando su flota de dispositivos registrados...",
    noApprovedDevices: "No se encontraron dispositivos registrados o aprobados para esta cuenta.",
    deviceHeader: "Identificador / Nombre del Dispositivo",
    statusHeader: "Estado de Confianza",
    actionsHeader: "Acción de Autoservicio",
    approveAction: "Aprobar Dispositivo",
    revokeAction: "Revocar Confianza",
    approvedStatus: "APROBADO",
    pendingStatus: "PENDIENTE DE APROBACIÓN",
    revokedStatus: "REVOCADO / NO APROBADO",
  },
  fr: {
    portalTitle: "Portail de Confiance des Appareils",
    subtitle: "Approbation BYOD Google Workspace et Vérification des Termineaux",
    myDevicesTab: "Mes Appareils Approuvés",
    adminConfigTab: "Configurations Administrateur",
    signInPrompt: "Veuillez vous connecter avec votre compte professionnel Google Workspace :",
    signOut: "Déconnexion",
    signedInAs: "Connecté en tant que :",
    loadingDevices: "Chargement de votre parc d'appareils enregistrés...",
    noApprovedDevices: "Aucun appareil enregistré ou approuvé trouvé pour ce compte.",
    deviceHeader: "Identifiant / Nom de l'appareil",
    statusHeader: "État de Confiance",
    actionsHeader: "Action en Libre-Service",
    approveAction: "Approuver l'appareil",
    revokeAction: "Révoquer la confiance",
    approvedStatus: "APPROUVÉ",
    pendingStatus: "EN ATTENTE D'APPROBATION",
    revokedStatus: "RÉVOQUÉ / NON APPROUVÉ",
  },
  ja: {
    portalTitle: "デバイストラスト ゲートウェイ ポータル",
    subtitle: "Google Workspace BYOD セルフサービス端末承認ポータル",
    myDevicesTab: "承認済みデバイス一覧",
    adminConfigTab: "管理者設定",
    signInPrompt: "企業用 Google Workspace アカウントでログインしてデバイスアクセスを管理してください:",
    signOut: "ログアウト",
    signedInAs: "ログイン中のアカウント:",
    loadingDevices: "登録済みデバイス情報を読み込み中...",
    noApprovedDevices: "このアカウントに登録または承認されているデバイスは見つかりませんでした。",
    deviceHeader: "デバイス識別子 / 名称",
    statusHeader: "信頼ステータス",
    actionsHeader: "セルフサービス操作",
    approveAction: "デバイスを承認",
    revokeAction: "信頼を取消 (アクセス解除)",
    approvedStatus: "承認済み",
    pendingStatus: "承認待ち",
    revokedStatus: "取消済み / 未承認",
  },
};

export const getTranslator = (locale: string): TranslationDictionary => {
  const normalized = locale.toLowerCase().slice(0, 2);
  return translations[normalized] || translations["en"];
};
