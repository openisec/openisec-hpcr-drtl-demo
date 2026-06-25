# Architecture

Updated: 2026-06-04

---

## Overview

Openisec HPCRD is an **AI Decision and Agent Governance Platform**.

It helps organizations design, approve, monitor, and evidence both human and AI Agent decisions — covering security, IT, AI adoption, vendor selection, and business governance.

Core concept: **H / P / C / R / D / Log**

| Field | Meaning |
|-------|---------|
| H | History / Background — context and situation |
| P | Pro — reasons to proceed |
| C | Con — reasons to reconsider |
| R | Recommendation — structured recommendation based on H/P/C |
| D | Decision — final decision by human or approved AI Agent |
| Log | Full audit trail of who decided what, when, and why |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js on Cloud Run |
| Backend | FastAPI (Python 3.12) on Cloud Run |
| Database | Cloud SQL for PostgreSQL |
| AI | Vertex AI Gemini Flash |
| Email | Resend |
| IaC | Terraform |
| CI/CD | GitHub Actions + Snyk |

---

## Environments

| Env | GCP Project |
|-----|-------------|
| dev | openisec-dev-XXXXXX |
| stg | openisec-stg-XXXXXX |
| prd | openisec-prd-XXXXXX |

---

## Core Data Model

### Decision Record (H/P/C/R/D/Log)

```json
{
  "id": "uuid",
  "org_id": "uuid",
  "title": "string",
  "decision_type": "security | ai_adoption | it_investment | vendor_selection | business | other",

  "history": "string — background and context",
  "pro": ["string"],
  "con": ["string"],
  "recommendation": ["string"],

  "actor_type": "Human | AI Agent | Hybrid | System",
  "agent_name": "string | null",
  "relevant_preapproval_id": "uuid | null",
  "relevant_preapproval_title": "string | null",
  "preapproval_found": "boolean | null",

  "decision": "string",
  "decision_by": "string — user name or agent name",
  "approval_status": "Approved | Rejected | Pending | Escalated | Blocked",
  "execution_status": "Not Started | Running | Completed | Failed | Blocked",

  "risk_score": "0-100",
  "risk_category": ["string"],
  "response_confidence": {
    "score": "0-100",
    "level": "high | medium | low | insufficient_context",
    "limiting_factors": ["string"]
  },

  "created_at": "timestamp",
  "updated_at": "timestamp",
  "log": [
    {
      "timestamp": "timestamp",
      "actor": "string",
      "actor_type": "Human | AI Agent | System",
      "action": "string",
      "detail": "string"
    }
  ]
}
```

---

## AI Agent Governance

### Agent Types

| Type | Role |
|------|------|
| Coordinator | Manages overall workflow, task decomposition, delegates to Workers and Checkers |
| Worker | Executes specific tasks: analysis, report generation, draft creation |
| Checker | Validates Worker output: accuracy, Preapproval compliance, risk assessment |

### Agent Record

```json
{
  "id": "uuid",
  "org_id": "uuid",
  "agent_name": "string",
  "description": "string",
  "agent_type": "Coordinator | Worker | Checker",
  "status": "Draft | Active | Suspended",
  "owner": "string",

  "what": "string",
  "why": "string",
  "who": "string",
  "when": "string",
  "where": "string",
  "how": "string",

  "input_spec": "string",
  "output_spec": "string",
  "constraints": ["string"],
  "prohibited_actions": ["string"],

  "allowed_data_sources": ["string"],
  "allowed_apis": ["string"],
  "write_permission": "boolean",
  "external_communication": "boolean",

  "trigger_type": "Manual | Scheduled | Event-based | API",
  "risk_level": "Low | Medium | High | Critical",
  "checker_required": "boolean",
  "human_approval_required": "boolean",
  "confidence_threshold": "0-100",
  "dry_run_mode": "boolean",

  "version": "string",
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

### Preapproval Record

```json
{
  "id": "uuid",
  "org_id": "uuid",
  "preapproval_name": "string",
  "description": "string",
  "applicable_agent_id": "uuid",
  "agent_role": "Coordinator | Worker | Checker",

  "allowed_actions": ["string"],
  "prohibited_actions": ["string"],
  "scope": "string",
  "data_access_level": "string",
  "execution_limit": "string",

  "risk_level": "Low | Medium | High | Critical",
  "human_approval_required": "boolean",
  "human_approval_condition": "string | null",

  "expiry_date": "date",
  "owner": "string",
  "approver": "string",
  "review_frequency": "string",
  "evidence_required": "boolean",
  "notification_rule": "string",

  "status": "Draft | Active | Suspended | Expired",
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

### Preapproval Evaluation Flow

```
AI Agent requests action
        ↓
POST /api/preapprovals/evaluate
        ↓
Relevant Preapproval found?
   ├── YES → Preapproval Active?
   │            ├── YES → Human Approval Required?
   │            │            ├── NO  → Execute + Log
   │            │            └── YES → Approval Inbox → Human Decision → Execute or Reject + Log
   │            └── NO  → Block + Alert
   └── NO  → Block workflow
              Create approval request
              Send admin alert (email)
              Create Decision Log (status: Blocked)
              Wait for human approval + Preapproval registration
```

### Approval Matrix

| Risk Level | Required Approval |
|------------|------------------|
| Low | Preapproval auto-execution allowed |
| Medium | Manager approval |
| High | Admin approval |
| Critical | Executive approval |

---

## API Structure

### Decision API
```
POST   /api/decisions
GET    /api/decisions/{id}
PATCH  /api/decisions/{id}
POST   /api/decisions/{id}/approve
POST   /api/decisions/{id}/reject
```

### Agent Registry API
```
GET    /api/agents
POST   /api/agents
GET    /api/agents/{id}
PATCH  /api/agents/{id}
POST   /api/agents/{id}/suspend
```

### Preapproval API
```
GET    /api/preapprovals
POST   /api/preapprovals
GET    /api/preapprovals/{id}
PATCH  /api/preapprovals/{id}
POST   /api/preapprovals/evaluate
```

### Agent Task API
```
POST   /api/agent-tasks
GET    /api/agent-tasks/{id}
PATCH  /api/agent-tasks/{id}
POST   /api/agent-tasks/{id}/cancel
```

### Agent Message API
```
POST   /api/agent-messages
GET    /api/agent-messages?task_id={task_id}
```

---

## Screen Structure

| Screen | Description |
|--------|-------------|
| Decision Workspace | Create and manage H/P/C/R/D records (human or Agent) |
| AI Agent Registry | Create, edit, suspend Agents with Prompt Builder UI |
| Preapproval Center | Register and manage Agent Preapprovals |
| Agent Workflow Monitor | Real-time Agent execution status |
| Approval Inbox | Human approval queue for pending decisions |
| Decision Log | Full audit history |
| Policy / Rule Settings | Approval matrix, risk rules, prohibited actions |
| Reports | Monthly, audit, and executive reports |
| Admin Settings | Org settings, users, Kill Switch |

---

## MVP Phases

### Phase 1 (Current)
- H / P / C / R / D / Log core
- Actor Type field
- Relevant Preapproval field
- Preapproval registration UI
- Blocked state when no Preapproval found
- Approval Inbox
- Decision Log

### Phase 2
- AI Agent Registry
- Agent Type: Coordinator / Worker / Checker
- Prompt Builder UI (5W1H + Risk + Output + Approval)
- Agent Task API
- Agent Message API

### Phase 3
- Agent Workflow Monitor
- Checker Agent execution
- Approval Matrix
- Dry Run / Simulation Mode
- Kill Switch (all agents, specific agent, specific workflow)
- Reports (monthly, audit, executive)

---

## Security

| Requirement | Implementation |
|-------------|---------------|
| OWASP Top 10:2025 | All components |
| Snyk SAST | CI/CD code scanning |
| Snyk SCA | Dependency scanning |
| Snyk IaC | Terraform scanning |
| SBOM | Generated in CI/CD |
| Password hashing | Argon2id |
| HTTPS + HSTS | All traffic |
| Secret management | GCP Secret Manager (no .env files) |
| Session tokens | HTTPOnly + Secure + SameSite=Lax |
| Rate limiting | Authentication endpoints |
| Audit logging | All operations logged |

## Data Isolation

- Logical: `org_{uuid}` schema per organization
- Physical: separate DB for enterprise (future)
