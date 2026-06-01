// Test IDs for ClearVault — single source of truth so tests stay stable.
export const NAV = {
  brand: "nav-brand",
  loginBtn: "nav-login-btn",
  signupBtn: "nav-signup-btn",
  logoutBtn: "nav-logout-btn",
  dashboardLink: "nav-dashboard-link",
  dealsLink: "nav-deals-link",
  uploadLink: "nav-upload-link",
};

export const LANDING = {
  hero: "landing-hero",
  heroCta: "landing-hero-cta",
  heroSecondary: "landing-hero-secondary",
  featureCard: (key) => `landing-feature-${key}`,
  pricingCard: (key) => `landing-pricing-${key}`,
  pricingCta: (key) => `landing-pricing-cta-${key}`,
};

export const AUTH = {
  loginForm: "login-form",
  loginEmail: "login-email-input",
  loginPassword: "login-password-input",
  loginSubmit: "login-submit-btn",
  signupForm: "signup-form",
  signupName: "signup-name-input",
  signupFirm: "signup-firm-input",
  signupEmail: "signup-email-input",
  signupPassword: "signup-password-input",
  signupSubmit: "signup-submit-btn",
};

export const DASHBOARD = {
  root: "dashboard-root",
  statDealsActive: "dashboard-stat-deals-active",
  statDocs: "dashboard-stat-documents",
  statRedFlags: "dashboard-stat-red-flags",
  statHighSeverity: "dashboard-stat-high-severity",
  recentActivity: "dashboard-recent-activity",
  dealsTable: "dashboard-deals-table",
  newDealBtn: "dashboard-new-deal-btn",
  commandPalette: "dashboard-command-palette",
};

export const DEAL = {
  newDealDialog: "deal-new-dialog",
  newDealName: "deal-new-name-input",
  newDealTarget: "deal-new-target-input",
  newDealSector: "deal-new-sector-input",
  newDealSize: "deal-new-size-input",
  newDealSubmit: "deal-new-submit-btn",
  detailRoot: "deal-detail-root",
  uploadBtn: "deal-detail-upload-btn",
  documentsTable: "deal-detail-documents-table",
};

export const UPLOAD = {
  dropzone: "upload-pdf-dropzone",
  fileInput: "upload-file-input",
  submit: "upload-submit-btn",
  dealSelect: "upload-deal-select",
  processingStatus: "upload-processing-status",
};

export const HOME = {
  emergentLink: "home-emergent-link",
};
