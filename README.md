# Zamp Invoice Agent

An AI agent that does the work of an accounts-payable clerk for an Indian company. It reads a vendor invoice PDF, works out what kind of transaction it is, checks it against the company's purchase orders, goods receipts, contracts and vendor master, and applies an editable rulebook. Then it either **approves the invoice on its own** or **hands it to the right person with the exact reason and the evidence**.

> **Status:** the full pipeline, API and web UI are built and tested (271 backend tests, 14 frontend tests; all 16 demo samples reach their expected outcome end to end). A visual redesign of the UI is planned.

---

## Contents

1. [What it does](#what-it-does)
2. [Architecture](#architecture)
3. [Transaction types](#transaction-types)
4. [How decisions are made](#how-decisions-are-made)
5. [Every rule, stage by stage](#every-rule-stage-by-stage)
6. [Outcomes and reason codes](#outcomes-and-reason-codes)
7. [The rulebook](#the-rulebook)
8. [Data sources](#data-sources)
9. [Audit trail](#audit-trail)
10. [Models](#models)
11. [Demo samples](#demo-samples)
12. [Known limitations and production work](#known-limitations-and-production-work)
13. [Repository layout](#repository-layout)
14. [Setup](#setup)

---

## What it does

- **Input:** a vendor invoice PDF, digital or scanned, uploaded in the web UI or picked from a set of demo samples.
- **Output:** one of four outcomes, with every check that ran, the evidence on the page, the rule applied, who owns the next step, and what that step is.

| Outcome | Meaning | Goes to |
|---|---|---|
| **Approved** | Every required check passed, within the agent's authority | Ready for payment; the PO ledger is updated |
| **Needs sign-off** | Clean, but above the agent's approval limit | Finance controller or budget owner |
| **On hold** | Might be fine, but a person must check something | The owner named in the rulebook (Procurement, AP team, Warehouse, Vendor master team…) |
| **Rejected** | Can never be paid as it stands | Back to the vendor, with the reason |

It is built for **India first**: ₹, GST (CGST/SGST/IGST), GSTIN validation, HSN/SAC codes, GST invoice rules (Rule 46) and e-invoice IRNs. Region-specific rules live in a separate rule pack, so a US pack can be added later without changing the pipeline.

**The core principle: the AI reads, the code decides.** AI is used where perception or judgment is needed: reading messy and scanned pages, classifying, matching vaguely worded lines, and a final review. Every rupee comparison and every rule is deterministic code, so the same invoice always gets the same decision, and every decision can be traced to a named rule.

---

## Architecture

![Agent graph](docs/architecture.svg)

Each invoice runs through one **LangGraph** state graph:

- **Blue nodes** make a single model call.
- **Purple nodes** are agents that call tools.
- **White nodes** are deterministic code.
- **The dashed node** is the human gate.

All model calls go through one **LLM gateway**, which handles the rate limit, retries, caching and logging. Every node writes its findings, tool calls and events to the **case record**, which streams live to the UI over server-sent events. A case on hold pauses at the human gate (LangGraph `interrupt()`) and resumes when a person acts.

**Node sequence**

| # | Node | Runs on | What it does |
|---|---|---|---|
| 1 | `ingest` | code | file fingerprint, file-type check, page count, encryption, metadata |
| 2 | `render_pages` / `text_layer` | code | page images (pypdfium2); embedded text with positions (pdfplumber, digital PDFs only) |
| 3 | `parse_pages` | AI | nemotron-3.5-parse reads each page image into text blocks with bounding boxes |
| 4 | `reconcile` | code | embedded text vs what the page shows; tamper signals; prompt-injection scan |
| 5 | `extract` | AI | Mistral Large 4 turns the parsed page into a strict JSON schema: value, confidence and source block per field |
| 6 | `ground_normalise` | code | every value must be found on the page; normalise dates, ₹, GSTIN, invoice numbers, units |
| 7 | `classify_document` | code + AI | tax invoice, credit note, proforma, or something else |
| 8 | `classify_transaction` | agent | Standard PO, Recurring or PO-less, with confidence and reason |
| 9 | `validate` | code | India rule pack: GST compliance and arithmetic |
| 10 | path subgraph | code + agent tools | Standard PO matching, Recurring contract checks, or PO-less policy and GL coding |
| 11 | `controls` | code | vendor, bank details, duplicates, split-to-avoid-limit, authority |
| 12 | `completeness_guard` | code | every required check for this path actually ran |
| 13 | `decide` | code + agent | rules engine sets the floor → agent review (can only escalate) → verdict text from the rulebook |
| 14 | `human_gate` | interrupt | a person approves, rejects, asks the vendor, confirms a field or re-checks |
| 15 | `finalise` | code | ledger update, payment date, sealed audit bundle |

---

## Transaction types

| Type | Example | How it's checked |
|---|---|---|
| **Standard PO** | 20 chairs against PO-4501 | Invoice vs PO, line by line. Goods POs are also checked against the goods receipt (**3-way match**); service POs need no receipt (**2-way**) |
| **Recurring** | Monthly IT support retainer against a blanket PO or contract | The billing period hasn't already been billed, the amount matches the contract schedule, the contract is active, and the balance remains |
| **PO-less** | Electricity bill, telecom, rent | No PO to match, so: is a PO-less purchase allowed for this category; GL account and cost centre suggested by the agent; routed to the budget owner; low auto-approve limit |

---

## How decisions are made

Two guardrails make the agent safe to let it act on money:

1. **Mandatory checks are graph nodes, not agent choices.** Each path has a fixed list of required checks that always run. The agent's tools are for *investigation*: finding a PO when none is printed, pairing vaguely described lines, suggesting a GL code. `completeness_guard` refuses to decide if any required check is missing.
2. **Rules set the floor; the AI can only escalate.**
   - The rules engine takes the most severe finding as the minimum outcome.
   - The agent then reviews the whole case and may make the outcome *stricter*, for example holding a case that passed every rule because a new vendor billed a round ₹4,99,000. It must give a reason and cite real findings.
   - Code rejects any agent output that is less strict than the rules or cites findings that don't exist.
   - The agent has no "approve" tool.

**Fail closed:** any model or tool error becomes a finding and puts the case on hold. Nothing is ever approved because something broke.

**Every problem at once:** a failed check records its finding and the run continues, so the case shows every issue, not only the first. A few checks stop the run because nothing after them would be meaningful; these are marked ⛔ in the diagrams below.

---

## Every rule, stage by stage

How to read these diagrams:
- The solid spine is the order the checks run in.
- A dashed arrow is what happens when a check fails: the reason code, the outcome, and the risk ID from the risk catalogue (e.g. `L5`).

Colours:
- 🟥 Reject
- 🟧 Hold
- 🟪 Needs sign-off
- 🟨 Warning (recorded, doesn't change the outcome alone)
- 🟦 an AI step

### Stage 1: Intake and reading

```mermaid
flowchart TD
  S(["PDF arrives"]) --> A1["File fingerprint: seen this exact file before?"]
  A1 -.->|yes| A1x["⛔ DUPLICATE_EXACT → Reject · A1 K1"]:::rej
  A1 --> A2["Real, readable PDF?"]
  A2 -.->|no| A2x["⛔ UNREADABLE_DOCUMENT → Hold · A2"]:::hold
  A2 --> A3["Password protected?"]
  A3 -.->|yes| A3x["⛔ ENCRYPTED_DOCUMENT → Hold · A3"]:::hold
  A3 --> RP["Render each page to an image"]
  A3 --> TL["Read embedded text layer<br/>digital PDFs only"]
  RP --> P["Parse each page<br/>nemotron-3.5-parse → text blocks + boxes"]:::ai
  P --> P2["More than one invoice, or pages missing?"]
  P2 -.->|yes| P2x["MULTIPLE_INVOICES_IN_FILE / INCOMPLETE_DOCUMENT → Hold · A5 A6"]:::hold
  P2 --> RC["Embedded text agrees with what the page shows?<br/>amounts · account number · GSTIN"]
  TL --> RC
  RC -.->|no| RCx["TEXT_LAYER_MISMATCH → Hold · L5"]:::hold
  RC --> TM["PDF edited after issue?<br/>metadata dates · editing software"]
  TM -.->|signals| TMx["DOCUMENT_TAMPER_SIGNALS → Warning · L4"]:::warn
  TM --> PI["Text addressed to the AI?<br/>'approve this', 'ignore previous'"]
  PI -.->|yes| PIx["SUSPICIOUS_INSTRUCTIONS_IN_DOCUMENT → Hold, locked · L6"]:::hold
  PI --> X["Extract fields to JSON<br/>Mistral Large 4 · value + confidence + source block"]:::ai
  X --> XJ["Valid JSON after one retry?"]
  XJ -.->|no| XJx["⛔ EXTRACTION_FAILED → Hold · B6"]:::hold
  XJ --> GR["Grounding: every value found on the page?"]
  GR -.->|no| GRx["Value dropped or confidence lowered · B1"]:::warn
  GR --> CF["Every key field read with ≥ 85% confidence?"]
  CF -.->|no| CFx["LOW_CONFIDENCE_FIELD → Hold, confirm in place · A4"]:::hold
  CF --> N["Normalise: DD/MM dates · ₹ amounts · GSTIN · invoice-number form · units · tax-inclusive to exclusive"]
  N --> Z(["to classification"])
  classDef rej fill:#F9E3E1,stroke:#B9342A,color:#5A1712
  classDef hold fill:#FBEEDB,stroke:#B26A0E,color:#5A3606
  classDef warn fill:#FFF7D6,stroke:#B89A00,color:#4D4000
  classDef ai fill:#E6EDFC,stroke:#2B5FD9,color:#14306E
```

Model calls in this stage go through the gateway: rate limit, backoff, temperature 0, cache by file hash. If a model is unavailable the case goes on hold with `AI_UNAVAILABLE` (B8), never to approve.

### Stage 2: Classification

```mermaid
flowchart TD
  S(["from reading"]) --> D["Classify document<br/>title and keywords · sign of totals · fast model if unclear"]:::ai
  D -.->|proforma · quotation · statement| Dx1["⛔ NOT_A_TAX_INVOICE → Reject · C1"]:::rej
  D -.->|credit or debit note| Dx2["⛔ CREDIT_NOTE_RECEIVED → Hold, AP team · C2 E4"]:::hold
  D -->|tax invoice| SG["Deterministic signals<br/>PO printed? PO exists? PO type? service period printed? vendor category?"]
  SG --> AG["Agent: classify_transaction · Nemotron 3 Ultra<br/>tools: vendor_lookup · po_search · contract_lookup"]:::agent
  AG -.->|confidence below 80%| AGx["⛔ CLASSIFICATION_UNCERTAIN → Hold · E1"]:::hold
  AG -->|Standard PO| SP(["Standard PO path"])
  AG -->|Recurring| RE(["Recurring path"])
  AG -->|PO-less| PL(["PO-less path"])
  classDef rej fill:#F9E3E1,stroke:#B9342A,color:#5A1712
  classDef hold fill:#FBEEDB,stroke:#B26A0E,color:#5A3606
  classDef ai fill:#E6EDFC,stroke:#2B5FD9,color:#14306E
  classDef agent fill:#F0E8FB,stroke:#7A3FC8,color:#3B1A66
```

The signals decide clear cases on their own. For example, a printed PO that exists and is a blanket or contract PO means Recurring. The agent is asked only when the signals conflict, and its answer, confidence and reasoning are stored. Recurring invoices wrongly looking like one-offs are caught by the PO-type signal (E3). PO-less misclassification is caught later, in the PO-less path (E2).

### Stage 3: Validation (India rule pack)

```mermaid
flowchart TD
  S(["classified invoice"]) --> V1["GST Rule 46 fields present?<br/>invoice no · date · supplier and buyer GSTIN · line items · taxable value · tax · total"]
  V1 -.->|missing| V1x["MISSING_MANDATORY_FIELD → Reject · C3"]:::rej
  V1 --> V2["Supplier GSTIN: format and check digit valid?"]
  V2 -.->|no| V2x["INVALID_GSTIN → Reject · C4"]:::rej
  V2 --> V3["GSTIN state code = vendor's state on file?"]
  V3 -.->|no| V3x["GSTIN_STATE_MISMATCH → Hold · C5"]:::hold
  V3 --> V4["Buyer GSTIN = our GSTIN?<br/>if supplier and buyer were swapped, fix and warn · B3"]
  V4 -.->|no| V4x["WRONG_BUYER_GSTIN → Reject · C6"]:::rej
  V4 --> V5["Vendor registration active?<br/>vendor master gst_status"]
  V5 -.->|cancelled| V5x["GSTIN_INACTIVE → Reject · C9"]:::rej
  V5 --> V6["Vendor must e-invoice? then IRN present and 64 hex characters?"]
  V6 -.->|missing| V6x["EINVOICE_IRN_MISSING → Reject · C7"]:::rej
  V6 -.->|malformed| V6y["INVALID_IRN → Hold · C8"]:::hold
  V6 --> V7["Tax type: supplier state = place of supply → CGST + SGST, else IGST"]
  V7 -.->|wrong type| V7x["WRONG_TAX_TYPE → Hold · D3"]:::hold
  V7 --> V8["Arithmetic: qty × rate = line · lines add to taxable · tax = rate × taxable · total within ₹1"]
  V8 -.->|off| V8x["ARITHMETIC_MISMATCH → Hold · D1 D2 B5"]:::hold
  V8 --> V9["Amount in words = amount in figures?"]
  V9 -.->|no| V9x["AMOUNT_WORDS_MISMATCH → Hold · D6 B2"]:::hold
  V9 --> V10["Dates: not in the future, not older than the tax-credit window"]
  V10 -.->|future| V10x["FUTURE_DATED_INVOICE → Hold · B4"]:::hold
  V10 -.->|old| V10y["STALE_INVOICE_DATE → Warning · C10"]:::warn
  V10 --> Z(["to the path for this transaction type"])
  classDef rej fill:#F9E3E1,stroke:#B9342A,color:#5A1712
  classDef hold fill:#FBEEDB,stroke:#B26A0E,color:#5A3606
  classDef warn fill:#FFF7D6,stroke:#B89A00,color:#4D4000
```

### Stage 4a: Standard PO path

```mermaid
flowchart TD
  S(["Standard PO"]) --> M1["PO number printed and found?"]
  M1 -.->|no| M1a["Agent ranks the vendor's open POs<br/>item and HSN overlap · same rate · amount within balance"]:::agent
  M1a -.->|score ≥ 90% and a clear lead| M1b["PO_INFERRED → Warning · G1"]:::warn
  M1a -.->|otherwise| M1c["⛔ PO_NOT_FOUND → Hold, candidates listed · G2"]:::hold
  M1 --> M2["PO issued to this vendor?"]
  M1b --> M2
  M2 -.->|no| M2x["PO_VENDOR_MISMATCH → Reject · G3"]:::rej
  M2 --> M3["PO open, not closed or cancelled?"]
  M3 -.->|no| M3x["PO_CLOSED → Hold · G4"]:::hold
  M3 --> M4["Pair each invoice line with a PO line<br/>HSN + description similarity · agent breaks ties"]
  M4 -.->|agent paired| M4a["LLM_LINE_PAIRING → Warning · G10"]:::warn
  M4 -.->|invoice line with no PO line| M4b["UNEXPECTED_CHARGES → Hold · G9"]:::hold
  M4 -.->|one lump line| M4c["HEADER_LEVEL_MATCH_ONLY → Warning · G11"]:::warn
  M4 --> L1["Per line: GST rate = PO rate?"]
  L1 -.->|no| L1x["GST_RATE_MISMATCH → Hold · D4"]:::hold
  L1 --> L2["Per line: units match or convert? kg vs tonnes"]
  L2 -.->|no| L2x["UNIT_MISMATCH → Hold · G8"]:::hold
  L2 --> L3["Per line: rate ≤ PO rate + 2% AND extra ≤ ₹5,000"]
  L3 -.->|above| L3x["PRICE_VARIANCE → Hold · G5"]:::hold
  L3 -.->|below PO| L3y["UNDER_BILLED → Warning · G15"]:::warn
  L3 --> L4["Per line: billed before + this qty ≤ ordered"]
  L4 -.->|over| L4x["QTY_EXCEEDS_ORDERED → Hold · G7"]:::hold
  L4 --> G0{"Goods PO?"}
  G0 -->|services: 2-way| H0
  G0 -->|goods: 3-way| L5["Goods receipt exists for the line?"]
  L5 -.->|no| L5x["RECEIPT_MISSING → Hold, Warehouse · H1 L9"]:::hold
  L5 --> L6["Billed before + this qty ≤ accepted qty<br/>QC-rejected goods don't count"]
  L6 -.->|over| L6x["QTY_EXCEEDS_RECEIVED → Hold · H2 H3"]:::hold
  L6 --> H0["PO total: invoiced to date + this ≤ PO value?"]
  H0 -.->|over| H0x["AMOUNT_EXCEEDS_PO_BALANCE → Hold, ledger shown · G12"]:::hold
  H0 -.->|already 100% billed| H0y["PO_FULLY_INVOICED → Hold · G13"]:::hold
  H0 --> H1["Invoice dated on or after the PO date?"]
  H1 -.->|before| H1x["INVOICE_BEFORE_PO → Hold · G14"]:::hold
  H1 --> Z(["to controls"])
  classDef rej fill:#F9E3E1,stroke:#B9342A,color:#5A1712
  classDef hold fill:#FBEEDB,stroke:#B26A0E,color:#5A3606
  classDef warn fill:#FFF7D6,stroke:#B89A00,color:#4D4000
  classDef agent fill:#F0E8FB,stroke:#7A3FC8,color:#3B1A66
```

A rate above the PO but within tolerance passes, and the exact variance is recorded in the audit trail (G6).

### Stage 4b: Recurring path

```mermaid
flowchart TD
  S(["Recurring"]) --> R1["Contract or blanket PO found for this vendor?"]
  R1 -.->|no| R1x["⛔ CONTRACT_NOT_FOUND → Hold"]:::hold
  R1 --> R2["Billing period read from the invoice?"]
  R2 -.->|unclear| R2x["LOW_CONFIDENCE_FIELD → Hold, confirm period · I5"]:::hold
  R2 --> R3["Period inside the contract's start and end dates?"]
  R3 -.->|no| R3x["CONTRACT_NOT_ACTIVE → Hold · I3"]:::hold
  R3 --> R4["Period not already billed?<br/>period ledger, regardless of invoice number"]
  R4 -.->|already billed| R4x["PERIOD_ALREADY_BILLED → Hold · I1"]:::hold
  R4 --> R5["Period not in the future?"]
  R5 -.->|future| R5x["ADVANCE_BILLING → Warning · I7"]:::warn
  R5 --> R6["Amount = contract amount for the period?"]
  R6 -.->|different| R6x["CONTRACT_AMOUNT_MISMATCH → Hold · I2 I6"]:::hold
  R6 --> R7["Billed to date + this ≤ blanket or contract total?"]
  R7 -.->|over| R7x["AMOUNT_EXCEEDS_PO_BALANCE → Hold, ledger shown · I4"]:::hold
  R7 --> Z(["to controls"])
  classDef hold fill:#FBEEDB,stroke:#B26A0E,color:#5A3606
  classDef warn fill:#FFF7D6,stroke:#B89A00,color:#4D4000
```

The duplicate check in controls is period-aware for recurring invoices, so next month's retainer is not mistaken for a duplicate (K8).

### Stage 4c: PO-less path

```mermaid
flowchart TD
  S(["PO-less"]) --> P1["Does an open PO exist for this vendor and these items?"]
  P1 -.->|yes| P1x["PO_EXISTS_FOR_PO_LESS → Warning, rerouted to Standard PO · E2"]:::warn
  P1 --> P2["Is this category allowed without a PO?<br/>utilities · telecom · rent · statutory · travel · subscriptions"]
  P2 -.->|no, e.g. furniture| P2x["PO_REQUIRED_FOR_CATEGORY → Hold, Procurement · J1"]:::hold
  P2 --> P3["Service account registered?<br/>e.g. electricity consumer number"]
  P3 -.->|unknown| P3x["UNKNOWN_SERVICE_ACCOUNT → Hold · J4"]:::hold
  P3 --> P4["Agent: GL coder<br/>chart of accounts → top 3 GL codes + cost centre + confidence"]:::agent
  P4 -.->|confidence below 80%| P4x["GL_CODING_UNCERTAIN → Hold, owner picks from top 3 · J3"]:::hold
  P4 --> P5["Amount within 3× the 6-month average?"]
  P5 -.->|spike| P5x["AMOUNT_ANOMALY → Hold · J5"]:::hold
  P5 --> P6["Amount ≤ ₹25,000 PO-less auto limit?"]
  P6 -.->|above| P6x["NEEDS_SIGNOFF → Budget owner · J2"]:::sign
  P6 --> Z(["to controls"])
  classDef hold fill:#FBEEDB,stroke:#B26A0E,color:#5A3606
  classDef warn fill:#FFF7D6,stroke:#B89A00,color:#4D4000
  classDef sign fill:#ECE6FA,stroke:#5B3CC4,color:#2E1A6B
  classDef agent fill:#F0E8FB,stroke:#7A3FC8,color:#3B1A66
```

### Stage 5: Controls (all paths)

```mermaid
flowchart TD
  S(["from any path"]) --> K1["Vendor in the master and active?"]
  K1 -.->|no| K1x["VENDOR_NOT_APPROVED → Reject, locked · F1 L2"]:::rej
  K1 --> K2["Name close to another vendor but a different GSTIN?<br/>e.g. 'Kaveri Packaging Industry' vs 'Industries'"]
  K2 -.->|yes| K2x["LOOKALIKE_VENDOR → Hold · F2 L3"]:::hold
  K2 --> K3["Name and contact details match the master?"]
  K3 -.->|name differs| K3x["VENDOR_IDENTITY_MISMATCH → Warning · F3"]:::warn
  K3 -.->|phone or email differs| K3y["CONTACT_DETAILS_CHANGED → Warning · F4"]:::warn
  K3 --> K4["Bank account and IFSC = vendor master?"]
  K4 -.->|different| K4x["BANK_DETAILS_MISMATCH → Hold, locked · L1"]:::hold
  K4 --> K5["Exact duplicate: same vendor + same normalised invoice number?"]
  K5 -.->|earlier one approved| K5x["DUPLICATE_EXACT → Reject · K2"]:::rej
  K5 -.->|earlier one still open| K5y["DUPLICATE_EXACT → Hold · K2"]:::hold
  K5 -.->|same number, different amount| K5z["DUPLICATE_NUMBER_DIFFERENT_AMOUNT → Hold · K4"]:::hold
  K5 --> K6["Fuzzy duplicate: same vendor and 2+ of<br/>number edit distance ≤ 2 · amount ±0.5% · dates ≤ 30 days · lines ≥ 90% similar"]
  K6 -.->|vs approved or open| K6x["DUPLICATE_PROBABLE → Hold, original linked · K3 K5"]:::hold
  K6 -.->|vs rejected| K6y["RESUBMISSION_OF_REJECTED → Warning · K6"]:::warn
  K6 --> K7["Same vendor, 7 days: each under ₹5 L but together over?"]
  K7 -.->|yes| K7x["SPLIT_BELOW_LIMIT → Sign-off on the total · L7"]:::sign
  K7 --> K8["Total ≤ ₹5 L auto-approve limit?"]
  K8 -.->|above| K8x["NEEDS_SIGNOFF → Finance controller · M1"]:::sign
  K8 --> Z(["to decision"])
  classDef rej fill:#F9E3E1,stroke:#B9342A,color:#5A1712
  classDef hold fill:#FBEEDB,stroke:#B26A0E,color:#5A3606
  classDef warn fill:#FFF7D6,stroke:#B89A00,color:#4D4000
  classDef sign fill:#ECE6FA,stroke:#5B3CC4,color:#2E1A6B
```

The duplicate key always includes the vendor, so the same invoice number from two different vendors is legitimate (K7).

### Stage 6: Decision

```mermaid
flowchart TD
  S(["all findings"]) --> G["Completeness guard<br/>did every required check for this path run?"]
  G -.->|no| Gx["CHECKS_INCOMPLETE → Hold · N2"]:::hold
  G --> RE["Rules engine<br/>most severe finding sets the floor<br/>Reject > Hold > Sign-off > Approve"]
  RE --> AR["Agent review · Nemotron 3 Ultra<br/>reads the findings and invoice · may propose a stricter outcome<br/>must give a reason and cite finding IDs"]:::agent
  AR --> CK{"Proposal same or stricter<br/>AND cites findings that exist?"}
  CK -->|no| CKx["Proposal discarded · AGENT_RATIONALE_INVALID → Warning · N1 N3"]:::warn
  CK -->|yes| AP["Escalation applied<br/>e.g. round amount just under the limit · L8 L11"]
  CKx --> VC
  AP --> VC["Verdict composer<br/>primary reason by rulebook order · why sentence from the rulebook template · owner · next step"]
  VC --> O1["Approved"]:::ok
  VC --> O2["Needs sign-off"]:::sign
  VC --> O3["On hold"]:::hold
  VC --> O4["Rejected"]:::rej
  classDef rej fill:#F9E3E1,stroke:#B9342A,color:#5A1712
  classDef hold fill:#FBEEDB,stroke:#B26A0E,color:#5A3606
  classDef warn fill:#FFF7D6,stroke:#B89A00,color:#4D4000
  classDef sign fill:#ECE6FA,stroke:#5B3CC4,color:#2E1A6B
  classDef ok fill:#E1F2EA,stroke:#1F7F55,color:#0D3D27
  classDef agent fill:#F0E8FB,stroke:#7A3FC8,color:#3B1A66
```

The "why" sentence comes from the rulebook template filled with the finding's numbers. It is never written by the model. The agent's own note is shown separately, labelled as the agent's, with its full reasoning trace one click away (N5).

### Stage 7: Human gate and finalise

```mermaid
flowchart TD
  O3(["On hold"]) --> HG["Human gate · LangGraph interrupt"]
  O2(["Needs sign-off"]) --> HG
  HG --> A1["Approve anyway"]
  A1 --> A1c{"Locked reason code?<br/>bank change · injection · …"}
  A1c -->|yes| A1n["Verification note required<br/>logged as a high-risk override · M2"]:::hold
  A1c -->|no| F
  A1n --> F
  HG --> A2["Reject"] --> RJ(["Back to vendor with reason"])
  HG --> A3["Ask vendor"] --> WV(["Waiting for vendor"])
  HG --> A4["Sign off"] --> F
  HG --> A5["Confirm a field"] --> RV(["Re-run from validation"])
  HG --> A6["Re-check with current data and rulebook"] --> RR(["Re-run · AOP_VERSION_CHANGED → Warning if rules changed · O3 O4"])
  O1(["Approved"]) --> F["Finalise<br/>ledger write, idempotent per case · O2<br/>payment date = invoice date + vendor terms<br/>seal audit bundle"]:::ok
  ED["A rule edited, then the affected case approved, by the same person"] -.-> EDx["SOD_RULE_EDIT_AND_APPROVE → Warning · M3"]:::warn
  classDef hold fill:#FBEEDB,stroke:#B26A0E,color:#5A3606
  classDef warn fill:#FFF7D6,stroke:#B89A00,color:#4D4000
  classDef ok fill:#E1F2EA,stroke:#1F7F55,color:#0D3D27
```

Every rule edit is versioned with who and why, and locked rules can't be edited at all, so a rule can't be quietly loosened to push one invoice through (M4).

---

## Outcomes and reason codes

**Reject:** `NOT_A_TAX_INVOICE` · `MISSING_MANDATORY_FIELD` · `INVALID_GSTIN` · `WRONG_BUYER_GSTIN` · `GSTIN_INACTIVE` · `EINVOICE_IRN_MISSING` · `VENDOR_NOT_APPROVED` · `PO_VENDOR_MISMATCH` · `DUPLICATE_EXACT`

**Hold:** `UNREADABLE_DOCUMENT` · `ENCRYPTED_DOCUMENT` · `MULTIPLE_INVOICES_IN_FILE` · `INCOMPLETE_DOCUMENT` · `TEXT_LAYER_MISMATCH` · `SUSPICIOUS_INSTRUCTIONS_IN_DOCUMENT` · `EXTRACTION_FAILED` · `LOW_CONFIDENCE_FIELD` · `AI_UNAVAILABLE` · `CREDIT_NOTE_RECEIVED` · `CLASSIFICATION_UNCERTAIN` · `GSTIN_STATE_MISMATCH` · `INVALID_IRN` · `WRONG_TAX_TYPE` · `ARITHMETIC_MISMATCH` · `AMOUNT_WORDS_MISMATCH` · `FUTURE_DATED_INVOICE` · `PO_NOT_FOUND` · `PO_CLOSED` · `UNEXPECTED_CHARGES` · `GST_RATE_MISMATCH` · `UNIT_MISMATCH` · `PRICE_VARIANCE` · `QTY_EXCEEDS_ORDERED` · `RECEIPT_MISSING` · `QTY_EXCEEDS_RECEIVED` · `AMOUNT_EXCEEDS_PO_BALANCE` · `PO_FULLY_INVOICED` · `INVOICE_BEFORE_PO` · `CONTRACT_NOT_FOUND` · `CONTRACT_NOT_ACTIVE` · `PERIOD_ALREADY_BILLED` · `CONTRACT_AMOUNT_MISMATCH` · `PO_REQUIRED_FOR_CATEGORY` · `UNKNOWN_SERVICE_ACCOUNT` · `GL_CODING_UNCERTAIN` · `AMOUNT_ANOMALY` · `LOOKALIKE_VENDOR` · `BANK_DETAILS_MISMATCH` · `DUPLICATE_PROBABLE` · `DUPLICATE_NUMBER_DIFFERENT_AMOUNT` · `CHECKS_INCOMPLETE` · `TOOL_ERROR`

**Needs sign-off:** `NEEDS_SIGNOFF` · `SPLIT_BELOW_LIMIT`

**Warning:** `DOCUMENT_TAMPER_SIGNALS` · `STALE_INVOICE_DATE` · `PO_INFERRED` · `LLM_LINE_PAIRING` · `HEADER_LEVEL_MATCH_ONLY` · `UNDER_BILLED` · `ADVANCE_BILLING` · `PO_EXISTS_FOR_PO_LESS` · `VENDOR_IDENTITY_MISMATCH` · `CONTACT_DETAILS_CHANGED` · `RESUBMISSION_OF_REJECTED` · `AGENT_RATIONALE_INVALID` · `AOP_VERSION_CHANGED` · `SOD_RULE_EDIT_AND_APPROVE`

Each code has an owner, a next step and an explanation template in the rulebook.

---

## The rulebook

`rulebook/aop.yaml` is the agent's operating procedure, in plain English next to every value. A non-engineer can change a tolerance and the next run follows it. Each case records the rulebook version it ran under.

```yaml
version: 3
region: IN
owns: "Receiving a vendor invoice through to an approve / sign-off / hold / reject decision. Never pays."
authority: {auto_approve_limit_inr: 500000, po_less_auto_limit_inr: 25000, split_window_days: 7}
tolerance:
  price: {over_pct: 2.0, over_abs_inr: 5000}   # within only if BOTH hold; under-billing passes
  qty_over_ordered_pct: 0
  qty_over_received_pct: 0
  po_balance_over_pct: 0
  contract_amount_pct: 0
duplicates: {window_days: 30, min_similarity_pct: 90}
confidence: {min_field: 0.85, po_inference_min: 0.90, classification_min: 0.80, gl_coding_min: 0.80}
po_less_allowed_categories: [utilities, telecom, rent, statutory, travel, subscriptions]
locked: [BANK_DETAILS_MISMATCH, VENDOR_NOT_APPROVED, PO_VENDOR_MISMATCH, EINVOICE_IRN_MISSING, SUSPICIOUS_INSTRUCTIONS_IN_DOCUMENT]
reasons:
  PRICE_VARIANCE:
    outcome: hold
    owner: Procurement
    explain: "{vendor} billed {billed_rate} against an agreed PO rate of {po_rate}. That is {pct}% ({abs}) more, above the {tol}% price tolerance."
    next: "Confirm the new rate with the vendor, or approve the variance once."
```

---

## Data sources

The agent reads the company's existing records. Here they are CSV files standing in for an ERP export.

| File | Contents |
|---|---|
| `data/erp/vendors.csv` | vendor master: GSTIN, state, bank account and IFSC, contact details, e-invoice flag, GST status, payment terms, category |
| `data/erp/purchase_orders.csv` | PO lines: type (goods / services / blanket), item, HSN/SAC, qty, unit, rate, GST rate |
| `data/erp/goods_receipts.csv` | received and accepted quantities per PO line |
| `data/erp/contracts.csv` | recurring contracts: period, billing cycle, amount per period |
| `data/erp/chart_of_accounts.csv` | GL codes, cost centres, budget owners |
| `data/erp/service_accounts.csv` | registered utility and telecom account numbers |

The agent's own store (SQLite) holds the case records, the PO and period ledgers (invoiced to date), rulebook versions, the model-call cache and the LangGraph checkpoints.

---

## Audit trail

Every case keeps a complete, replayable record:

- the original PDF, page images, parsed text with boxes, and the extracted JSON
- every check with its result and evidence (page and position)
- every tool call with its arguments and JSON result
- every model call: model, prompt, response, **reasoning trace**, latency
- the agent's structured rationale (the main record) and its raw reasoning (attached)
- every human action: who, when, which action, and the note
- the rulebook version and the file fingerprint

---

## Models

All served through NVIDIA's OpenAI-compatible API (build.nvidia.com). Every model is a setting in `.env` and can be swapped without code changes.

| Role | Model |
|---|---|
| Page parsing (text + boxes) | `nvidia/nemotron-3.5-parse` |
| Field extraction | `mistralai/mistral-large-4-1t-a52b` |
| Small, frequent helper calls | `mistralai/mistral-large-4-1t-a52b` |
| Agent: classification, tools, review | `nvidia/nemotron-3-ultra-550b-a55b` |
| Similarity: line pairing, duplicates, lookalike vendors | `nvidia/nemotron-3.5-embed-1b` |

---

## Demo samples

| Sample | Shows |
|---|---|
| Clean invoice, goods PO, 3-way match | auto-approve |
| Steel billed 3% above PO | price-tolerance hold; editing the rule changes the outcome |
| Vendor's bank account changed | locked fraud hold |
| Third retainer invoice over the blanket balance | ledger hold |
| Same retainer month billed twice | period already billed |
| Same invoice resent with a new number | probable duplicate |
| Vendor must e-invoice, no IRN | reject |
| Scanned invoice, no PO number | reading a skewed, noisy scan; working out the PO itself; auto-approved when every check passes |
| Electricity bill | PO-less GL coding and routing |
| Furniture bought without a PO | maverick-spend hold |
| Proforma invoice | reject |
| Invoice text telling the AI to approve | injection hold; the agent cannot approve |
| Hidden text layer with a different amount | reconcile catch |
| Three ₹4.9 L invoices in one week | split-to-avoid-limit sign-off |
| Lookalike vendor name | fraud hold |
| Amount in words differs from figures | hold |

---

## Known limitations and production work

Deliberately out of scope for this version:

- **Concurrency.** Two invoices against the same PO processed at the same moment could both read the same remaining balance. In production: a per-PO lock, and re-checking the balance inside the ledger transaction before writing. Not needed for single-user demo runs.
- **Live government checks.** GSTIN status, GSTR-2B filing and IRN verification against the government portals. Here the vendor master stands in for them.
- **Tax deductions and payment rules.** TDS, the MSME 45-day payment rule, payment-date holiday calendars.
- **Other transaction shapes.** Foreign-currency invoices, advances and retention, partial payments, multi-entity buyers.
- **Wider fraud data.** Employee-vendor collusion checks need an employee master. E-way bill validation needs the portal.
- **Platform concerns.** Real ERP, email and bank integrations; SSO; multi-tenancy.
- **Free model endpoints are slow under load.** On NVIDIA's free tier a digital invoice takes about 30–60 seconds end to end; reading a *scanned* invoice with the vision model has taken up to 10 minutes. Demo samples replay recorded replies; production would use paid, provisioned endpoints.

---

## Repository layout

Organised by responsibility. Business configuration, company data and code live apart, and the backend folders follow the order an invoice moves through the pipeline.

```
rulebook/                 the agent's operating procedure (editable, versioned)
  aop.yaml
  versions/
data/
  erp/                    read-only stand-in for the company's ERP (vendors, POs, receipts, contracts, GL, service accounts)
  seed/                   past cases and ledger history loaded on demo reset
samples/                  demo invoice specs, PDF generator, generated PDFs, recorded model outputs
backend/
  src/ap_agent/
    core/                 settings, money, domain models
    rulebook/             load / save / version the rulebook
    erp/                  read the ERP files
    storage/              case records, ledgers, seeding
    ai/                   model gateway, agent tool loop, agent tools
    reading/              1 · PDF → page images → parsed blocks → extracted, grounded invoice
    classify/             2 · document type and transaction type
    rules/                pure rule functions (normalisation; india/ rule pack)
    checks/               3–5 · one file per stage: intake, validation, standard_po, recurring, po_less, controls
    decision/             6 · rules floor, agent review guard, verdict
    pipeline/             LangGraph state, nodes, graph, event bus
    api/                  FastAPI app and routes
  tests/                  unit/ (mirrors src) · integration/ · live/ (real model calls, off by default)
frontend/src/
  api/                    API client and types
  views/                  WorkQueue · LiveCase · Rulebook · ConnectedData
  components/             shared UI pieces
  styles/                 theme tokens
scripts/                  helper scripts (GSTIN generator, smoke test)
docs/                     architecture diagram
storage/                  runtime data, not committed
```

---

## Setup

Requirements: Python 3.11+, Node 20+, an NVIDIA API key from [build.nvidia.com](https://build.nvidia.com) (free endpoints).

```bash
cp .env.example .env                      # add NVIDIA_API_KEY

# backend
cd backend
python -m pip install -e ".[dev]"
python -m pytest                          # unit + end-to-end tests (no network: model replies are replayed)

# frontend
cd ../frontend
npm ci
npm test
npm run build                             # the backend serves frontend/dist

# run it
cd ../backend
python -m uvicorn ap_agent.api.app:app --app-dir src --port 8000
# open http://localhost:8000
```

For frontend development with hot reload, run `npm run dev` in `frontend/` (it proxies `/api` to port 8000).

**Demo samples and recorded replies.** The 16 demo invoices in `samples/pdf/` replay recorded model replies from `samples/cache/`, so the demo does not depend on a live model call. Uploaded PDFs always call the models live. To re-record: `python samples/seed_cache.py` (or `--fresh S08` for one sample). To regenerate the PDFs: `python samples/generate.py`.

**Live model tests** (off by default): `python -m pytest -m live tests/live`.

**Docker**

```bash
docker build -t ap-agent .
docker run -p 8000:8000 --env-file .env -v ap-agent-storage:/app/storage ap-agent
scripts/smoke.sh http://localhost:8000    # resets the demo data, runs sample S01, expects APPROVED
```

The image holds no secrets: `NVIDIA_API_KEY` and the `MODEL_*` settings come from the environment. Mount a persistent volume at `/app/storage` (case records, uploads, page images).
