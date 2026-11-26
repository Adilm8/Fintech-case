import type { Verdict } from "@/lib/types";

export type InfoRouteKey =
  | "howItWorks"
  | "help"
  | "support"
  | "security"
  | "about"
  | "terms"
  | "privacy";

export interface InfoStepItem {
  id: string;
  stepNumber: string;
  title: string;
  summary: string;
  bullets: string[];
  badge: string;
}

export interface InfoVerdictGuideItem {
  verdict: Verdict;
  title: string;
  whenShown: string;
  actionTitle: string;
  actionDetails: string;
  signingRule: string;
}

export interface InfoFaqItem {
  id: string;
  category: "verdicts" | "workflow" | "features" | "privacy";
  question: string;
  answer: string;
}

export interface InfoSecurityPillar {
  id: string;
  title: string;
  summary: string;
  points: string[];
  note?: string;
}

export interface InfoLegalSection {
  title: string;
  paragraphs: string[];
}

export interface InfoTeamRolePlaceholder {
  role: string;
  focus: string;
  tag: string;
}

export interface InfoRoadmapStage {
  phase: string;
  title: string;
  description: string;
  statusLabel: string;
}

export interface InfoDictionary {
  common: {
    backToApp: string;
    prototypeBadge: string;
    sectionNavAria: string;
    footerNavAria: string;
    openQueueCta: string;
    openHelpCta: string;
    openSecurityCta: string;
    openSupportCta: string;
    learnMore: string;
  };
  nav: Record<InfoRouteKey, string>;
  footer: {
    brandDescription: string;
    productGroupTitle: string;
    supportGroupTitle: string;
    legalGroupTitle: string;
    backToPayments: string;
    prototypeNotice: string;
    syntheticNote: string;
  };
  howItWorks: {
    title: string;
    subtitle: string;
    diagramTitle: string;
    diagramSubtitle: string;
    diagramAriaLabel: string;
    diagram: {
      inputTitle: string;
      inputItems: string[];
      precheckTitle: string;
      precheckDesc: string;
      layersTitle: string;
      layers: Array<{ title: string; detail: string }>;
      engineTitle: string;
      engineBadge: string;
      engineDesc: string;
      outputTitle: string;
      outputDesc: string;
      verdictLabels: Record<Verdict, string>;
      verdictActions: Record<Verdict, string>;
    };
    stepsTitle: string;
    stepsSubtitle: string;
    steps: InfoStepItem[];
    verdictsTitle: string;
    verdictsSubtitle: string;
    verdictColWhen: string;
    verdictColAction: string;
    verdictColSigning: string;
    verdicts: InfoVerdictGuideItem[];
    workflowTitle: string;
    workflowSubtitle: string;
    workflowItems: Array<{ title: string; description: string }>;
    ctaTitle: string;
    ctaDescription: string;
  };
  help: {
    title: string;
    subtitle: string;
    searchPlaceholder: string;
    searchAriaLabel: string;
    clearSearch: string;
    categoriesAriaLabel: string;
    categoryAll: string;
    categories: Record<"verdicts" | "workflow" | "features" | "privacy", string>;
    expandAll: string;
    collapseAll: string;
    shownCount: string;
    emptyTitle: string;
    emptyDescription: string;
    resetFilters: string;
    items: InfoFaqItem[];
    stillNeedHelpTitle: string;
    stillNeedHelpDescription: string;
  };
  support: {
    title: string;
    subtitle: string;
    prototypeBannerTitle: string;
    prototypeBannerDescription: string;
    formTitle: string;
    formDescription: string;
    nameLabel: string;
    namePlaceholder: string;
    emailLabel: string;
    emailPlaceholder: string;
    topicLabel: string;
    topics: Array<{ value: string; label: string }>;
    messageLabel: string;
    messagePlaceholder: string;
    submitButton: string;
    resetButton: string;
    validationError: string;
    emailValidationError: string;
    toastSuccessTitle: string;
    toastSuccessDescription: string;
    submittedBannerTitle: string;
    submittedBannerDescription: string;
    contactsTitle: string;
    contactsDescription: string;
    emailContactLabel: string;
    emailContactValue: string;
    phoneContactLabel: string;
    phoneContactValue: string;
    hoursLabel: string;
    hoursValue: string;
    quickLinksTitle: string;
    quickLinksDescription: string;
  };
  security: {
    title: string;
    subtitle: string;
    summaryStrip: Array<{ label: string; value: string; hint: string }>;
    pillars: InfoSecurityPillar[];
    secrecyComparisonTitle: string;
    secrecyComparisonSubtitle: string;
    clientSeesTitle: string;
    clientSeesItems: string[];
    analystSeesTitle: string;
    analystSeesItems: string[];
    secrecyDisclaimer: string;
    auditTitle: string;
    auditSubtitle: string;
    auditStoredTitle: string;
    auditStoredItems: string[];
    auditNotStoredTitle: string;
    auditNotStoredItems: string[];
    invoiceNoticeTitle: string;
    invoiceNoticeDescription: string;
    invoiceNoticePoints: string[];
    limitationsTitle: string;
    limitationsSubtitle: string;
    limitations: string[];
  };
  terms: {
    title: string;
    subtitle: string;
    bannerTitle: string;
    bannerDescription: string;
    updatedLabel: string;
    sections: InfoLegalSection[];
  };
  privacy: {
    title: string;
    subtitle: string;
    bannerTitle: string;
    bannerDescription: string;
    updatedLabel: string;
    sections: InfoLegalSection[];
  };
  about: {
    title: string;
    subtitle: string;
    problemTitle: string;
    problemLead: string;
    problemParagraphs: string[];
    problemStats: Array<{ value: string; label: string; source: string }>;
    statsDisclaimer: string;
    solutionTitle: string;
    solutionSubtitle: string;
    solutionCards: Array<{ title: string; description: string }>;
    teamTitle: string;
    teamSubtitle: string;
    teamPlaceholderNotice: string;
    teamMembers: InfoTeamRolePlaceholder[];
    roadmapTitle: string;
    roadmapSubtitle: string;
    roadmap: InfoRoadmapStage[];
  };
}
