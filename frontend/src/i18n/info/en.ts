import type { InfoDictionary } from "./types";

export const infoEn: InfoDictionary = {
  common: {
    backToApp: "Back to Payments to Sign",
    prototypeBadge: "ITU HACKATHON-2026 Prototype",
    sectionNavAria: "Information sections",
    footerNavAria: "Footer navigation",
    openQueueCta: "Open payment queue",
    openHelpCta: "Help & FAQ",
    openSecurityCta: "Security & data",
    openSupportCta: "Contact support",
    learnMore: "Learn more",
  },
  nav: {
    howItWorks: "How It Works",
    help: "Help & FAQ",
    security: "Security",
    support: "Support",
    about: "About",
    terms: "Terms",
    privacy: "Privacy",
  },
  footer: {
    brandDescription:
      "Pre-signing supplier payment verification module inside SME internet banking.",
    productGroupTitle: "Product",
    supportGroupTitle: "Help",
    legalGroupTitle: "Legal",
    backToPayments: "Payments to Sign",
    prototypeNotice:
      "Prototype for ITU HACKATHON-2026. Not an official bank service",
    syntheticNote:
      "This demo runs on synthetic data with no real transfers or digital signatures.",
  },
  howItWorks: {
    title: "How Business Shield Works",
    subtitle:
      "Before a payment order is signed, the system compares supplier details against your company's payment history and internal bank data, highlights changes character by character, and guides the next safe action.",
    diagramTitle: "Pre-Signing Verification Flow",
    diagramSubtitle:
      "All rules run over internal data and catalogs with zero external network calls — completing in milliseconds with clear \"was → became\" explanations.",
    diagramAriaLabel:
      "Business Shield flow diagram: payment or invoice input, requisites pre-checks, four analysis layers, rule engine, and five verdict outcomes",
    diagram: {
      inputTitle: "1. Payment to Verify",
      inputItems: [
        "Order from the signing queue or manual entry",
        "Auto-fill from a test invoice (PDF / photo)",
      ],
      precheckTitle: "2. Format & Checksum Pre-Checks",
      precheckDesc:
        "BIN/IIN (mod-11) and IIK (mod-97) checksums, bank code vs. BIC consistency against the NBK catalog.",
      layersTitle: "3. Four Verification Layers",
      layers: [
        {
          title: "Client History (12 mo.)",
          detail: "Usual IIKs, banks, KNPs, trusted accounts, duplicate invoices & structuring.",
        },
        {
          title: "Bank Internal Account Data",
          detail:
            "Account holder match, new-account signal & anonymized bank-wide signals — without disclosing secrecy.",
        },
        {
          title: "Lookalike Names & Symbols",
          detail: "Impersonated names, Latin/Greek homoglyphs, hidden Unicode, urgency phrases.",
        },
        {
          title: "Amounts & Payment Codes",
          detail: "Supplier median, MAD spread, client percentiles, and KBe entity matching.",
        },
      ],
      engineTitle: "4. Transparent Rule Engine",
      engineBadge: "≈ 3 ms · no external APIs",
      engineDesc:
        "Computes a 0–100 risk score, records the ruleset version, and builds a line-by-line \"in invoice / in history\" comparison table.",
      outputTitle: "5. Verdict & Signing Control",
      outputDesc:
        "The accountant sees exact reasons and advice; signing stays locked until an allowed verdict or director decision is recorded.",
      verdictLabels: {
        green: "Green",
        yellow: "Yellow",
        red: "Red",
        grey: "Grey",
        invalid: "Invalid",
      },
      verdictActions: {
        green: "Sign",
        yellow: "Director / verify",
        red: "Postpone",
        grey: "Check contract",
        invalid: "Fix details",
      },
    },
    stepsTitle: "What Is Checked Step by Step",
    stepsSubtitle:
      "Every check produces a plain-language reason and, when something differs, shows the exact comparison against your supplier's established details.",
    steps: [
      {
        id: "requisites",
        stepNumber: "01",
        badge: "Format & Catalogs",
        title: "Requisites Pre-Checks & Budget Fast-Path",
        summary:
          "Before evaluating fraud risk, the engine verifies that the entered requisites are structurally valid and free of typos.",
        bullets: [
          "BIN/IIN mod-11 checksum & date prefix validation and KZ IIK (ISO 13616 mod-97) checksum validation.",
          "Verification that the 3-digit bank code inside the IIK matches the entered BIC using the NBK bank catalog.",
          "Existence check for internal bank accounts and entity-type consistency (legal entity vs. individual) with optional KBe.",
          "Payments to Treasury and State Corporation \"Government for Citizens\" accounts with valid details receive a green verdict.",
        ],
      },
      {
        id: "history",
        stepNumber: "02",
        badge: "Company History",
        title: "Requisites Compared Against Payment History",
        summary:
          "Standard account validation confirms an account exists, not whether you paid it before. Business Shield compares each order against your 12-month payment history.",
        bullets: [
          "Detects a new IIK or bank change for a known supplier (switching to another bank at or above the supplier median escalates to red).",
          "Flags if the entered IIK was previously used by a different counterparty.",
          "Recognizes trusted accounts previously confirmed by your director with a comment.",
          "Short-term check memory: catches repeated invoice numbers within 90 days, structuring (3+ payments in 72 hours), and 7-day accumulated transfers to a new recipient.",
        ],
      },
      {
        id: "bank-data",
        stepNumber: "03",
        badge: "Secrecy Preserved",
        title: "Bank's Own Internal Account Data",
        summary:
          "When the recipient account is held within the bank, ownership is verified internally without exposing another customer's name or details.",
        bullets: [
          "If a new internal account belongs to the same BIN as a known supplier, the bank confirms the match (amount checks still run).",
          "If the internal account belongs to a different company, a blocking red signal fires with neutral wording — never revealing the owner's name, BIN, or opening date.",
          "Flags recently opened internal accounts without exposing the exact opening date to the client.",
          "Anonymized bank-wide signals (implemented on synthetic data in bank_signals.json): aggregated complaints from other clients on an IIK, first-time inflows to a fresh account from many unrelated payers (exempting established bank-known BINs), and a mule watchlist — never disclosing payer names or BINs.",
          "Detailed internal account data is separated into the \"Antifraud analyst view\".",
        ],
      },
      {
        id: "lookalike",
        stepNumber: "04",
        badge: "Character Analysis",
        title: "Lookalike Names & Hidden Characters",
        summary:
          "Attackers frequently register lookalike companies or substitute a single letter so an accountant overlooks the change.",
        bullets: [
          "Normalizes legal forms (LLP/ТОО, IE/ИП, etc.) and strips invisible Unicode control and combining characters.",
          "Detects visual clones: Latin or Greek lookalikes inside Cyrillic words, Kazakh-Russian swaps (e.g. \"ұ\" vs \"у\"), digits replacing letters, transliterations, and suffix variants.",
          "Highlights altered and hidden characters right inside the \"In invoice / In history\" comparison table.",
          "Detects urgency and \"new requisites\" cues in payment purposes across Russian, Kazakh (\"шұғыл\", \"жедел\"), and English.",
        ],
      },
      {
        id: "amounts",
        stepNumber: "05",
        badge: "Amounts & Codes",
        title: "Amount Anomalies, KBe/KNP & Counterparty Age",
        summary:
          "Each supplier's payment profile is modeled individually so normal seasonal spikes stay calm while abrupt outliers stand out.",
        bullets: [
          "Compares the payment amount against that supplier's historical median, MAD spread, and percentiles.",
          "For new recipients, compares against your company's 90th percentile (large first payments prompt director review or escalate to yellow/red).",
          "Evaluates optional KBe and KNP codes — such as KBe 17 (legal entity) paired with an individual IIN, or an unusual KNP for a known supplier.",
          "Flags recently registered BINs and mismatches between the entered name and taxpayer registry.",
        ],
      },
    ],
    verdictsTitle: "Verdict Colors & Recommended Actions",
    verdictsSubtitle:
      "Signing stays locked until an allowed verdict or confirmation is present. Here is what each of the five verdicts means.",
    verdictColWhen: "When it appears",
    verdictColAction: "Recommended action",
    verdictColSigning: "Signing requirement",
    verdicts: [
      {
        verdict: "green",
        title: "Same as before",
        whenShown:
          "Details and amount match your payment history, the account is confirmed by the bank or your director, or it is a valid budget payment.",
        actionTitle: "Sign",
        actionDetails:
          "No extra verification needed — you can proceed directly to signing the payment order.",
        signingRule: "Signing is allowed immediately.",
      },
      {
        verdict: "yellow",
        title: "Changes detected",
        whenShown:
          "Changes or warnings were found: a new IIK or bank for a known supplier, a repeated invoice number, an unusual amount, or urgency phrasing.",
        actionTitle: "Send to director",
        actionDetails:
          "Call the supplier using the phone number from your contract (not from the email) and route the payment to the director for approval.",
        signingRule:
          "Allowed after director approval or after the accountant confirms phone verification (in prod mode, if any counterparty identity signal fired, phone confirmation is blocked and director approval is required).",
      },
      {
        verdict: "red",
        title: "Likely spoofing",
        whenShown:
          "A blocking fact or high risk score was triggered: an internal bank account belongs to another company, a lookalike supplier name, a bank switch at usual/high amount, or an extreme amount spike.",
        actionTitle: "Postpone & verify",
        actionDetails:
          "Do not sign immediately. Postpone the payment, verify the invoice through an independent channel, and escalate to the director if needed.",
        signingRule:
          "Only after explicit director approval with a mandatory comment (at least 10 non-whitespace characters).",
      },
      {
        verdict: "grey",
        title: "No history",
        whenShown:
          "First payment to a new recipient with no transactions in the past 12 months and no critical discrepancies in the requisites.",
        actionTitle: "Verify against contract",
        actionDetails:
          "Double-check BIN/IIN, IIK, and amount against the signed contract. If the amount exceeds your 90th percentile, the system recommends director review.",
        signingRule:
          "Allowed after accountant phone-verification confirmation or director approval (in prod mode, any counterparty identity signal requires director approval).",
      },
      {
        verdict: "invalid",
        title: "Invalid details",
        whenShown:
          "BIN/IIN or IIK checksum fails, the BIC is invalid, the bank code in the IIK does not match the BIC, or the internal bank account does not exist.",
        actionTitle: "Fix payment details",
        actionDetails:
          "Click \"Fix payment details\", correct the highlighted field, and re-run verification.",
        signingRule:
          "Both signing and director approval are blocked until the error is corrected.",
      },
    ],
    workflowTitle: "From Supplier Invoice to Signature",
    workflowSubtitle:
      "How supporting tools fit into daily accountant and director workflows.",
    workflowItems: [
      {
        title: "Invoice Upload (PDF or Photo)",
        description:
          "In the New Payment dialog, upload a test invoice (PDF, PNG, JPEG, or WebP up to 10 MB) to prefill payment fields, with a mandatory verification checkbox whenever confidence is low or warnings appear.",
      },
      {
        title: "Director Approvals & Trusted Accounts",
        description:
          "Directors review the same comparison table and signals. For a yellow account-change payment — or a red verdict whose only risk signals are IIK and bank change (no blocking or other risk signals) — they can check \"Trust this account\" with a comment of 10+ characters so future payments turn green.",
      },
      {
        title: "Audit Log & Three Languages",
        description:
          "Every verification and decision is appended to the audit log (request hash, ruleset version, verdict, rule IDs). Both UI and API responses work in Russian, Kazakh, and English.",
      },
    ],
    ctaTitle: "Try It on Built-In Demo Scenarios",
    ctaDescription:
      "The queue includes 10 representative cases: repeat payment, bank switch, Latin homoglyph letter, another company's account, new supplier, and an IIK typo.",
  },
  help: {
    title: "Help & Frequently Asked Questions",
    subtitle:
      "Clear answers about verdicts, legitimate bank changes, director approvals, trusted accounts, invoice upload, languages, and banking secrecy.",
    searchPlaceholder: "Search questions and answers...",
    searchAriaLabel: "Search FAQ",
    clearSearch: "Clear search",
    categoriesAriaLabel: "Question categories",
    categoryAll: "All questions",
    categories: {
      verdicts: "Verdicts & signals",
      workflow: "Approvals & accounts",
      features: "Features & languages",
      privacy: "Secrecy & prototype",
    },
    expandAll: "Expand all",
    collapseAll: "Collapse all",
    shownCount: "Showing {shown} of {total} questions",
    emptyTitle: "No matching questions found",
    emptyDescription:
      "Try another keyword or switch back to \"All questions\".",
    resetFilters: "Reset filters",
    items: [
      {
        id: "why-yellow",
        category: "verdicts",
        question: "Why did a payment receive a yellow \"Changes detected\" verdict?",
        answer:
          "A yellow verdict means the payment differs from your established history with that supplier or has warning signs — such as a new IIK or bank, a duplicate invoice number within 90 days, an unusual amount, or urgency wording like \"urgent / new requisites\". Open the check screen to see the exact reason under \"Why\" and the side-by-side comparison table.",
      },
      {
        id: "supplier-changed-bank",
        category: "workflow",
        question: "What if the supplier genuinely changed their bank or account?",
        answer:
          "A first unconfirmed account switch always triggers an alert (yellow, or red if the bank changed and the amount is at or above the supplier's median), because requisites alone cannot distinguish a real switch from spoofing. Call the supplier using the verified number from your contract (never from the new email), then send the payment to the director. The director can approve with a comment of 10+ characters and check \"Trust this account\" — even on a red verdict when the only risk signals are IIK and bank change with no other risk or blocking signals — so future payments to that account turn green.",
      },
      {
        id: "director-confirmation",
        category: "workflow",
        question:
          "What does director confirmation do and when is a comment required?",
        answer:
          "In the Approvals section, the director reviews all differences, risk reasons, and the accountant's note, then approves or rejects the payment. Director approval unlocks signing for yellow, grey, and red payments. A mandatory comment of at least 10 non-whitespace characters is required when approving a red verdict or marking an account as trusted. No comment is required to reject, and invalid payments cannot be approved.",
      },
      {
        id: "trusted-accounts",
        category: "workflow",
        question:
          "How do trusted accounts work, and can a red payment be marked trusted?",
        answer:
          "Checking \"Trust this account\" links the new IIK to that supplier so subsequent payments immediately receive a green verdict labeled \"New account confirmed by director\". Trust can be granted — always with a mandatory director comment (10+ characters) — on a yellow IIK/bank-change payment, and also on a red verdict when the only risk signals are IIK and bank change (no blocking or other risk signals). Whenever a red verdict includes any other risk or blocking signal (such as a lookalike name, third-party bank account, or watchlist match), trust stays unavailable.",
      },
      {
        id: "invoice-upload",
        category: "features",
        question:
          "How does supplier invoice upload (PDF or photo) work, and why is confirmation sometimes required?",
        answer:
          "Inside the New Payment form, you can drag and drop or choose an invoice file (PDF, PNG, JPEG, or WebP up to 10 MB). The recognition service extracts recipient name, BIN/IIN, IIK, BIC, amount, purpose, and KBe/KNP (with template-based fallback) and validates checksums. If recognition confidence is low or warnings appear, you must check \"I verified the details against the invoice\" before submitting. Because the file is sent for recognition, upload test invoices only in this prototype.",
      },
      {
        id: "languages",
        category: "features",
        question: "Which languages are supported and how do I switch?",
        answer:
          "Business Shield supports Russian (РУС), Kazakh in Cyrillic (ҚАЗ), and English (ENG). Use the language switcher in the top header; your selection is saved in the browser. Switching languages updates both the interface and server-generated headlines, signal explanations, and advice. Risk rules also handle Kazakh characters in lookalike detection and urgency words across all three languages.",
      },
      {
        id: "banking-secrecy",
        category: "privacy",
        question:
          "Does checking internal bank accounts violate banking secrecy?",
        answer:
          "Account ownership is checked strictly inside the bank. Clients only receive a mismatch fact (\"Account belongs to another company\") — never the third-party holder's name, BIN, or opening date. Internal details are isolated in the antifraud analyst view (toggled on the Approvals screen in demo mode, and restricted to authenticated bank analyst sessions in production). Final client wording is subject to bank compliance approval.",
      },
      {
        id: "why-red",
        category: "verdicts",
        question: "Why did a payment turn red, and can it still be processed?",
        answer:
          "A red \"Likely spoofing\" verdict is issued for a blocking fact (such as an internal bank account belonging to another company) or a high risk score (lookalike name, hidden symbols, bank change on a typical/large amount, or extreme amount spike). An accountant cannot sign a red payment alone — it should be postponed and verified. If confirmed legitimate, it can only be signed after explicit director approval with a mandatory comment.",
      },
      {
        id: "why-grey",
        category: "verdicts",
        question: "What does a grey \"No history\" verdict mean?",
        answer:
          "Grey indicates a first payment to a recipient with no payments in your 12-month history and no critical requisite errors. Normally, it can be signed after checking the contract and confirming phone verification. If the amount exceeds your company's 90th percentile, the primary recommendation shifts to director approval; amounts exceeding 3× or 10× that percentile escalate to yellow or red.",
      },
      {
        id: "invalid-requisites",
        category: "verdicts",
        question: "What does \"Invalid details\" mean and how do I fix it?",
        answer:
          "This verdict appears when formal validation fails: a bad BIN/IIN or IIK checksum, an unknown BIC, a mismatch between the IIK bank code and the BIC, or a nonexistent internal bank account. Neither signing nor approval is allowed. Click \"Fix payment details\" on the check screen to edit the highlighted field and re-verify in place.",
      },
      {
        id: "lookalike-names",
        category: "verdicts",
        question:
          "How does the system spot a single swapped letter or invisible character?",
        answer:
          "Before matching supplier names, the engine strips invisible Unicode format and combining characters, normalizes legal forms, and maps visually confusable characters across scripts (Latin or Greek inside Cyrillic, Kazakh \"ұ\" vs \"у\", digits replacing letters, transliteration). Altered characters are highlighted individually in the comparison table and Attack Console.",
      },
      {
        id: "seasonal-amounts",
        category: "verdicts",
        question:
          "Our supplier has large seasonal invoices. Will those trigger false alarms?",
        answer:
          "Amounts are evaluated against each individual supplier's history (median, MAD spread, and percentiles). If similarly large payments have occurred before to the same supplier's usual account, the payment stays green. Alerts trigger when an amount sharply exceeds the historical range or combines with another risk signal such as an account change.",
      },
      {
        id: "budget-payments",
        category: "features",
        question: "How are tax and government budget payments handled?",
        answer:
          "Payments to Treasury and State Corporation \"Government for Citizens\" accounts undergo full BIN, IIK, and BIC validation first. Once requisites pass, they receive a green verdict without triggering supplier-spoofing rules.",
      },
      {
        id: "demo-vs-production",
        category: "privacy",
        question:
          "How does this prototype differ from a full production bank rollout?",
        answer:
          "Demo mode uses synthetic data for a single sample company, simulates signing without live digital signatures (NCALayer), and keeps approvals and trusted accounts in memory (resettable via \"Reset demo\"). The same repository also includes a local production-like mode (APP_MODE=prod) with SQLite, login and roles, a server-enforced signing gate, hash-chained audit logs, and 1C/CSV batch import (tested only on synthetic data). Live bank rollout adds PostgreSQL, bank SSO/JWT authentication, pre-NCALayer integration, validation on real 1C exports, and a shadow-mode pilot.",
      },
    ],
    stillNeedHelpTitle: "Still have a question?",
    stillNeedHelpDescription:
      "Explore the verification flow diagram on How It Works or test the local feedback form on Support.",
  },
  support: {
    title: "Support",
    subtitle:
      "Demonstration contact page for the Business Shield prototype. Submissions are handled locally in your browser.",
    prototypeBannerTitle: "Local prototype form",
    prototypeBannerDescription:
      "Submitting this form only shows a local success toast — nothing is transmitted or stored on any server. Please do not enter real bank details, passwords, or personal information.",
    formTitle: "Send a Test Inquiry",
    formDescription:
      "Ask about payment verification verdicts, director approvals, or demo scenarios.",
    nameLabel: "Your name",
    namePlaceholder: "e.g., Aigul Serikova",
    emailLabel: "Contact email",
    emailPlaceholder: "name@example.kz",
    topicLabel: "Topic",
    topics: [
      { value: "verdict", label: "Question about a payment verdict" },
      { value: "approvals", label: "Director approvals & trusted accounts" },
      { value: "invoice", label: "Supplier invoice upload & recognition" },
      { value: "security", label: "Security & audit log" },
      { value: "other", label: "Other prototype question" },
    ],
    messageLabel: "Message",
    messagePlaceholder:
      "Describe the scenario or demo payment ID (for example, Q-002 or Q-003)...",
    submitButton: "Submit inquiry",
    resetButton: "Clear form",
    validationError: "Please fill in your name, a valid email, and a message.",
    emailValidationError: "Please enter a valid email address.",
    toastSuccessTitle: "Inquiry submitted (locally)",
    toastSuccessDescription:
      "Prototype demo only: no message was sent anywhere.",
    submittedBannerTitle: "Local confirmation triggered",
    submittedBannerDescription:
      "This form ran solely in your browser with no network request. You can clear the fields to test another submission.",
    contactsTitle: "Placeholder Contacts",
    contactsDescription:
      "Provided strictly as hackathon prototype placeholders — not associated with any real bank.",
    emailContactLabel: "Email (placeholder)",
    emailContactValue: "support@example.kz",
    phoneContactLabel: "Phone (placeholder)",
    phoneContactValue: "+7 (700) 000-00-00 — test number",
    hoursLabel: "Sample hours",
    hoursValue: "Mon–Fri, 09:00–18:00 (Astana time)",
    quickLinksTitle: "Helpful Pages",
    quickLinksDescription:
      "You may find the answer right away in the prototype documentation:",
  },
  security: {
    title: "Security & Data Handling",
    subtitle:
      "How Business Shield verifies payments without exposing banking secrecy, what the audit log stores, and how test invoice files are handled.",
    summaryStrip: [
      {
        label: "External calls per check",
        value: "0",
        hint: "Risk engine runs locally; optional invoice extraction and plain-language summary call an external API only when a key is set and never affect verdicts",
      },
      {
        label: "Banking secrecy",
        value: "Fact only",
        hint: "Never exposes third-party owner name, BIN, or opening date",
      },
      {
        label: "Audit log",
        value: "SHA-256",
        hint: "Request hash, ruleset version, and rule IDs without plaintext details",
      },
      {
        label: "Invoice uploads",
        value: "Test only",
        hint: "Upload synthetic or test invoices only in this prototype",
      },
    ],
    pillars: [
      {
        id: "data-usage",
        title: "How Data Is Used During Verification",
        summary:
          "The verification core checks payment orders exclusively against internal sources and local catalogs, with no outbound API calls.",
        points: [
          "12-month client payment history: usual IIKs, banks, amounts, and KNP codes per supplier.",
          "Internal bank account directory: verifies account ownership and age strictly inside the bank boundary.",
          "Anonymized bank-wide signals (synthetic bank_signals.json): aggregated client complaints on an IIK, multi-payer inflows to fresh accounts (exempting established bank-known BINs), and a mule watchlist — without disclosing payer names or BINs.",
          "NBK bank catalog: bank codes, BICs, and budget recipient markers (Treasury, Government for Citizens).",
          "Short-term check memory: detects repeated invoice numbers within 90 days, 72-hour structuring, and 7-day cumulative volume to new recipients.",
        ],
      },
      {
        id: "transparent-rules",
        title: "Explainable, Deterministic Rules",
        summary:
          "Verdicts come from auditable rules with explicit scores and thresholds rather than an opaque black box.",
        points: [
          "Every response carries a ruleset_version so any past decision can be reproduced against the exact rules in effect.",
          "Every signal includes a plain-language reason and field evidence (expected vs. actual).",
          "Local benchmarks run in roughly 3 ms per payment.",
        ],
      },
    ],
    secrecyComparisonTitle: "Banking Secrecy: Separation of Output",
    secrecyComparisonSubtitle:
      "Information about another customer's account is processed inside the bank and never disclosed in plaintext to the client.",
    clientSeesTitle: "What the Client Sees (Accountant & Director)",
    clientSeesItems: [
      "Neutral alert only: \"Account is registered to another company\".",
      "A \"Recently opened account\" indicator without revealing the exact opening date.",
      "Comparison against the client's own payment history and character-level name diffs.",
      "No third-party account holder name or BIN appears in check responses, queues, or audit logs.",
    ],
    analystSeesTitle: "What Is Isolated in Antifraud Analyst View",
    analystSeesItems: [
      "Internal account owner details (name and BIN) for fraud investigation.",
      "Account opening date and age in days.",
      "Exact character positions of suspicious mixed-script or hidden symbols.",
      "In the demo, this view is toggled on the Approvals screen; in production, access is restricted to authenticated bank analyst roles.",
    ],
    secrecyDisclaimer:
      "Prototype note: in demo mode, the analyst view is unauthenticated for easy demonstration. Production wording and access controls must be approved by bank compliance.",
    auditTitle: "Audit Log",
    auditSubtitle:
      "Every payment check and director decision is written to an append-only audit log tied to the active ruleset version.",
    auditStoredTitle: "Recorded in Each Audit Entry",
    auditStoredItems: [
      "Timestamp, check_id, and (for decisions) approval_id.",
      "SHA-256 hash of the canonical request payload (independent of UI language).",
      "ruleset_version, resulting verdict, triggered rule IDs, and recorded action.",
    ],
    auditNotStoredTitle: "Excluded From Demo Audit Plaintext",
    auditNotStoredItems: [
      "Counterparty names and payment purpose text.",
      "BIN/IIN numbers, IIK account numbers, and payment amounts.",
      "Third-party internal bank account owner metadata.",
    ],
    invoiceNoticeTitle: "Invoice Upload: Test Data Only",
    invoiceNoticeDescription:
      "The New Payment form supports uploading an invoice file (PDF, PNG, JPEG, or WebP up to 10 MB) to prefill payment fields and validate checksums.",
    invoiceNoticePoints: [
      "Uploaded files are sent to the invoice recognition service (with template-based fallback); therefore, use synthetic or test invoices only in this prototype.",
      "Do not upload real commercial invoices, contracts, customer requisites, or personal data.",
      "Whenever confidence is low or warnings are returned, submission is blocked until the user verifies fields against the original and checks the confirmation box.",
    ],
    limitationsTitle: "Honest Prototype Limitations",
    limitationsSubtitle:
      "Important boundaries to keep in mind while evaluating the hackathon build:",
    limitations: [
      "All datasets (150-payment history, 12 suppliers, account directory, bank-wide signals, and queue) are synthetic.",
      "No live digital signature (NCALayer) is connected in demo mode: clicking \"Sign\" simulates submission.",
      "Approvals, trusted accounts, and short-term memory live in process memory and reset on restart or \"Reset demo\".",
      "Interbank ownership verification for external banks is not connected; external accounts rely on client history, format validation, and anomaly checks.",
    ],
  },
  terms: {
    title: "Terms of Use",
    subtitle:
      "Short placeholder terms of use for the Business Shield hackathon prototype.",
    bannerTitle: "Hackathon Prototype Placeholder (ITU HACKATHON-2026)",
    bannerDescription:
      "This placeholder text is not a public offer, banking agreement, or official legal document of any financial institution. The application is provided strictly for demonstration purposes.",
    updatedLabel: "Document status: prototype placeholder · ITU HACKATHON-2026",
    sections: [
      {
        title: "1. Prototype Purpose",
        paragraphs: [
          "Business Shield was created for ITU HACKATHON-2026 to demonstrate pre-signing verification for B2B supplier payments. All screens, texts, and scenarios are intended solely for evaluation and testing.",
        ],
      },
      {
        title: "2. No Real Financial Transactions",
        paragraphs: [
          "This prototype is not connected to payment rails, live bank accounts, or digital signature software (NCALayer). Clicking Sign, Approve, Reject, or submitting the Support form does not move real funds or create legally binding obligations.",
        ],
      },
      {
        title: "3. Synthetic Data & Verification Limits",
        paragraphs: [
          "Payment history, supplier lists, queues, and account catalogs are synthetic. Verdicts displayed by the prototype (green, yellow, red, grey, invalid) are illustrative and carry no financial or legal guarantee.",
        ],
      },
      {
        title: "4. Test Data Only",
        paragraphs: [
          "When testing the New Payment form, Attack Console, invoice upload, or Support form, use fictional or test data only. Do not submit confidential documents, real bank requisites, or third-party personal data.",
        ],
      },
      {
        title: "5. Closing Note (Placeholder)",
        paragraphs: [
          "Any production deployment requires formal legal terms drafted and approved by the adopting bank's legal and compliance teams under the laws of the Republic of Kazakhstan.",
        ],
      },
    ],
  },
  privacy: {
    title: "Privacy Policy",
    subtitle:
      "Short placeholder privacy notice for the Business Shield hackathon prototype.",
    bannerTitle: "Hackathon Prototype Placeholder (ITU HACKATHON-2026)",
    bannerDescription:
      "This page is an informational placeholder for a hackathon prototype and is not an official personal-data processing policy of any bank.",
    updatedLabel: "Document status: prototype placeholder · ITU HACKATHON-2026",
    sections: [
      {
        title: "1. Overview",
        paragraphs: [
          "The Business Shield prototype is designed for evaluation with synthetic data and does not collect real personal or banking records.",
        ],
      },
      {
        title: "2. Browser Local Storage",
        paragraphs: [
          "For convenience, the app stores your chosen interface language (key: business-shield.lang) and temporary edits to the demo payment queue in your browser's localStorage. You can clear this state anytime via \"Reset demo\" or browser settings.",
        ],
      },
      {
        title: "3. Verification Audit Log",
        paragraphs: [
          "When a test check or director decision runs, the prototype server logs a timestamp, check ID, canonical request SHA-256 hash, ruleset version, verdict, and triggered rule IDs. Plaintext company names, BIN/IINs, IIKs, amounts, and payment purposes are not written to the demo audit log.",
        ],
      },
      {
        title: "4. Invoice File Uploads",
        paragraphs: [
          "If you use the optional invoice upload feature (PDF, PNG, JPEG, or WebP up to 10 MB), the file is sent to the invoice recognition service to prefill form fields. Upload only test files containing no commercial, banking, or personal secrets.",
        ],
      },
      {
        title: "5. Support Form",
        paragraphs: [
          "The Support page form runs purely in your browser, displays a local toast notification, and transmits nothing to any server or third party.",
        ],
      },
    ],
  },
  about: {
    title: "About Business Shield",
    subtitle:
      "Protecting SME companies from supplier invoice requisite spoofing before a payment order is signed.",
    problemTitle: "The Problem We Address",
    problemLead:
      "Fraudsters compromise business email threads or send forged invoices with \"updated bank details\" for a known supplier. The accountant signs the transfer voluntarily — and conventional bank antifraud allows it because the customer authorized the payment.",
    problemParagraphs: [
      "In Kazakhstan, there is no public service allowing a business to verify who owns a bank account (IIK) before paying: third-party account holder names are protected by banking secrecy. Once an authorized payment is signed, recovering funds is extremely difficult for small businesses.",
      "Business Shield sits directly before signature: it cross-checks the payment against what the client and bank already know, shows exact field-level differences, and requires conscious review or director approval before risky payments can proceed.",
    ],
    problemStats: [
      {
        value: "~2.18M",
        label: "active SME entities in Kazakhstan",
        source: "Bureau of National Statistics of RK, as of Oct 1, 2025",
      },
      {
        value: "≈ $3B",
        label: "reported U.S. losses to Business Email Compromise (BEC) in 2025",
        source: "FBI IC3 2025 Report — cited as international scale context",
      },
      {
        value: "74%",
        label: "of surveyed U.S. organizations targeted by BEC in 2025",
        source: "AFP 2026 Survey — U.S. benchmark, not Kazakhstan statistics",
      },
    ],
    statsDisclaimer:
      "No public Kazakhstan-specific statistics on B2B requisite spoofing are available; U.S. figures are cited solely to illustrate the global scale of BEC.",
    solutionTitle: "The Business Shield Approach",
    solutionSubtitle:
      "Why we built explainable history-and-bank verification instead of an opaque score.",
    solutionCards: [
      {
        title: "Client-Specific Context",
        description:
          "Checks not only BIN/IIK/BIC validity, but also consistency with the company's 12-month history with each supplier.",
      },
      {
        title: "Internal Checks Without Secrecy Leaks",
        description:
          "Internal account ownership is evaluated inside the bank: clients see only the mismatch fact, while detailed metadata stays with antifraud analysts.",
      },
      {
        title: "Explainability & Speed (≈ 3 ms)",
        description:
          "Auditable rule sets with versioning (ruleset_version), character-level diffs, and concrete next steps for accountants and directors.",
      },
      {
        title: "Trilingual & Pilot-Ready",
        description:
          "Russian, Kazakh, and English across UI and API, append-only audit logging, 480+ automated tests, and a shadow-mode pilot plan.",
      },
    ],
    teamTitle: "Project Team",
    teamSubtitle:
      "Built for ITU HACKATHON-2026 (functional placeholder roles shown below).",
    teamPlaceholderNotice:
      "Team roles are shown as hackathon prototype placeholders without real personal details or legal entity records.",
    teamMembers: [
      {
        role: "Product & Antifraud Analytics",
        focus:
          "B2B requisite-spoofing scenarios, risk rule design, unit economics, and shadow-mode pilot plan.",
        tag: "Role · placeholder",
      },
      {
        role: "Backend & Risk Engine",
        focus:
          "BIN/IIN/IIK/BIC validators, lookalike character analysis, audit log, and trilingual API.",
        tag: "Role · placeholder",
      },
      {
        role: "Frontend & User Experience",
        focus:
          "Signing queue, character-diff verification view, director desk, attack console, and product pages.",
        tag: "Role · placeholder",
      },
      {
        role: "Quality & Security",
        focus:
          "400-case synthetic evaluation set, automated test suite, blind-spot analysis, and banking secrecy controls.",
        tag: "Role · placeholder",
      },
    ],
    roadmapTitle: "Roadmap",
    roadmapSubtitle:
      "Phased transition from hackathon prototype to production B2B payment protection.",
    roadmap: [
      {
        phase: "Phase 1",
        statusLabel: "Next step",
        title: "Shadow-Mode Pilot on 10–20 SME Clients",
        description:
          "Run for 2–3 months without blocking signatures to measure real-world yellow/red rates, director overrides, review times, and prevented losses.",
      },
      {
        phase: "Phase 2",
        statusLabel: "Production hardening",
        title: "Database, Bank Roles & Pre-NCALayer Hook",
        description:
          "Move approvals, trusted accounts, short-term memory, and audit logs to PostgreSQL, enforce roles via bank session tokens, integrate ahead of NCALayer, and add monitored fail-open degradation.",
      },
      {
        phase: "Phase 3",
        statusLabel: "Scale",
        title: "Validation on Real 1C Exports",
        description:
          "1C/CSV batch import and batch green signing are already implemented in prod mode (tested only on synthetic data); the next step is validating against live \"1C: Accounting for Kazakhstan\" exports and tuning batch throughput.",
      },
      {
        phase: "Phase 4",
        statusLabel: "Industry integration",
        title: "Interbank \"BIN ↔ IIK: Yes/No\" Verification",
        description:
          "Extend ownership matching to external banks following the Verification of Payee model via the NBK Antifraud Center without disclosing holder names (subject to regulatory approval).",
      },
      {
        phase: "Phase 5",
        statusLabel: "Expanded protection",
        title: "Live Bank Feeds, Decision Tables & In-Bank Parsing",
        description:
          "Bank-wide signals are already implemented on synthetic data (bank_signals.json); next steps are connecting live anonymized bank-wide feeds, managing rule weights via decision tables without code changes, and running invoice parsing inside bank infrastructure.",
      },
    ],
  },
};
