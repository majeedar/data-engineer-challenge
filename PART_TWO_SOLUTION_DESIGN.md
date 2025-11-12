# Part Two: Cloud Solution Design - Concise Plan

## Architecture

**Simple Flow:**
```
IoT Sensors → Azure IoT Hub → Event Hubs → Azure Databricks → Delta Lake (Bronze/Silver/Gold) →  APIs
                                                                                                          ↓
                                                                  Power Platform (Power Automate + SharePoint + Chatbot)
                                                                                          ↓
                                                                              Customer Communication
```

**Key Principle:** Single platform (Databricks) for data processing. Power Platform for customer communication automation.

---

## Technology Stack

### Data Layer
- **Azure IoT Hub** - Device management
- **Azure Event Hubs** - Message streaming
- **Azure Data Lake Gen2** - Storage
- **Delta Lake** - ACID transactions on data lake
- **Azure Databricks** - Unified data processing (ingestion + transformation)

### Data access Layer
- **Azure API Management** - REST APIs
- **Azure Functions** - API backends

### Communication Layer (Power Platform)
- **Power Automate** - Workflow automation
- **SharePoint Online** - Documentation storage
- **Power Virtual Agents** - Chatbot interface
- **Azure OpenAI + RAG** - Intelligent answers
- **Azure DevOps** - Ticket tracking

### Monitoring Layer
- **Azure Monitor** - Infrastructure health
- **Databricks Workflows** - Job orchestration
- **Great Expectations** - Data quality

---

## Deployment

**Infrastructure as Code:** Terraform

**Key Resources:** IoT Hub, Event Hubs, ADLS Gen2, Databricks, SharePoint, Power Platform Environment

**Environments:** Dev → Staging → Production via CI/CD


---

## Data Pipeline

- **Bronze:** Raw data from Event Hubs → Delta Lake (continuous)
- **Silver:** Cleaned data, deduplication, validation (every 5 min)
- **Gold:** 1-minute aggregates (every 1 min)

---

## Monitoring

**Azure Monitor:** Infrastructure metrics, alerts (Critical/Warning/Info)

**Databricks:** Job runs, latency, resource usage

**Quality Checks:** Schema, nulls, ranges, completeness, freshness

**Quality Score:** 0-100% (>95% = good, 80-95% = warning, <80% = critical)

---

## Customer Communication (Power Platform)

### 1. Automated Quality Reports
- **Power Automate** queries Databricks daily at 8 AM
- Generates PDF report per customer
- Emails report and stores in **SharePoint**

### 2. AI Documentation Chatbot
- **SharePoint** stores all documentation
- **Azure OpenAI + RAG** answers questions from SharePoint docs
- **Power Virtual Agents** provides chatbot interface
- 24/7 instant answers, creates tickets if needed

### 3. Automated Ticket System
- **Power Automate** receives requests (email/portal/chatbot)
- AI categorizes and routes to **Azure DevOps**
- Sends confirmation, tracks SLA, updates customer
- Auto-resolves common issues from SharePoint knowledge base

