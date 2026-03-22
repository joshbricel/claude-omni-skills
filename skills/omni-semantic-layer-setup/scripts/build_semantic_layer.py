"""
Build the semantic layer for the Salesforce Demo branch in Omni.
Uses the POST /api/v1/models/{modelId}/yaml endpoint to write view, topic,
relationship, and skill YAML files.

Reference: https://docs.omni.co/api/models/create-or-update-yaml-files
AI Optimization: https://docs.omni.co/modeling/develop/ai-optimization
"""

import os
import requests
import sys

BASE_URL = os.environ.get("OMNI_BASE_URL", "")
API_KEY = os.environ.get("OMNI_API_KEY", "")
MODEL_ID = os.environ.get("OMNI_MODEL_ID", "")
BRANCH_ID = os.environ.get("OMNI_BRANCH_ID", "")

if not all([BASE_URL, API_KEY, MODEL_ID, BRANCH_ID]):
    print("ERROR: Missing required environment variables.")
    print("Set: OMNI_BASE_URL, OMNI_API_KEY, OMNI_MODEL_ID, OMNI_BRANCH_ID")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


def post_yaml(file_name: str, yaml_content: str):
    """Write a YAML file to the branch."""
    url = f"{BASE_URL}/api/v1/models/{MODEL_ID}/yaml?branchId={BRANCH_ID}"
    resp = requests.post(url, headers=HEADERS, json={
        "fileName": file_name,
        "yaml": yaml_content,
        "mode": "combined",
    })
    if resp.status_code == 200:
        print(f"  OK: {file_name}")
    else:
        print(f"  FAIL: {file_name} -> {resp.status_code}: {resp.text}")
        return False
    return True


# ── VIEW YAML FILES ─────────────────────────────────────────────────────────

SF_USERS_VIEW = '''\
schema: PUBLIC
table_name: SF_USERS

dimensions:
  id:
    sql: '"ID"'
    format: ID
    primary_key: true
    hidden: true

  firstname:
    sql: '"FIRSTNAME"'
    label: First Name
    hidden: true

  lastname:
    sql: '"LASTNAME"'
    label: Last Name
    hidden: true

  name:
    sql: '"NAME"'
    label: Rep Name
    description: Full name of the sales representative
    synonyms:
      - sales rep
      - rep
      - salesperson
      - AE
      - account executive

  email:
    sql: '"EMAIL"'
    label: Email
    hidden: true

  userrole:
    sql: '"USERROLE"'
    label: Role
    description: "Sales role in the organization hierarchy"
    sample_values:
      - Sales Rep
      - Senior Sales Rep
      - Account Executive
      - Sales Manager
      - Regional Director
      - VP of Sales
    synonyms:
      - title
      - position
      - job role

  profile:
    sql: '"PROFILE"'
    label: Profile
    hidden: true

  region__c:
    sql: '"REGION__C"'
    label: Region
    description: Sales region assignment
    sample_values:
      - Northeast
      - Southeast
      - Midwest
      - West
      - Southwest
    synonyms:
      - territory
      - geo
      - geography

  office__c:
    sql: '"OFFICE__C"'
    label: Office
    description: Office location
    synonyms:
      - location
      - branch

  isactive:
    sql: '"ISACTIVE"'
    label: Is Active
    description: Whether the user is currently active. FALSE means deactivated or departed.

  managerid:
    sql: '"MANAGERID"'
    hidden: true

  createddate:
    sql: '"CREATEDDATE"'
    label: Created Date
    hidden: true

measures:
  count:
    aggregate_type: count
    label: Number of Reps
    synonyms:
      - headcount
      - rep count
      - team size
'''

SF_ACCOUNTS_VIEW = '''\
schema: PUBLIC
table_name: SF_ACCOUNTS

ai_context: |
  AcctName and Name contain identical values. AcctName is a legacy duplicate field.
  Always use Name as the canonical account name field.
  AnnualRevenue is the account's own revenue, NOT our revenue from them.

dimensions:
  id:
    sql: '"ID"'
    format: ID
    primary_key: true
    hidden: true

  name:
    sql: '"NAME"'
    label: Account Name
    description: Company name
    synonyms:
      - company
      - client
      - customer
      - account

  acctname:
    sql: '"ACCTNAME"'
    label: Account Name (Legacy)
    description: "DUPLICATE of Name. Legacy field kept for backward compatibility. Use Name instead."
    hidden: true

  industry:
    sql: '"INDUSTRY"'
    label: Industry
    description: Industry vertical of the account
    sample_values:
      - Technology
      - Financial Services
      - Healthcare
      - E-Commerce
      - SaaS / Software
    synonyms:
      - vertical
      - sector

  type:
    sql: '"TYPE"'
    label: Account Type
    description: "Relationship type with this account"
    all_values:
      - Customer
      - Prospect
      - Partner
      - Former Customer
    synonyms:
      - account status
      - customer type

  region__c:
    sql: '"REGION__C"'
    label: Region
    sample_values:
      - Northeast
      - Southeast
      - Midwest
      - West
      - Southwest
    synonyms:
      - territory
      - geo

  office__c:
    sql: '"OFFICE__C"'
    label: Office
    synonyms:
      - location
      - branch

  annualrevenue:
    sql: '"ANNUALREVENUE"'
    label: Annual Revenue
    description: "Self-reported annual revenue of the account company. This is NOT our revenue from them."
    format: usdcurrency
    ai_context: "This is the account's own annual revenue, not what we bill them."
    synonyms:
      - company revenue
      - ARR

  numberofemployees:
    sql: '"NUMBEROFEMPLOYEES"'
    label: Employee Count
    synonyms:
      - headcount
      - company size
      - employees

  phone:
    sql: '"PHONE"'
    hidden: true

  website:
    sql: '"WEBSITE"'
    label: Website
    hidden: true

  ownerid:
    sql: '"OWNERID"'
    hidden: true

  ownername:
    sql: '"OWNERNAME"'
    label: Account Owner
    description: Sales rep who owns this account
    synonyms:
      - rep
      - owner

  billingstate:
    sql: '"BILLINGSTATE"'
    label: State
    synonyms:
      - billing state

  billingcity:
    sql: '"BILLINGCITY"'
    label: City
    synonyms:
      - billing city

  createddate:
    sql: '"CREATEDDATE"'
    label: Created Date

  lastmodifieddate:
    sql: '"LASTMODIFIEDDATE"'
    hidden: true

  isdeleted:
    sql: '"ISDELETED"'
    hidden: true

  referralcompany:
    sql: '"REFERRALCOMPANY"'
    label: Referral Company
    description: Company that referred this account. Can be joined to Activities or Opportunities via ReferralCompany.
    synonyms:
      - referral
      - referral partner
      - referring company

measures:
  count:
    aggregate_type: count
    label: Number of Accounts
    synonyms:
      - account count
      - customer count
'''

SF_CONTACTS_VIEW = '''\
schema: PUBLIC
table_name: SF_CONTACTS

ai_context: |
  LeadSource is the ORIGINAL source of the lead, not ongoing campaign attribution.
  For campaign-level attribution, join to SF_Campaign_Members via ContactId.

dimensions:
  id:
    sql: '"ID"'
    format: ID
    primary_key: true
    hidden: true

  firstname:
    sql: '"FIRSTNAME"'
    label: First Name
    hidden: true

  lastname:
    sql: '"LASTNAME"'
    label: Last Name
    hidden: true

  name:
    sql: '"NAME"'
    label: Contact Name
    description: Full name of the contact person
    synonyms:
      - person
      - individual
      - contact

  accountid:
    sql: '"ACCOUNTID"'
    hidden: true

  accountname:
    sql: '"ACCOUNTNAME"'
    label: Account Name
    synonyms:
      - company

  title:
    sql: '"TITLE"'
    label: Job Title
    description: Job title at the company (CEO, VP, Director, etc.)
    sample_values:
      - CEO
      - CFO
      - VP of Operations
      - Director of IT
      - Facilities Manager
    synonyms:
      - role
      - position

  department:
    sql: '"DEPARTMENT"'
    label: Department
    sample_values:
      - Executive
      - Finance
      - Operations
      - IT
      - Marketing

  email:
    sql: '"EMAIL"'
    label: Email
    hidden: true

  phone:
    sql: '"PHONE"'
    hidden: true

  mailingstate:
    sql: '"MAILINGSTATE"'
    label: State
    synonyms:
      - mailing state

  mailingcity:
    sql: '"MAILINGCITY"'
    label: City

  leadsource:
    sql: '"LEADSOURCE"'
    label: Lead Source
    description: "Original source of the lead when first created. NOT the same as campaign attribution. For marketing channel analysis, use Campaign Members instead."
    ai_context: "This is the original lead source only. For ongoing campaign attribution, join to sf_campaign_members."
    sample_values:
      - Web
      - Phone Inquiry
      - Partner Referral
      - Event
      - Cold Call
    synonyms:
      - source
      - origin

  ownerid:
    sql: '"OWNERID"'
    hidden: true

  hasoptedoutofemail:
    sql: '"HASOPTEDOUTOFEMAIL"'
    label: Email Opt-Out
    description: TRUE means do not send marketing emails
    hidden: true

  donotcall:
    sql: '"DONOTCALL"'
    hidden: true

  isdeleted:
    sql: '"ISDELETED"'
    hidden: true

  createddate:
    sql: '"CREATEDDATE"'
    label: Created Date

  lastactivitydate:
    sql: '"LASTACTIVITYDATE"'
    label: Last Activity Date
    description: Date of the most recent activity logged against this contact

measures:
  count:
    aggregate_type: count
    label: Number of Contacts
    synonyms:
      - contact count
      - people count
'''

SF_OPPORTUNITIES_VIEW = '''\
schema: PUBLIC
table_name: SF_OPPORTUNITIES

ai_context: |
  CRITICAL FIELD NOTES:
  - Competitor__c is MISLEADINGLY named. For WON deals it stores the win attribution
    channel (values starting with 'CH -'). For LOST deals it stores the competitor who won.
    For open deals it is NULL.
  - "Channel Wins" = WHERE Competitor__c LIKE 'CH%' AND StageName = 'Closed Won'
  - IsClosed is TRUE for BOTH won AND lost deals. Always pair with IsWon.
  - FiscalYear uses July start. FY25 = Jul 2024 through Jun 2025.
  - AcctName is a denormalized copy of the account name for convenience.
  - Win Rate = won deals / closed deals (not all deals).

dimensions:
  id:
    sql: '"ID"'
    format: ID
    primary_key: true
    hidden: true

  name:
    sql: '"NAME"'
    label: Opportunity Name
    description: "Auto-generated name: AccountName - Type - CloseDate"

  accountid:
    sql: '"ACCOUNTID"'
    hidden: true

  acctname:
    sql: '"ACCTNAME"'
    label: Account Name
    description: Denormalized account name for reporting
    synonyms:
      - company
      - client
      - customer

  stagename:
    sql: '"STAGENAME"'
    label: Stage
    description: Current deal pipeline stage
    all_values:
      - Prospecting
      - Qualification
      - Needs Analysis
      - Value Proposition
      - Id. Decision Makers
      - Perception Analysis
      - Proposal/Price Quote
      - Negotiation/Review
      - Closed Won
      - Closed Lost
    synonyms:
      - status
      - deal stage
      - pipeline stage

  amount:
    sql: '"AMOUNT"'
    label: Deal Amount
    description: Deal value in USD
    format: usdcurrency
    synonyms:
      - deal value
      - deal size
      - contract value

  closedate:
    sql: '"CLOSEDATE"'
    label: Close Date
    description: Expected or actual close date
    synonyms:
      - closed date
      - expected close

  fiscalyear:
    sql: '"FISCALYEAR"'
    label: Fiscal Year
    description: "Fiscal year based on July start. FY25 = Jul 2024 through Jun 2025. FY26 = Jul 2025 through Jun 2026."
    ai_context: "IMPORTANT: Fiscal year starts in July, NOT January. FY25 covers Jul 2024 - Jun 2025. When users say 'this year' or 'FY26', use FiscalYear = 2026."
    sample_values:
      - 2024
      - 2025
      - 2026
      - 2027
    synonyms:
      - FY
      - fiscal

  fiscalquarter:
    sql: '"FISCALQUARTER"'
    label: Fiscal Quarter
    description: "Fiscal quarter based on July FY start. Q1=Jul-Sep, Q2=Oct-Dec, Q3=Jan-Mar, Q4=Apr-Jun."
    ai_context: "Fiscal quarters: Q1=Jul-Sep, Q2=Oct-Dec, Q3=Jan-Mar, Q4=Apr-Jun. NOT calendar quarters."
    all_values:
      - Q1
      - Q2
      - Q3
      - Q4
    synonyms:
      - quarter
      - FQ

  type:
    sql: '"TYPE"'
    label: Opportunity Type
    description: "Type of business"
    all_values:
      - New Business
      - Existing Business
      - Renewal
      - Add-On
    synonyms:
      - deal type
      - business type

  leadsource:
    sql: '"LEADSOURCE"'
    label: Lead Source
    synonyms:
      - source
      - channel

  ownerid:
    sql: '"OWNERID"'
    hidden: true

  ownername:
    sql: '"OWNERNAME"'
    label: Sales Rep
    description: The sales rep who owns this opportunity
    synonyms:
      - rep
      - owner
      - AE
      - salesperson

  region__c:
    sql: '"REGION__C"'
    label: Region
    sample_values:
      - Northeast
      - Southeast
      - Midwest
      - West
      - Southwest
    synonyms:
      - territory
      - geo
      - geography

  office__c:
    sql: '"OFFICE__C"'
    label: Office
    synonyms:
      - location

  industry__c:
    sql: '"INDUSTRY__C"'
    label: Industry
    description: Industry of the related account
    synonyms:
      - vertical
      - sector

  probability:
    sql: '"PROBABILITY"'
    label: Win Probability
    description: Win probability percentage, auto-set by stage
    format: percent

  forecastcategory:
    sql: '"FORECASTCATEGORY"'
    label: Forecast Category
    all_values:
      - Pipeline
      - Best Case
      - Commit
      - Omitted
      - Closed
    synonyms:
      - forecast
      - forecast bucket

  isclosed:
    sql: '"ISCLOSED"'
    label: Is Closed
    description: "TRUE for BOTH Closed Won AND Closed Lost. This does NOT mean the deal was won. Use Is Won to distinguish."
    ai_context: "IsClosed=TRUE includes BOTH wins AND losses. Always combine with IsWon to identify actual wins."

  iswon:
    sql: '"ISWON"'
    label: Is Won
    description: "TRUE only for Closed Won deals. IsClosed=TRUE + IsWon=FALSE = Closed Lost."
    ai_context: "Use this field to identify wins. IsWon=TRUE means Closed Won. IsWon=FALSE + IsClosed=TRUE means Closed Lost."

  competitor_c:
    sql: '"COMPETITOR__C"'
    label: Win Channel / Competitor
    description: "MISLEADING FIELD NAME. For WON deals: win attribution channel (CH - Partner Referral, CH - Existing Relationship, etc.). For LOST deals: competitor who won (Acme Corp, etc.). NULL for open deals."
    ai_context: "This field is confusingly named. For WON deals it contains the win attribution channel (values like 'CH - Partner Referral'). The pattern Competitor__c LIKE 'CH%' AND StageName = 'Closed Won' identifies Channel Wins. For LOST deals it contains the competitor who won."
    sample_values:
      - CH - Existing Relationship
      - CH - Partner Referral
      - CH - Direct Outreach
      - CH - RFP Response
      - Acme Corp
      - Globex Inc
      - No Decision
    synonyms:
      - win channel
      - competitor
      - channel wins
      - win source
      - how we won
      - why we lost

  nextstep:
    sql: '"NEXTSTEP"'
    hidden: true

  description:
    sql: '"DESCRIPTION"'
    hidden: true

  createddate:
    sql: '"CREATEDDATE"'
    label: Created Date

  lastmodifieddate:
    sql: '"LASTMODIFIEDDATE"'
    hidden: true

  isdeleted:
    sql: '"ISDELETED"'
    hidden: true

  referralcompany:
    sql: '"REFERRALCOMPANY"'
    label: Referral Company
    description: Referral partner who sourced this deal. Inherited from the Account.
    synonyms:
      - referral
      - referral partner

measures:
  count:
    aggregate_type: count
    label: Number of Opportunities
    synonyms:
      - deal count
      - opp count
      - number of deals

  total_amount:
    sql: '"AMOUNT"'
    aggregate_type: sum
    label: Total Deal Value
    description: Sum of deal amounts in USD
    format: usdcurrency
    synonyms:
      - total revenue
      - total pipeline
      - bookings

  average_amount:
    sql: '"AMOUNT"'
    aggregate_type: average
    label: Average Deal Size
    format: usdcurrency
    synonyms:
      - avg deal size
      - average deal value
      - ACV

  won_count:
    sql: "CASE WHEN \\"ISWON\\" = TRUE THEN 1 ELSE 0 END"
    aggregate_type: sum
    label: Won Deals
    description: Count of Closed Won deals
    synonyms:
      - wins
      - closed won count

  closed_count:
    sql: "CASE WHEN \\"ISCLOSED\\" = TRUE THEN 1 ELSE 0 END"
    aggregate_type: sum
    label: Closed Deals
    description: Count of all closed deals (both won and lost)

  total_won_amount:
    sql: "CASE WHEN \\"ISWON\\" = TRUE THEN \\"AMOUNT\\" ELSE 0 END"
    aggregate_type: sum
    label: Total Won Revenue
    description: Sum of Amount for Closed Won deals only
    format: usdcurrency
    synonyms:
      - closed won revenue
      - won value
      - bookings

  total_pipeline:
    sql: "CASE WHEN \\"ISCLOSED\\" = FALSE THEN \\"AMOUNT\\" ELSE 0 END"
    aggregate_type: sum
    label: Open Pipeline
    description: Sum of Amount for open deals (IsClosed=FALSE)
    format: usdcurrency
    synonyms:
      - pipeline value
      - active pipeline
      - open deals
'''

SF_ACTIVITIES_VIEW = '''\
schema: PUBLIC
table_name: SF_ACTIVITIES

ai_context: |
  WhatId is a polymorphic lookup field that usually references an Opportunity ID
  (joins to SF_Opportunities.Id). WhatName is the name of that related record.
  Activities track all BD (business development) touchpoints: calls, meetings,
  emails, site visits, etc.

dimensions:
  id:
    sql: '"ID"'
    format: ID
    primary_key: true
    hidden: true

  subject:
    sql: '"SUBJECT"'
    label: Subject
    description: Brief description of the activity

  type:
    sql: '"TYPE"'
    label: Activity Type
    description: Type of BD activity performed
    all_values:
      - Call
      - Email
      - Meeting
      - Site Visit
      - Proposal Sent
      - Follow-Up
      - Networking Event
      - Lunch/Dinner
      - Conference
      - Webinar
      - Product Demo
      - Contract Review
    synonyms:
      - activity
      - touchpoint
      - interaction type

  status:
    sql: '"STATUS"'
    label: Status
    all_values:
      - Completed
      - Not Started
      - In Progress

  priority:
    sql: '"PRIORITY"'
    label: Priority
    all_values:
      - High
      - Normal
      - Low

  activitydate:
    sql: '"ACTIVITYDATE"'
    label: Activity Date
    description: Date the activity occurred or is scheduled
    synonyms:
      - date
      - when

  durationinminutes:
    sql: '"DURATIONINMINUTES"'
    label: Duration (Minutes)
    description: Length of activity in minutes. Only populated for calls, meetings, demos, and site visits.
    synonyms:
      - length
      - time spent

  accountid:
    sql: '"ACCOUNTID"'
    hidden: true

  accountname:
    sql: '"ACCOUNTNAME"'
    label: Account Name
    synonyms:
      - company
      - client

  contactid:
    sql: '"CONTACTID"'
    hidden: true

  contactname:
    sql: '"CONTACTNAME"'
    label: Contact Name
    description: Person involved in this activity
    synonyms:
      - person
      - who

  whatid:
    sql: '"WHATID"'
    label: Related Record ID
    description: "Polymorphic lookup ID. Usually references an Opportunity (SF_Opportunities.Id). Use WhatName for the display name."
    ai_context: "This is a Salesforce polymorphic lookup. In this dataset it always references an Opportunity ID. Join to SF_Opportunities via WhatId = Id."
    hidden: true

  whatname:
    sql: '"WHATNAME"'
    label: Related Opportunity
    description: Name of the related opportunity (if any)
    synonyms:
      - related deal
      - opportunity

  ownerid:
    sql: '"OWNERID"'
    hidden: true

  ownername:
    sql: '"OWNERNAME"'
    label: Sales Rep
    description: Rep who performed this activity
    synonyms:
      - rep
      - owner
      - performed by

  region__c:
    sql: '"REGION__C"'
    label: Region
    synonyms:
      - territory

  office__c:
    sql: '"OFFICE__C"'
    label: Office

  referralcompany:
    sql: '"REFERRALCOMPANY"'
    label: Referral Company
    synonyms:
      - referral

  description:
    sql: '"DESCRIPTION"'
    label: Description
    hidden: true

  isdeleted:
    sql: '"ISDELETED"'
    hidden: true

  createddate:
    sql: '"CREATEDDATE"'
    label: Created Date
    hidden: true

measures:
  count:
    aggregate_type: count
    label: Number of Activities
    synonyms:
      - activity count
      - touchpoints
      - interactions

  total_duration:
    sql: '"DURATIONINMINUTES"'
    aggregate_type: sum
    label: Total Duration (Minutes)
    description: Total minutes spent on activities
    synonyms:
      - total time
      - time spent

  avg_duration:
    sql: '"DURATIONINMINUTES"'
    aggregate_type: average
    label: Avg Duration (Minutes)
    synonyms:
      - average time
'''

SF_CAMPAIGN_MEMBERS_VIEW = '''\
schema: PUBLIC
table_name: SF_CAMPAIGN_MEMBERS

ai_context: |
  Campaign Members tracks which contacts were included in which marketing campaigns
  and whether they responded. This is the proper table for marketing attribution
  analysis, NOT the LeadSource field on Contacts.
  To attribute revenue to campaigns, join: Campaign Members -> Contacts -> Accounts -> Opportunities.

dimensions:
  id:
    sql: '"ID"'
    format: ID
    primary_key: true
    hidden: true

  campaignid:
    sql: '"CAMPAIGNID"'
    label: Campaign ID
    hidden: true

  campaignname:
    sql: '"CAMPAIGNNAME"'
    label: Campaign Name
    description: Name of the marketing campaign
    sample_values:
      - FY25 Q1 Email Blast
      - FY25 Spring Webinar Series
      - Healthcare Vertical Push
      - Regional Roadshow 2025
      - Executive Roundtable Series
    synonyms:
      - campaign
      - marketing campaign

  campaigntype:
    sql: '"CAMPAIGNTYPE"'
    label: Campaign Type
    description: Marketing channel used
    all_values:
      - Email
      - Webinar
      - Conference
      - Advertisement
      - Direct Mail
      - Partner
      - Content
      - Event
      - Referral
      - Social
    synonyms:
      - channel
      - campaign channel
      - marketing channel

  contactid:
    sql: '"CONTACTID"'
    hidden: true

  contactname:
    sql: '"CONTACTNAME"'
    label: Contact Name
    synonyms:
      - person
      - recipient

  accountid:
    sql: '"ACCOUNTID"'
    hidden: true

  accountname:
    sql: '"ACCOUNTNAME"'
    label: Account Name
    synonyms:
      - company

  status:
    sql: '"STATUS"'
    label: Member Status
    description: Campaign interaction status
    all_values:
      - Sent
      - Responded
      - Attended
      - No Show
      - Converted
    synonyms:
      - response status

  hasresponded:
    sql: '"HASRESPONDED"'
    label: Has Responded
    description: "TRUE if the member took action: Responded, Attended, or Converted"
    synonyms:
      - engaged
      - responded

  firstrespondeddate:
    sql: '"FIRSTRESPONDEDDATE"'
    label: First Responded Date
    description: Date of first engagement with the campaign

  leadsource:
    sql: '"LEADSOURCE"'
    label: Original Lead Source
    description: "Original source of the contact. NOT the campaign channel. Use Campaign Type for the marketing channel."
    ai_context: "This is the contact's original lead source, not the campaign channel. Do not confuse with Campaign Type."
    hidden: true

  createddate:
    sql: '"CREATEDDATE"'
    label: Added to Campaign Date
    description: Date the contact was added to the campaign

measures:
  count:
    aggregate_type: count
    label: Number of Campaign Members
    synonyms:
      - members
      - recipients

  response_count:
    sql: "CASE WHEN \\"HASRESPONDED\\" = TRUE THEN 1 ELSE 0 END"
    aggregate_type: sum
    label: Responses
    description: Count of members who responded, attended, or converted
    synonyms:
      - engagements
      - responses

  non_response_count:
    sql: "CASE WHEN \\"HASRESPONDED\\" = FALSE THEN 1 ELSE 0 END"
    aggregate_type: sum
    label: Non-Responses
    description: Count of members who did not respond
'''

# ── RELATIONSHIPS ───────────────────────────────────────────────────────────

RELATIONSHIPS = '''\
- join_from_view: sf_accounts
  join_to_view: sf_opportunities
  on_sql: ${sf_accounts.id} = ${sf_opportunities.accountid}
  relationship_type: one_to_many
  join_type: always_left

- join_from_view: sf_accounts
  join_to_view: sf_contacts
  on_sql: ${sf_accounts.id} = ${sf_contacts.accountid}
  relationship_type: one_to_many
  join_type: always_left

- join_from_view: sf_accounts
  join_to_view: sf_activities
  on_sql: ${sf_accounts.id} = ${sf_activities.accountid}
  relationship_type: one_to_many
  join_type: always_left

- join_from_view: sf_contacts
  join_to_view: sf_campaign_members
  on_sql: ${sf_contacts.id} = ${sf_campaign_members.contactid}
  relationship_type: one_to_many
  join_type: always_left

- join_from_view: sf_users
  join_to_view: sf_opportunities
  on_sql: ${sf_users.id} = ${sf_opportunities.ownerid}
  relationship_type: one_to_many
  join_type: always_left

- join_from_view: sf_users
  join_to_view: sf_activities
  on_sql: ${sf_users.id} = ${sf_activities.ownerid}
  relationship_type: one_to_many
  join_type: always_left

- join_from_view: sf_activities
  join_to_view: sf_opportunities
  on_sql: ${sf_activities.whatid} = ${sf_opportunities.id}
  relationship_type: many_to_one
  join_type: always_left
'''

# ── TOPIC ────────────────────────────────────────────────────────────────────

SALESFORCE_TOPIC = '''\
base_view: sf_opportunities
label: Salesforce CRM
group_label: Sales Analytics

ai_context: |
  This is a SaaS company's Salesforce CRM data modeled after a company like Omni.

  CRITICAL BUSINESS RULES:
  1. Competitor__c is MISLEADINGLY named. For WON deals it stores the win attribution
     channel (values starting with 'CH -' like 'CH - Partner Referral'). For LOST
     deals it stores the competitor who won. For open deals it is NULL.
  2. "Channel Wins" means: Competitor__c LIKE 'CH%' AND StageName = 'Closed Won'
  3. IsClosed is TRUE for BOTH Closed Won AND Closed Lost. Always combine with IsWon.
  4. FiscalYear uses a July start. FY25 = Jul 2024 - Jun 2025. FY26 = Jul 2025 - Jun 2026.
  5. Fiscal Quarters: Q1=Jul-Sep, Q2=Oct-Dec, Q3=Jan-Mar, Q4=Apr-Jun.
  6. Win Rate = Won Deals / Closed Deals. Do NOT divide by all deals.
  7. WhatId on Activities is a polymorphic lookup that references Opportunity IDs.
  8. LeadSource on Contacts is the original source only. For campaign attribution,
     use Campaign Members joined through Contacts.
  9. AcctName and Name on Accounts are identical (legacy duplicate).
  10. AnnualRevenue on Accounts is the account's own revenue, not our revenue from them.

  COMMON QUERY PATTERNS:
  - Pipeline: WHERE IsClosed = FALSE
  - FY25 Wins: WHERE FiscalYear = 2025 AND IsWon = TRUE
  - Channel Wins: WHERE Competitor__c LIKE 'CH%' AND StageName = 'Closed Won'
  - Activity by rep: GROUP BY OwnerName, Type
  - Campaign ROI: Join Campaign Members -> Contacts -> Accounts -> Opportunities

joins:
  sf_accounts:
    sf_contacts:
      sf_campaign_members: {}
  sf_activities: {}
  sf_users: {}

fields:
  - all_views.*

skills:
  pipeline_report:
    label: Pipeline Report
    description: |
      Generate a pipeline report showing open opportunities grouped by stage, region, and sales rep.
      Use sf_opportunities where IsClosed = FALSE.
      Show total deal value and count per group.
      Sort by stage in pipeline order.
    input: "Any specific filters? (e.g., region, rep, fiscal year)"

  win_analysis:
    label: Win Analysis
    description: |
      Analyze closed won deals. Show:
      1. Total wins and revenue by fiscal year
      2. Win rate using Won Deals / Closed Deals measures
      3. Top win channels from Competitor__c (values starting with 'CH -')
      4. Average deal size for wins
      Group by region and sales rep.
    input: "Which fiscal year or time period?"

  rep_activity_scorecard:
    label: Rep Activity Scorecard
    description: |
      Create a sales rep scorecard showing:
      1. Number of activities by type (calls, meetings, emails, etc.)
      2. Total activity duration in hours
      3. Number of unique accounts touched
      4. Pipeline value of related opportunities (via WhatId join)
      Group by sales rep (OwnerName).
    input: "Which time period? (e.g., this quarter, FY25)"

  campaign_performance:
    label: Campaign Performance
    description: |
      Analyze marketing campaign effectiveness:
      1. Response rate by campaign (Responses / total members)
      2. Campaign type breakdown (Email, Webinar, Event, etc.)
      3. To attribute revenue: join Campaign Members -> Contacts -> Accounts -> Opportunities
      Do NOT use LeadSource for this analysis.
    input: "Any specific campaigns or time period to focus on?"
'''

# ── MODEL CONFIG ─────────────────────────────────────────────────────────────

MODEL_CONFIG = '''\
ai_context: |
  Before generating a query, explain your field selection and reasoning.
  If the question involves fiscal year or quarter, confirm you are using
  July-start fiscal calendar (not calendar year).
  After presenting results, suggest 2-3 follow-up questions.

ai_chat_topics:
  - salesforce_crm
'''


def validate_branch():
    """Run Omni API validation and return (errors, warnings)."""
    url = f"{BASE_URL}/api/v1/models/{MODEL_ID}/validate?branchId={BRANCH_ID}"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        print(f"  Validation request failed: {resp.status_code}")
        return [], []

    result = resp.json()
    if isinstance(result, list):
        errors = [r for r in result if not r.get("is_warning", False)]
        warnings = [r for r in result if r.get("is_warning", False)]
    else:
        errors = result.get("errors", [])
        warnings = result.get("warnings", [])
    return errors, warnings


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Deploy semantic layer YAML to an Omni branch.")
    parser.add_argument("--merge", action="store_true",
                        help="After deploying and validating, merge the branch to production")
    args = parser.parse_args()

    print("Building semantic layer for Omni branch...")
    print(f"  Branch ID: {BRANCH_ID}")
    print(f"  Branch ID: {BRANCH_ID}")
    print()

    # Step 1: Deploy to branch
    files = [
        ("PUBLIC/sf_users.view", SF_USERS_VIEW),
        ("PUBLIC/sf_accounts.view", SF_ACCOUNTS_VIEW),
        ("PUBLIC/sf_contacts.view", SF_CONTACTS_VIEW),
        ("PUBLIC/sf_opportunities.view", SF_OPPORTUNITIES_VIEW),
        ("PUBLIC/sf_activities.view", SF_ACTIVITIES_VIEW),
        ("PUBLIC/sf_campaign_members.view", SF_CAMPAIGN_MEMBERS_VIEW),
        ("relationships", RELATIONSHIPS),
        ("salesforce_crm.topic", SALESFORCE_TOPIC),
        ("model", MODEL_CONFIG),
    ]

    success = 0
    fail = 0
    for file_name, yaml_content in files:
        if post_yaml(file_name, yaml_content):
            success += 1
        else:
            fail += 1

    print(f"\nDone: {success} succeeded, {fail} failed")

    if fail > 0:
        print("\nDeploy had failures. Fix errors before validating.")
        return 1

    # Step 2: Validate
    print("\nValidating...")
    errors, warnings = validate_branch()

    if errors:
        print(f"  Errors: {len(errors)}")
        for e in errors[:10]:
            msg = e.get("message", str(e)) if isinstance(e, dict) else str(e)
            print(f"    - {msg}")
    if warnings:
        print(f"  Warnings: {len(warnings)}")
        for w in warnings[:10]:
            msg = w.get("message", str(w)) if isinstance(w, dict) else str(w)
            print(f"    - {msg}")
    if not errors and not warnings:
        print("  No errors or warnings!")

    branch_url = f"{BASE_URL}/ide/model/{MODEL_ID}?branchId={BRANCH_ID}"
    print(f"\nBranch URL: {branch_url}")

    # Step 3: Gate merge behind validation + explicit flag
    if errors:
        print("\nBRANCH HAS ERRORS — will not merge. Fix errors and re-deploy.")
        print("Run validate_omni_model.py for detailed diagnostics and fix suggestions.")
        return 1

    if not args.merge:
        print("\nDeployed to branch only (not merged to production).")
        print("Review the branch in Omni, then re-run with --merge to push to production:")
        print(f"  python3 build_semantic_layer.py --merge")
        return 0

    # Merge to production
    print("\nMerging branch to production...")
    merge_url = f"{BASE_URL}/api/v1/models/{MODEL_ID}/merge?branchId={BRANCH_ID}"
    resp = requests.post(merge_url, headers=HEADERS)
    if resp.status_code == 200:
        print("  Merged successfully!")
    else:
        print(f"  Merge failed: {resp.status_code}: {resp.text}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
