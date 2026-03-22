# Omni Semantic Layer Setup

Configure an Omni model branch with descriptions, relationships, AI context, and sample queries to optimize for AI chatbot usage.

## Trigger

Activate when the user asks to "set up the semantic layer", "add descriptions to the model", "optimize for AI", or "configure context engineering" in Omni.

## Prerequisites

- `OMNI_API_KEY` environment variable
- `OMNI_BASE_URL` environment variable
- An existing Omni branch (use `omni-branch-creator` skill first)
- Knowledge of the source tables and their business logic

## Deployment Rules

**NEVER deploy directly to production.** All changes follow this workflow:

1. **Deploy to branch** → `python3 build_semantic_layer.py` (deploys to branch only)
2. **Validate** → `python3 validate_omni_model.py` (must pass all checks)
3. **Review in Omni** → User audits the branch in the Omni UI
4. **Merge to production** → `python3 validate_omni_model.py --merge` (re-validates then merges)

If asked to "push to production", "merge", or "go live", always confirm the branch has been validated and reviewed first. Do not skip the branch step.

## Workflow

### Step 1: Discover the Branch and Its Schema

List models to find the target branch:

```bash
curl -s -L "$OMNI_BASE_URL/api/v1/models" \
  -H "Authorization: Bearer $OMNI_API_KEY" | python3 -c "
import json, sys
models = json.load(sys.stdin)
for m in models.get('records', []):
    if m.get('modelKind') == 'BRANCH':
        print(f'{m[\"name\"]} -> {m[\"id\"]}')"
```

Then fetch the current YAML to understand existing views and topics:

```bash
curl -s -L "$OMNI_BASE_URL/api/v1/models/{MODEL_ID}/yaml?branchId={BRANCH_ID}" \
  -H "Authorization: Bearer $OMNI_API_KEY"
```

### Step 2: Build View YAML with Descriptions

For each table, create or update a `.view` YAML file with field-level descriptions, synonyms, and formatting.

Key fields to always describe:
- Fields with misleading names (e.g., `Competitor__c`)
- Boolean fields that need usage context (e.g., `IsClosed` vs `IsWon`)
- Polymorphic lookups (e.g., `WhatId`)
- Duplicate fields (e.g., `AcctName` vs `Name`)
- Date/fiscal fields with non-obvious definitions

Example view YAML:

```yaml
view: sf_opportunities
  sql_table_name: DEMO_DB.PUBLIC.SF_OPPORTUNITIES

  dimensions:
    competitor_c:
      sql: ${TABLE}.Competitor__c
      label: "Win Channel / Competitor"
      description: "MISLEADING NAME: For WON deals, stores win attribution channel (CH - xxx). For LOST deals, stores the competitor who won. NULL for open deals."
      synonyms: ["win channel", "competitor", "channel wins", "win source"]

    is_closed:
      sql: ${TABLE}.IsClosed
      label: "Is Closed"
      description: "TRUE for both Closed Won AND Closed Lost. Use with Is Won to distinguish wins from losses."

    is_won:
      sql: ${TABLE}.IsWon
      label: "Is Won"
      description: "TRUE only for Closed Won deals. IsClosed=TRUE + IsWon=FALSE means Closed Lost."

    fiscal_year:
      sql: ${TABLE}.FiscalYear
      label: "Fiscal Year"
      description: "July-start fiscal year. FY25 = Jul 2024 through Jun 2025."
      synonyms: ["FY", "fiscal"]

  measures:
    total_amount:
      sql: ${TABLE}.Amount
      type: sum
      label: "Total Deal Value"
      description: "Sum of deal amounts in USD"
      format: "$#,##0"

    win_rate:
      sql: "CAST(SUM(CASE WHEN ${is_won} THEN 1 ELSE 0 END) AS FLOAT) / NULLIF(SUM(CASE WHEN ${is_closed} THEN 1 ELSE 0 END), 0)"
      type: number
      label: "Win Rate"
      description: "Percentage of closed deals that were won. Only counts IsClosed=TRUE deals in denominator."
      format: "0.0%"
```

### Step 3: Deploy to Branch (NOT production)

Deploy YAML to the branch for testing:

```bash
python3 build_semantic_layer.py
```

This deploys all views, relationships, topic, and model config to the branch. It does NOT merge to production — that requires `--merge` after validation passes.

### Step 4: Define Relationships

Create a relationships file connecting tables:

```yaml
# relationships.yaml
relationships:
  - name: account_to_opportunities
    from: sf_accounts
    to: sf_opportunities
    type: one_to_many
    join: ${sf_accounts.id} = ${sf_opportunities.account_id}

  - name: account_to_activities
    from: sf_accounts
    to: sf_activities
    type: one_to_many
    join: ${sf_accounts.id} = ${sf_activities.account_id}

  - name: activities_to_opportunities
    from: sf_activities
    to: sf_opportunities
    type: many_to_one
    join: ${sf_activities.what_id} = ${sf_opportunities.id}

  - name: contacts_to_accounts
    from: sf_contacts
    to: sf_accounts
    type: many_to_one
    join: ${sf_contacts.account_id} = ${sf_accounts.id}

  - name: campaign_members_to_contacts
    from: sf_campaign_members
    to: sf_contacts
    type: many_to_one
    join: ${sf_campaign_members.contact_id} = ${sf_contacts.id}

  - name: users_to_opportunities
    from: sf_users
    to: sf_opportunities
    type: one_to_many
    join: ${sf_users.id} = ${sf_opportunities.owner_id}
```

### Step 5: Add AI Context

Add `ai_context` to the topic to teach Omni's AI (Blobby) the business rules:

```yaml
topic: salesforce_analytics
  ai_context: |
    This is a SaaS company's Salesforce CRM data.

    CRITICAL FIELD NOTES:
    - Competitor__c is MISLEADINGLY named. For WON deals it stores the win attribution
      channel (values starting with 'CH -' like 'CH - Partner Referral'). For LOST deals
      it stores the competitor who won. For open deals it is NULL.
    - "Channel Wins" means: Competitor__c LIKE 'CH%' AND StageName = 'Closed Won'
    - IsClosed is TRUE for BOTH won AND lost deals. Always pair with IsWon.
    - FiscalYear uses July start. FY25 = Jul 2024 through Jun 2025.
    - WhatId in Activities is a polymorphic lookup usually pointing to an Opportunity.
    - AcctName and Name on Accounts are identical (legacy duplication).
    - LeadSource on Contacts is original source only. Campaign attribution is in Campaign Members.
    - Win Rate = COUNT(IsWon=TRUE) / COUNT(IsClosed=TRUE), not divided by all deals.

    COMMON QUERIES:
    - Pipeline: WHERE IsClosed = FALSE
    - FY25 Wins: WHERE FiscalYear = 2025 AND IsWon = TRUE
    - Activity by rep: GROUP BY OwnerName, Type
```

### Step 6: Add Sample Queries

Create example question-answer pairs that teach the AI correct patterns:

```yaml
  sample_queries:
    - question: "How many deals did we win from referral partners in FY25?"
      fields: [sf_opportunities.count, sf_opportunities.total_amount]
      filters:
        sf_opportunities.competitor_c: "CH - Partner Referral"
        sf_opportunities.stage_name: "Closed Won"
        sf_opportunities.fiscal_year: "2025"

    - question: "What is our win rate by region?"
      fields: [sf_opportunities.region_c, sf_opportunities.win_rate]
      filters:
        sf_opportunities.is_closed: "true"
```

### Step 7: Validate

Run the comprehensive model validator:

```bash
python3 validate_omni_model.py
```

This checks:
1. Omni API validation (remote errors/warnings)
2. Format strings (e.g., `usd` is invalid → use `usdcurrency`)
3. Aggregate types (e.g., `number` is invalid → use `sum`, `count`, etc.)
4. Topic join graph (verifies each topic join has a matching relationship)
5. View reachability (ensures all views are reachable from base_view)
6. Relationship field references (verifies `${view.field}` refs exist)

Fix all failures before proceeding. The script outputs suggested fixes for each error.

You can also validate locally before deploying:

```bash
python3 validate_omni_model.py --local
```

### Step 8: Review in Omni

After validation passes, the user should review the branch in the Omni UI:
- Open the branch URL provided by the build script
- Test the AI chatbot with sample questions
- Verify field labels, formats, and join behavior

### Step 9: Merge to Production

Only after validation passes AND user review:

```bash
python3 validate_omni_model.py --merge
```

This re-runs all validation checks and only merges if everything passes.

Alternatively via build script (also validates first):

```bash
python3 build_semantic_layer.py --merge
```

## Checklist

- [ ] All gotcha fields have descriptions and synonyms
- [ ] Relationships defined between all related tables
- [ ] ai_context covers critical business rules
- [ ] sample_queries cover the top 5-10 common questions
- [ ] Hidden fields marked (e.g., duplicate AcctName)
- [ ] Measures include format strings
- [ ] Deployed to branch (NOT production)
- [ ] `validate_omni_model.py` passes with 0 failures
- [ ] Branch reviewed in Omni UI
- [ ] Merged to production with `--merge` flag
