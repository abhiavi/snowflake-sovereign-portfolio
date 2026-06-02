---
marp: true
theme: default
paginate: true
_paginate: false
header: 'Snowflake Sovereign MCP Interceptor'
footer: 'Track 1 Architecture | Snowflake Sovereign AI Portfolio'
style: |
  section {
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
    background: radial-gradient(circle at 0% 0%, #ffffff 0%, #f0f7fc 100%);
    color: #1d1d1f;
    padding: 60px;
    display: flex;
    flex-direction: column;
    justify-content: center;
  }
  h1 {
    background: linear-gradient(135deg, #29B5E8 0%, #005682 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-size: 2.8rem;
    font-weight: 800;
    margin-bottom: 20px;
  }
  h2 {
    color: #86868b;
    font-size: 1.4rem;
    font-weight: 500;
    margin-top: -10px;
    margin-bottom: 30px;
  }
  .card {
    background: rgba(255, 255, 255, 0.4);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(255, 255, 255, 0.6);
    border-radius: 16px;
    padding: 24px;
    box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.04);
    margin-top: 10px;
  }
  .highlight {
    color: #29B5E8;
    font-weight: 700;
  }
  ul {
    font-size: 1.1rem;
    line-height: 1.6;
  }
  li {
    margin-bottom: 8px;
  }
---

# Slide 1: Killing Shadow AI
## The Cortex AI Governance Illusion

<div class="card">

- Relying on LLM prompt-level controls to enforce enterprise security policies is a <span class="highlight">governance failure</span>.
- Probabilistic models are inherently non-deterministic, making raw APIs highly vulnerable to semantic bypasses.
- True enterprise safety requires inline, deterministic interdiction before execution occurs.

</div>

---

# Slide 2: The Data Leakage Threat
## How Model Context Protocol Exposes Storage

<div class="card">

- Downstream Cortex LLMs generate tool calls dynamically via Model Context Protocol (MCP).
- Semantic jailbreaks bypass standard catalog limits by altering query parameters or path variables.
- Raw file structures and restricted database tables are leaked directly into <span class="highlight">unstructured model logs</span>.

</div>

---

# Slide 3: Sovereign Interceptor
## Edge Validation Middleware

<div class="card">

- We deploy a localized **Zero-Trust MCP Ingress Gateway** as a security middleware layer.
- Incoming tool-call payloads are intercepted at the network level and validated against strict schemas.
- Enforces OBO (On-Behalf-Of) token verification, path canonicalization (`os.path.normpath`), and a Metadata Containment Map.

</div>

---

# Slide 4: Deterministic Guarantees
## Proof of Integrity

<div class="card">

- Validated using our automated security test harness:
  - **Aadhaar/PAN Redaction**: Overwritten in-place to prevent credential leaks.
  - **Directory Traversal (`../../`)**: Detected and blocked at the canonicalization layer.
  - **SQL injection WAF**: Restricts SQL command structures, returning strict 403 errors on command injections.

</div>

---

# Slide 5: Eliminate Shadow AI
## Get the Sovereign MCP Gateway Code

<div class="card">

- Establish a robust, zero-hop security layer for your Snowflake Cortex integrations.
- Read the full "Towards Data Science" whitepaper detailing code blocks and deployment configurations.
- Access the production-ready code repository:
  - <span class="highlight">Link to GitHub & Full Article in Comments Below!</span>

</div>
