# CampusOps — Complete System Design

> **An AI-powered Event Operations Agent that handles the repetitive work of running campus events and only involves humans when a real decision or approval is required.**

---

## 1. Overview

CampusOps is an AI agent built using the **Strands Agents SDK** and deployed using **Amazon Bedrock AgentCore**.

The system helps student organizations and campus event organizers manage the operational workload involved in conducting an event.

Instead of simply providing instructions, CampusOps can:

* Understand an event request written in natural language.
* Find a suitable room.
* Prepare a permission request.
* Create an event registration form.
* Send event announcements.
* Monitor registrations.
* Detect situations requiring attention.
* Send reminders when appropriate.
* Maintain the event's operational state across conversations.
* Ask for human approval when an action requires human authorization.

The system is designed around a **human-in-the-loop** model.

The agent performs operational work autonomously, but it does **not** self-authorize actions that require institutional or human approval.

---

# 2. Problem Statement

Organizing a college event involves much more than planning the event itself.

A typical organizer may need to:

1. Find a suitable room.
2. Check room capacity.
3. Obtain faculty or institutional approval.
4. Create a registration form.
5. Publish the registration link.
6. Send announcements.
7. Monitor registrations.
8. Send reminders.
9. Track attendance.
10. Prepare a final summary.

These tasks are repetitive, fragmented across different tools, and often require the organizer to manually coordinate several systems.

CampusOps aims to turn this fragmented workflow into a single agent-driven workflow.

### Traditional workflow

```text
Organizer
   │
   ├── Check room
   ├── Write permission email
   ├── Create Google Form
   ├── Create spreadsheet
   ├── Write announcement
   ├── Send emails
   ├── Check registrations
   └── Send reminders
```

### CampusOps workflow

```text
Organizer
     │
     ▼
"Run a Python workshop for 80 students next Saturday."
     │
     ▼
CampusOps Agent
     │
     ├── Find suitable room
     ├── Prepare approval request
     ├── Create registration form
     ├── Send announcement
     └── Monitor registrations
              │
              ▼
      Human decision only
      when required
```

---

# 3. Hackathon Track

## Primary Track

**Everyday Agents**

CampusOps is designed primarily for the Everyday Agents track because its primary user is an individual event organizer who wants to offload repetitive operational work.

The organizer remains the beneficiary while the agent handles their administrative workload.

The system is therefore not positioned as a general-purpose community-management platform.

---

# 4. Core Design Principle

The central design principle is:

> **The agent should do the work, not merely explain how to do the work.**

A conventional AI assistant might respond:

> "To organize a workshop, you should find a room, create a registration form, and send an announcement."

CampusOps instead performs those operations through tools.

```text
User Intent
     ↓
Agent Reasoning
     ↓
Tool Selection
     ↓
External Action
     ↓
State Update
     ↓
Monitoring
     ↓
Human Decision — only when required
```

---

# 5. Goals

## 5.1 Primary Goals

CampusOps should:

* Understand natural-language event requests.
* Convert requests into structured event information.
* Find suitable rooms.
* Handle registration setup.
* Handle event communications.
* Maintain event state.
* Read registration statistics.
* Support multi-turn interactions.
* Minimize unnecessary human interaction.
* Preserve human approval for actions that require authorization.

## 5.2 Secondary Goals

The system should also demonstrate:

* Agentic tool use.
* Persistent state.
* External API integration.
* Human-in-the-loop execution.
* Autonomous monitoring.
* Safe action boundaries.
* Deployment using Amazon Bedrock AgentCore.

---

# 6. Non-Goals

The MVP will **not** attempt to:

* Directly book university rooms through a real university database.
* Autonomously approve institutional requests.
* Build a Discord/Slack bot.
* Implement a complex multi-agent hierarchy.
* Generate PDF reports.
* Integrate with a real college event database.
* Replace faculty or institutional approval.

These capabilities can remain future roadmap items.

---

# 7. MVP Scope

The MVP consists of one Strands agent and a small collection of tools.

## MVP workflow

```text
Natural-language request
        ↓
Extract event information
        ↓
Check room availability
        ↓
Prepare permission request
        ↓
Create registration form
        ↓
Send announcement
        ↓
Read registration count
```

The complete MVP can therefore demonstrate an end-to-end operational workflow without requiring a large distributed architecture.

---

# 8. Example User Request

The primary demo scenario is:

> **"MACS wants to conduct a Python workshop for 80 students next Saturday."**

The agent extracts:

```json
{
  "organization": "MACS",
  "event_type": "workshop",
  "title": "Python Workshop",
  "expected_headcount": 80,
  "date": "next Saturday"
}
```

The exact date is resolved by the agent based on the current date/context.

---

# 9. System Architecture

## 9.1 High-Level Architecture

```text
                         ┌──────────────────────┐
                         │        User          │
                         │  Event Organizer     │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │   CampusOps Agent    │
                         │                      │
                         │  Strands Agents SDK  │
                         └──────────┬───────────┘
                                    │
                  ┌─────────────────┼──────────────────┐
                  │                 │                  │
                  ▼                 ▼                  ▼
          ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
          │ Room Tool    │  │ Forms Tool   │  │ Gmail Tools  │
          └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
                 │                 │                  │
                 ▼                 ▼                  ▼
          Google Sheets      Google Forms          Gmail
          (Mock Rooms)                              API
                                    │
                                    ▼
                              Response Sheet
                                    │
                                    ▼
                           Registration Tracking

                         ┌──────────────────────┐
                         │   AgentCore Memory   │
                         │   Event State        │
                         └──────────────────────┘

                         ┌──────────────────────┐
                         │  AgentCore Runtime   │
                         │  Deployed Agent      │
                         └──────────────────────┘
```

---

# 10. Architectural Philosophy

The MVP deliberately uses a **flat single-agent architecture**.

```text
User
  ↓
Strands Agent
  ├── check_room_availability
  ├── draft_permission_email
  ├── create_registration_form
  ├── send_announcement
  ├── get_registration_count
  ├── send_reminder
  └── generate_summary
```

The system does **not** initially use:

```text
CampusOps Agent
      │
 ┌────┼───────────────┐
 ↓    ↓               ↓
Event Communication Logistics
Agent      Agent       Agent
```

A multi-agent architecture can be introduced later, but it is intentionally excluded from the MVP to reduce coordination complexity and implementation risk.

---

# 11. Core Components

## 11.1 User Interface

The frontend provides a conversational interface where the organizer can:

* Describe an event.
* Ask for event status.
* Ask for registration statistics.
* Approve or reject pending actions.
* Request reminders.
* Ask for summaries.

Example:

```text
User:
MACS wants to conduct a Python workshop for 80 students next Saturday.

Agent:
I found LH-302 with a capacity of 100.

A faculty approval request has been prepared.

Would you like me to proceed with the registration setup?
```

---

# 12. Strands Agent

The Strands agent is the central reasoning component.

Its responsibilities are:

1. Understand user intent.
2. Extract structured information.
3. Determine the next required operation.
4. Select the appropriate tool.
5. Validate tool results.
6. Update event state.
7. Continue the workflow.
8. Stop when human input is required.
9. Resume after approval or additional information.

Conceptually:

```text
User Request
     ↓
Intent Understanding
     ↓
Event State
     ↓
Determine Next Action
     ↓
Tool Call
     ↓
Validate Result
     ↓
Update State
     ↓
Continue / Ask Human
```

---

# 13. Tool Layer

CampusOps exposes operational capabilities as tools to the Strands agent.

## 13.1 `check_room_availability`

### Purpose

Find a suitable room for the requested event.

### Inputs

```json
{
  "date": "YYYY-MM-DD",
  "capacity": 80
}
```

### Process

```text
Agent
  ↓
check_room_availability()
  ↓
Google Sheets
  ↓
Filter rooms by:
  - date
  - availability
  - capacity
  ↓
Return candidates
```

### Example output

```json
{
  "room": "LH-302",
  "capacity": 100,
  "available": true
}
```

### Implementation

The room database is represented by a seeded Google Sheet.

This is intentionally a mock because a real university room-booking API is not assumed to be publicly available.

The mock must be explicitly disclosed during the demonstration.

---

# 14. `draft_permission_email`

### Purpose

Prepare a permission request for the responsible faculty member or authority.

### Inputs

```json
{
  "organization": "MACS",
  "event_title": "Python Workshop",
  "date": "2026-08-29",
  "room": "LH-302",
  "expected_headcount": 80
}
```

### Output

A Gmail draft is created.

The agent does **not** automatically send an approval request when institutional authorization is required.

```text
Agent
  ↓
Generate permission request
  ↓
Create Gmail Draft
  ↓
Human reviews
  ↓
Human sends/approves
```

This is a deliberate safety boundary.

---

# 15. `create_registration_form`

### Purpose

Create a Google Form for event registration.

### Inputs

```json
{
  "title": "Python Workshop",
  "description": "Registration for the MACS Python Workshop",
  "event_date": "2026-08-29"
}
```

### Process

```text
Strands Agent
      ↓
Google Forms API
      ↓
Create Form
      ↓
Link response destination
      ↓
Google Sheets
      ↓
Return form URL
```

The registration form automatically stores responses in a linked Google Sheet.

---

# 16. `send_announcement`

### Purpose

Send the event announcement.

### Inputs

```json
{
  "event_title": "Python Workshop",
  "event_date": "2026-08-29",
  "room": "LH-302",
  "registration_link": "..."
}
```

### Process

```text
Agent
  ↓
Generate announcement
  ↓
Gmail API
  ↓
Send to configured organization mailing list
```

---

# 17. `get_registration_count`

### Purpose

Retrieve the current registration count.

### Example

```text
User:
How many people have registered?

Agent:
23 students have registered out of the expected 80.
```

### Process

```text
Agent
  ↓
get_registration_count()
  ↓
Google Sheets API
  ↓
Count responses
  ↓
Return current registration count
```

---

# 18. Stretch Tool — `send_reminder`

The reminder tool is implemented only after the MVP is stable.

It can:

1. Read registrant emails.
2. Determine that the event is approaching.
3. Generate a reminder.
4. Send the reminder.

Example:

```text
Registration:
23 / 80

Event:
Tomorrow

Agent:
Registration is currently below the expected attendance.

I prepared a reminder email.

Send it?
```

The human can approve the communication before it is sent.

---

# 19. Stretch Tool — `generate_summary`

After an event, the agent can read the registration/attendance data and generate a summary.

Example:

```text
# Python Workshop Summary

Expected attendees: 80
Registered: 63
Attendance: 57
Attendance rate: 90.5%

Event status: Completed
```

The MVP should use Markdown/text rather than introducing a dedicated PDF generation system.

---

# 20. Event Data Model

The central object in the system is an `Event`.

```text
Event {
    id
    org
    title
    date

    expected_headcount

    room
    room_capacity

    status

    form_id
    form_link
    sheet_id

    registrant_count

    announcement_sent
    reminder_sent
}
```

---

# 21. Event State Machine

The event follows a lifecycle.

```text
                    ┌───────────┐
                    │   DRAFT   │
                    └─────┬─────┘
                          │
                          ▼
                ┌──────────────────┐
                │ ROOM IDENTIFIED  │
                └────────┬─────────┘
                         │
                         ▼
              ┌───────────────────────┐
              │ PENDING APPROVAL      │
              └───────────┬───────────┘
                          │
                    Human Approval
                          │
                          ▼
                    ┌──────────┐
                    │  LIVE    │
                    └────┬─────┘
                         │
                         ▼
               ┌──────────────────┐
               │ EVENT APPROACHING│
               └────────┬─────────┘
                        │
                        ▼
                  ┌───────────┐
                  │  CLOSED   │
                  └───────────┘
```

The event status prevents the agent from treating every interaction as an independent task.

---

# 22. Human-in-the-Loop Design

Human approval is a fundamental part of the architecture.

The agent should not perform actions outside its authorization boundary.

## Example

```text
Agent
  ↓
Finds room
  ↓
Creates permission request
  ↓
────────────────────────────
 HUMAN APPROVAL REQUIRED
────────────────────────────
  ↓
Approved
  ↓
Continue workflow
```

This provides a clear boundary between:

### Autonomous actions

* Reading room data.
* Creating forms.
* Reading registrations.
* Preparing messages.
* Monitoring event state.

### Human-controlled actions

* Institutional approval.
* Authorization-sensitive decisions.
* Final approval of important communications where appropriate.

---

# 23. Agent State and Memory

CampusOps needs to retain information across multiple user interactions.

Example:

### Turn 1

```text
User:
Create the Python workshop.

Agent:
Event created.
Room: LH-302
Registration form: ...
```

### Turn 2

```text
User:
How many have registered?

Agent:
23 students have registered.
```

The second request should not require rebuilding the event from scratch.

The system therefore stores event state using **AgentCore Memory**.

The event ID can be used as the logical key for retrieving event state.

---

# 24. Persistent State

Conceptually:

```text
AgentCore Memory
       │
       ├── Event ID
       │
       ├── Event details
       ├── Room
       ├── Approval status
       ├── Form ID
       ├── Sheet ID
       ├── Registration count
       ├── Announcement status
       └── Reminder status
```

This allows the agent to resume an event workflow across multiple interactions.

---

# 25. Proactive Monitoring

A key extension of CampusOps is moving beyond request-response behavior.

Instead of requiring:

```text
User:
How many registered?
```

the system can periodically evaluate the event state.

Example:

```text
Expected attendees = 80
Current registrations = 23
Time until event = 2 days
```

The agent can reason:

```text
Registration rate is low
        ↓
Event is approaching
        ↓
A reminder may be useful
        ↓
Prepare reminder
        ↓
Ask human for approval
```

This demonstrates the core idea of an agent that works in the background and only interrupts the user when a meaningful decision is required.

---

# 26. Exception Handling

CampusOps should handle failures gracefully.

## 26.1 Tool Failure

If a Google API request fails:

```text
Tool call
   ↓
Failure
   ↓
Retry
   ↓
If still failing
   ↓
Inform user
```

## 26.2 Invalid Tool Arguments

The agent's tools should use strict schemas.

Example:

```text
create_registration_form(
    title: string,
    event_date: date,
    ...
)
```

Invalid arguments should be rejected before the external API is called.

---

# 27. Safety Boundaries

The agent should validate important operations before execution.

### Example

The agent should not:

* Invent a room.
* Assume approval was granted.
* Send an institutional approval request as if it were already authorized.
* Claim that a mocked room database is real.
* Report fabricated registration counts.
* Continue an event workflow when required information is missing.

---

# 28. External Integrations

| Integration                 | Status | Purpose                       |
| --------------------------- | ------ | ----------------------------- |
| Google Forms API            | Real   | Create registration forms     |
| Google Sheets API           | Real   | Store/read registrations      |
| Gmail API                   | Real   | Draft/send communications     |
| Room database               | Mocked | Demonstrate room availability |
| Discord/Slack               | Future | Additional communication      |
| PDF generation              | Future | Event reports                 |
| Real college event database | Future | Real room/event integration   |

The distinction between real and mocked integrations must be disclosed during the demonstration.

---

# 29. Google Sheets Room Database

The mock room database can contain:

| Room         | Capacity | Date     | Available |
| ------------ | -------: | -------- | --------- |
| LH-101       |       60 | Saturday | No        |
| LH-201       |       75 | Saturday | Yes       |
| LH-302       |      100 | Saturday | Yes       |
| Seminar Hall |      150 | Saturday | No        |

The room-selection tool filters this dataset.

Example:

```text
Requested capacity: 80

LH-101       → 60  ❌
LH-201       → 75  ❌
LH-302       → 100 ✅
Seminar Hall → 150 ❌
```

The agent therefore recommends:

```text
LH-302
Capacity: 100
```

---

# 30. End-to-End Workflow

## Step 1 — User Request

```text
MACS wants to conduct a Python workshop
for 80 students next Saturday.
```

---

## Step 2 — Intent Extraction

The agent extracts:

```text
Organization: MACS
Event: Python Workshop
Expected attendees: 80
Date: Next Saturday
```

---

## Step 3 — Room Search

The agent calls:

```text
check_room_availability()
```

The mock room sheet is queried.

Result:

```text
LH-302
Capacity: 100
Available: Yes
```

---

## Step 4 — Permission Request

The agent prepares a Gmail draft.

```text
To: Faculty Advisor

Subject:
Permission Request — MACS Python Workshop

...

Room:
LH-302

Expected attendance:
80
```

The request remains under human control.

---

## Step 5 — Registration Form

The agent calls:

```text
create_registration_form()
```

Google Forms creates:

```text
Python Workshop Registration
```

The response destination is linked to Google Sheets.

---

## Step 6 — Announcement

The agent generates an announcement and calls:

```text
send_announcement()
```

The event is now open for registration.

---

## Step 7 — Registration Tracking

Later:

```text
User:
How many people registered?
```

The agent calls:

```text
get_registration_count()
```

Result:

```text
23 registered
```

---

## Step 8 — Monitoring

The agent observes:

```text
Expected: 80
Registered: 23
Event: 2 days away
```

It determines that the registration count may require attention.

---

## Step 9 — Human Decision

```text
Agent:

Only 23 of the expected 80 students
have registered.

I prepared a reminder announcement.

Would you like me to send it?
```

The agent waits for the human decision.

---

# 31. API and Tool Interaction Model

The agent should not directly manipulate external services arbitrarily.

Instead:

```text
LLM
 │
 ▼
Structured Tool Call
 │
 ▼
Tool Validation
 │
 ▼
External API
 │
 ▼
Validated Result
 │
 ▼
Agent
```

This keeps the reasoning layer separate from external side effects.

---

# 32. Suggested Tool Interface

Conceptually:

```python
check_room_availability(
    date: str,
    capacity: int
)

draft_permission_email(
    organization: str,
    event_title: str,
    date: str,
    room: str,
    expected_headcount: int
)

create_registration_form(
    event_title: str,
    event_date: str,
    description: str
)

send_announcement(
    event_title: str,
    event_date: str,
    room: str,
    registration_link: str
)

get_registration_count(
    sheet_id: str
)

send_reminder(
    event_id: str
)

generate_summary(
    event_id: str
)
```

The final implementation should use strict schemas for each tool.

---

# 33. Prompt Architecture

The Strands agent should have a system prompt defining:

## Role

```text
You are CampusOps, an AI event operations agent.
Your purpose is to perform operational work required
to organize and monitor campus events.
```

## Responsibilities

```text
- Understand event requests.
- Maintain event state.
- Use available tools.
- Validate information.
- Continue workflows when safe.
- Ask for human approval when required.
```

## Restrictions

```text
- Never claim mocked data is real.
- Never fabricate tool results.
- Never assume institutional approval.
- Never bypass human authorization.
- Do not execute unnecessary actions.
```

---

# 34. Deployment Architecture

CampusOps is intended to be deployed using **Amazon Bedrock AgentCore**.

```text
                  Internet
                     │
                     ▼
             ┌───────────────┐
             │    Frontend   │
             └───────┬───────┘
                     │
                     ▼
             ┌───────────────┐
             │ AgentCore     │
             │ Runtime       │
             └───────┬───────┘
                     │
                     ▼
             ┌───────────────┐
             │ Strands Agent │
             └───────┬───────┘
                     │
       ┌─────────────┼─────────────┐
       ▼             ▼             ▼
   Gmail API    Forms API     Sheets API
                     │
                     ▼
              AgentCore Memory
```

---

# 35. Why AgentCore?

AgentCore provides two particularly useful capabilities for this project.

## AgentCore Runtime

Provides a deployed runtime for the agent instead of requiring the agent to run only inside a local notebook or development environment.

## AgentCore Memory

Provides persistent state that can support multi-turn event workflows.

This is particularly relevant because CampusOps is not a one-shot chatbot.

An event can span:

```text
Day 1:
Create event

Day 2:
Check registrations

Day 5:
Send reminder

Day 7:
Generate summary
```

The agent therefore needs to maintain event context over time.

---

# 36. Security Model

CampusOps interacts with external services through authenticated APIs.

OAuth credentials should be handled securely.

The application should:

* Request only required scopes.
* Avoid hardcoding credentials.
* Store secrets outside source code.
* Validate tool inputs.
* Limit external side effects.
* Require human approval for sensitive actions.
* Avoid exposing OAuth tokens to the LLM.

---

# 37. Failure and Recovery Strategy

## OAuth/API Setup Failure

Test each API independently before integrating it with Strands.

```text
Google Forms
     ↓
Standalone test
     ↓
Pass
     ↓
Integrate with agent
```

Repeat for:

* Gmail
* Sheets
* AgentCore

---

## Live API Failure

Maintain:

```text
Primary:
Live API

Fallback:
Cached/mock response
```

A recorded backup run can also be maintained for the final demonstration.

---

## Malformed Tool Call

```text
LLM
 ↓
Invalid arguments
 ↓
Schema validation
 ↓
Reject
 ↓
Retry / correct
```

---

# 38. Observability

The system should log important agent operations.

Example:

```text
[10:30:12] User request received
[10:30:13] Event details extracted
[10:30:13] check_room_availability()
[10:30:14] Room LH-302 selected
[10:30:15] draft_permission_email()
[10:30:17] create_registration_form()
[10:30:19] Form created
[10:30:20] send_announcement()
```

This makes the agent's actions visible during development and useful during the hackathon demo.

---

# 39. Testing Strategy

## Unit Tests

Test individual tools independently.

```text
check_room_availability()
create_registration_form()
get_registration_count()
```

## Integration Tests

Test:

```text
Strands Agent
      ↓
Tool
      ↓
Google API
      ↓
Result
```

## Agent Tests

Test natural-language inputs:

```text
"Create a Python workshop for 80 people."

"Organize a coding competition for 150 students."

"How many students registered?"
```

## Failure Tests

Test:

* Missing date.
* Missing expected capacity.
* No suitable room.
* API failure.
* Invalid form data.
* Unauthorized action.
* Empty registration sheet.

---

# 40. Example Failure Scenarios

## No Room Available

```text
User:
Organize an event for 300 people.

Agent:
I couldn't find an available room with capacity
for 300 people.

Would you like me to search for alternative dates?
```

---

## Missing Information

```text
User:
Create a workshop.

Agent:
I can do that. What date should the workshop
be scheduled for, and approximately how many
students do you expect?
```

---

## Approval Required

```text
Agent:
I found a suitable room and prepared the
permission request.

The room still requires faculty approval.

Approve the request?
```

---

# 41. Data Flow

```text
User
 │
 │ Natural language
 ▼
Strands Agent
 │
 │ Structured event information
 ▼
Event State
 │
 ├─────────────┐
 │             │
 ▼             ▼
Room Tool    Communication Tools
 │             │
 ▼             ├── Gmail
Sheets         └── Forms
 │
 └─────────────┐
               ▼
          Event State
               │
               ▼
        AgentCore Memory
```

---

# 42. Current Build vs Future Roadmap

## Current MVP

```text
✓ Natural-language event request
✓ Event information extraction
✓ Room availability lookup
✓ Mock room database
✓ Permission email draft
✓ Google Form creation
✓ Google Sheets registration tracking
✓ Announcement email
✓ Registration count
✓ Human approval boundary
```

## Stretch

```text
→ Automated reminders
→ Event summary
→ Proactive registration monitoring
→ Persistent memory
```

## Future

```text
→ Multi-agent architecture
→ Slack integration
→ Discord integration
→ PDF reports
→ Real university event database
→ Real room booking integration
→ Calendar integration
→ Advanced analytics
→ Automated post-event workflows
```

---

# 43. Future Multi-Agent Architecture

The future architecture can use Strands' agent-as-tool pattern.

```text
                    CampusOps
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
      Event Agent  Communication  Logistics
                       Agent        Agent
          │            │            │
          ▼            ▼            ▼
       Forms        Gmail/Slack    Rooms
       Events       Announcements  Scheduling
```

This architecture is intentionally **not part of the MVP**.

It should be presented as an extension path rather than claimed as an implemented feature.

---

# 44. Why a Single Agent Is Better for the MVP

A single agent provides:

* Lower implementation complexity.
* Easier debugging.
* Fewer coordination failures.
* Faster development.
* Clearer tool execution.
* A simpler hackathon demonstration.

The architecture can later evolve into multiple specialized agents if the system grows.

---

# 45. Demonstration Plan

The entire live demonstration should follow one golden path.

## Step 1

Enter:

```text
MACS wants to conduct a Python workshop
for 80 students next Saturday.
```

## Step 2

Show the agent extracting:

```text
Organization: MACS
Event: Python Workshop
Expected: 80
Date: Saturday
```

## Step 3

Agent checks the room.

```text
LH-302
Capacity: 100
Available
```

Explain:

> "This is a mock registrar sheet standing in for a real room-booking API."

---

## Step 4

Agent creates the permission request.

Explain:

> "The agent prepares the request, but a human advisor still approves it."

---

## Step 5

Agent creates the Google Form.

Show the actual form.

---

## Step 6

Agent sends the announcement.

Show the Gmail result.

---

## Step 7

Ask:

```text
How many people have registered?
```

Agent reads the linked Sheet.

Example:

```text
23 registered.
```

---

## Step 8 — Optional

Demonstrate proactive monitoring:

```text
23 / 80 registered
Event tomorrow
```

Agent says:

```text
Registration is lower than expected.

I've prepared a reminder.

Would you like me to send it?
```

---

# 46. Demo Architecture Visualization

The presentation should clearly distinguish:

```text
             CURRENT BUILD
                  │
                  ▼
        ┌──────────────────┐
        │  Strands Agent   │
        └────────┬─────────┘
                 │
     ┌───────────┼────────────┐
     ▼           ▼            ▼
   Rooms       Forms        Gmail
   Mocked       Real         Real
                 │
                 ▼
              Sheets
               Real
```

And separately:

```text
             FUTURE
                │
                ▼
          Multi-Agent
             System
                │
       ┌────────┼────────┐
       ▼        ▼        ▼
     Event   Comms    Logistics
```

This prevents the architecture from appearing to claim features that are not actually implemented.

---

# 47. Development Plan

## Phase 1 — Infrastructure

* Configure AWS/AgentCore.
* Configure Strands project.
* Configure Google OAuth.
* Configure Gmail API.
* Configure Google Forms API.
* Configure Google Sheets API.

---

## Phase 2 — Tools

Implement and independently test:

```text
check_room_availability
create_registration_form
get_registration_count
draft_permission_email
send_announcement
```

---

## Phase 3 — Agent

Connect the tools to the Strands agent.

Test:

```text
User request
    ↓
Reasoning
    ↓
Tool selection
    ↓
Tool execution
    ↓
Next tool
```

---

## Phase 4 — State

Implement:

```text
Event
Event status
Form ID
Sheet ID
Room
Registration count
Approval status
```

Persist the state using AgentCore Memory.

---

## Phase 5 — Proactive Behavior

Add:

```text
Registration monitoring
       ↓
Threshold evaluation
       ↓
Reminder preparation
       ↓
Human approval
```

---

## Phase 6 — Stretch Features

Only after the MVP works reliably:

```text
send_reminder()
generate_summary()
```

Do not begin stretch features before the core workflow works reliably.

---

# 48. Risk Management

| Risk                             | Mitigation                                    |
| -------------------------------- | --------------------------------------------- |
| OAuth setup takes too long       | Test APIs independently first                 |
| LLM makes malformed tool call    | Strict schemas + validation                   |
| Google API fails during demo     | Cached/mock fallback                          |
| Scope creep                      | Freeze MVP before stretch work                |
| Agent claims mocked data is real | Explicit system instruction + demo disclosure |
| Agent bypasses approval          | Human-in-the-loop state transition            |
| Lost event state                 | Persistent event memory                       |
| No suitable room                 | Ask user for alternative date/capacity        |
| Duplicate action                 | Track action status in event state            |

---

# 49. MVP Success Criteria

The MVP is successful if the agent can complete the following workflow:

```text
Natural-language request
        ↓
Extract event details
        ↓
Find room
        ↓
Prepare permission request
        ↓
Create registration form
        ↓
Send announcement
        ↓
Read registration count
```

The system must also:

* Maintain event state.
* Clearly distinguish real and mocked integrations.
* Preserve human approval boundaries.
* Recover gracefully from tool failures.
* Demonstrate actual external actions rather than only generating text.

---

# 50. Key Differentiator

CampusOps is not designed to be another chatbot that tells organizers what they should do.

Its differentiator is:

> **CampusOps converts a natural-language goal into a sequence of real-world operations and maintains the event workflow after the initial request.**

The progression is:

```text
Chatbot
   ↓
Tool-using Assistant
   ↓
Task Automation
   ↓
Agent
```

CampusOps aims for the final stage.

---

# 51. One-Line Pitch

> **CampusOps is an AI event operations agent that turns a simple event request into real operational actions—room discovery, registration, communication, and monitoring—while keeping humans in control of decisions that require approval.**

---

# 52. Final Architecture

```text
                              ┌───────────────────┐
                              │       USER        │
                              │ Event Organizer   │
                              └─────────┬─────────┘
                                        │
                                        ▼
                              ┌───────────────────┐
                              │  CampusOps Agent  │
                              │                   │
                              │ Strands Agents    │
                              │ SDK               │
                              └─────────┬─────────┘
                                        │
                   ┌────────────────────┼────────────────────┐
                   │                    │                    │
                   ▼                    ▼                    ▼
          ┌────────────────┐   ┌────────────────┐   ┌────────────────┐
          │ Room Tool      │   │ Registration   │   │ Communication  │
          │                │   │ Tools          │   │ Tools          │
          └───────┬────────┘   └───────┬────────┘   └───────┬────────┘
                  │                    │                    │
                  ▼                    ▼                    ▼
          ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
          │ Google       │      │ Google Forms │      │ Gmail API    │
          │ Sheets       │      │ API          │      │              │
          │ Mock Rooms   │      └──────┬───────┘      └──────────────┘
          └──────────────┘             │
                                       ▼
                                ┌──────────────┐
                                │ Google       │
                                │ Sheets       │
                                │ Registrants  │
                                └──────┬───────┘
                                       │
                                       ▼
                              ┌──────────────────┐
                              │ Event State      │
                              │                  │
                              │ draft            │
                              │ pending_approval │
                              │ live             │
                              │ closed           │
                              └────────┬─────────┘
                                       │
                         ┌─────────────┴──────────────┐
                         ▼                            ▼
                ┌──────────────────┐        ┌──────────────────┐
                │ AgentCore        │        │ Human Approval   │
                │ Memory           │        │ Boundary         │
                └──────────────────┘        └──────────────────┘
                         │
                         ▼
                ┌──────────────────┐
                │ AgentCore        │
                │ Runtime          │
                └──────────────────┘
```

---

# 53. Design Philosophy

CampusOps follows five principles:

### 1. **Action over explanation**

The agent should perform useful work rather than merely describe it.

### 2. **Human control**

The agent should never silently cross authorization boundaries.

### 3. **Persistent state**

Events are long-running workflows, not isolated conversations.

### 4. **Honest architecture**

Real integrations, mocked integrations, and future capabilities must be clearly separated.

### 5. **Useful autonomy**

The agent should work independently when possible and interrupt the organizer only when human judgment is actually needed.

---

# 54. Conclusion

CampusOps transforms campus event management from a collection of repetitive administrative tasks into an agent-driven operational workflow.

The MVP deliberately focuses on a small but complete loop:

```text
REQUEST
   ↓
REASON
   ↓
FIND
   ↓
PREPARE
   ↓
CREATE
   ↓
COMMUNICATE
   ↓
MONITOR
   ↓
ASK HUMAN WHEN NEEDED
```

Rather than attempting to build an enormous multi-agent platform, the system prioritizes a reliable, demonstrable core.

The long-term vision is a campus operations agent capable of managing increasingly complex event workflows while preserving human oversight over decisions that require authorization.

**CampusOps doesn't just tell organizers what to do. It does the operational work for them.**