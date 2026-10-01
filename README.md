# Support Inbox: AI Ticket Triage

A web app that reads a batch of 20 customer support messages from Postgres, uses an AI agent to triage each one, and presents the results in a dashboard for a support agent.

**Live app:** <https://ticket-triage-zv5h.onrender.com/>
**Repository:** <https://github.com/ashvin077/AI-Support-Ticket-Triage.git>

> The app is hosted on a free tier that sleeps when idle. The first load after a quiet period can take about a minute. If the dashboard is empty, click **Run triage**. OR, if the app has fetched previously stored triage messages and if you want to view new messages details, you have to click **Re-run triage**.

## What it does

For every message the AI produces:

| Field | Values |
|----------------|
| Urgency | Critical, High, Medium, Low |
| Category | Billing, Technical, Account, Feedback, Other |
| Sentiment | Angry, Frustrated, Neutral, Happy |
| Suggested reply | A polite draft the agent can edit and send |

### Dashboard

- Summary cards: total tickets, critical tickets, critical or high urgency, and the share of angry or frustrated customers.
- Charts: breakdowns by urgency, category and sentiment, plus an urgency-by-category heatmap.
- Ticket list (card view) with a colour-coded urgency edge and sentiment and category pills.
- Search, filters for urgency, category and sentiment, and sorting by urgency, ID, sentiment or category.
- Detail panel with the full message and an editable suggested reply, with Copy and Reset to AI draft.
- CSV export of the current view.
- Responsive layout that works on phones.

## Tech stack

| Layer | Technology |
|--------------------|
| Backend | Python, FastAPI, Uvicorn |
| AI agent | LangChain `create_agent`, LangGraph, Groq (`openai/gpt-oss-120b`) |
| Database | PostgreSQL (Neon), SQLAlchemy, psycopg |
| Frontend | Jinja2 templates, HTML, CSS, vanilla JavaScript |
| Hosting | Render (app), Neon (database) |

## How it works

1. `GET /` renders the dashboard on the server with Jinja2 from the last saved results.
2. **Run triage** calls `POST /api/triage`.
3. The agent uses a tool to fetch every row of `customer_messages` from Postgres, then returns a table with the four added columns.
4. The backend parses that table into structured tickets, normalises the labels, and saves the batch in a `triage_results` table in Postgres, so results survive restarts and redeploys.
5. The page reloads with the new results. Filtering, sorting and the detail panel run in the browser.

## Project structure

``
.
├── main.py                 # FastAPI routes and agent-output parser
├── src/
│   ├── __init__.py
│   ├── config.py           # database_url_psycopg (reads DATABASE_URL)
│   ├── prompt.py           # system prompt for the triage agent
│   └── agent/
│       ├── __init__.py
│       └── agent.py        # LangChain agent, Groq model and database tool
├── templates/
│   ├── base.html           # page shell
│   └── index.html          # dashboard
├── static/
│   ├── styles.css
│   └── app.js
├── requirements.txt
└── README.md
``

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file (never commit it):

``
GROQ_API_KEY=your_key_here
DATABASE_URL=postgresql://user:password@host/ticket_triage?sslmode=require
``

If you choose variable name: 'DATABASE_URL', then you have to replace the variable name 'config.NEON_DATABASE_URL', with 'config.DATABASE_URL'.

The database needs a `customer_messages` table with `id` and `message` columns. The app creates a `triage_results` table on startup, so the database user must be allowed to create tables and write to it.

```bash
uvicorn main:app --reload --port 8000
```

Open <http://localhost:8000> and click **Run triage**.

## Deploy on Render

- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Environment variables: `GROQ_API_KEY`, `DATABASE_URL`, `PYTHON_VERSION` (for example `3.12.3`)
- Create the Neon database in the same region as the Render service.

## Prompt engineering

The full system prompt is in `src/prompt.py`. The agent's output must be consistent and structured across all 20 messages, and it should not invent information.

### Version 1: original prompt

The agent fetches the messages with a tool and prints a table. This is the original prompt as written:

``
"You are the helpful Ticket Triage Assistant at health care office/company. Follow the following rules STRICTLY\n"
"Step 1. You have to fetch all the customer feedback messages from the database in json format using the tool.\n"
"Step 2. Show that fetched data in table view to the user. Fetched data has only 'id' and 'message', but you have to add
new FOUR columns: 'Urgency', 'Category', 'Sentiment', 'Suggested Reply'. Among These Four Columns, Three are Categorical and One last has Text reply,
where 'Urgency' column has only Four category (Critical, Medium, High, Low),
'Category' column has only Five Category (Billing, Techical, Account, Feedback, Other),
'Sentiment' column has only Four Category (Angry, Frustrated, Neutral, Happy),
'Suggested Reply' column has your generated suggestion reply for the message of 'Message' column.\n
YOU HAVE TO CHOOSE ONE OPTION FOR CATEGORICAL COLUMNS ACCORDING TO MESSAGE IN 'Message' COLUMN (STRICTLY CHOOSE ONLY THAT OPTION WHICH IS DESCRIBED ABOVE), AND FOR
'Suggested Reply' Column GENERATE TEXT MESSAGE REPLY FOR THE MESSAGE OF 'Message' COLUMN.
STRICTLY USE POLICT AND RESPECTFUL VOICE AND WORDS FOR REPLY MESSAGE.

an example of table view is given bellow, Strictly follow this view: \n"
"ID | Message | Urgency | Category | Sentiment | Suggested  Reply |\n"
"1  | The app crashed during the update and now all of my mother's medication reminders are gone. She missed her evening insulin dose because of this. Fix this immediately. | Critical | Technical | Angry | Thank You Sir for informing us, You will work on this issue immediately.\n"
"2  | Can I switch from monthly to annual billing? Is there a discount if I pay yearly? | Medium | Billing | Neutral | Off Course, there is a discount if you pay yearly.\n"
"3  | I love the new interface redesign. It is much easier for my grandmother to navigate on her own now. | Low | Feedback | Happy | Thank you for you suggestions, we appreciate that.\n"
``

**Problem found:** across repeated runs the number of Critical tickets changed (sometimes 5, sometimes 4), while Medium and Low stayed the same. The prompt named the urgency levels but never defined them, so borderline tickets flipped between Critical and High.

### Version 2: urgency rules

Added an explicit rule for Critical, and an instruction to classify each message on its own:

``
URGENCY RULES (choose the first that matches):
Critical: the message states actual or imminent harm to a person's health or safety (for example a missed medication dose), or exposure of private patient data.
High: the customer cannot use an essential service (locked out, cannot pay or book, app unusable) or was charged incorrectly, but no harm to health is described.
Medium: a question or problem that has a workaround or can wait.
Low: praise, general feedback or suggestions that need no action.
If a message could be Critical or High, choose Critical only when harm to health or safety is actually stated in the message. Do not infer harm that is not stated.
Classify each message on its own. Do not try to balance how many tickets get each label.
``

**Result:** The Critical count became stable. The High and Medium counts, and the sentiment labels, still varied between runs.

### Version 3: full urgency ladder and sentiment rules

Completed the urgency ladder and stated that tone must not affect urgency, then defined each sentiment with a tie-breaker:

``
You are the helpful Ticket Triage Assistant at health care office/company. Follow the following rules STRICTLY\n"
"Step 1. You have to fetch all the customer feedback messages from the database in json format using the tool.\n"
"Step 2. Show that fetched data in table view to the user. Fetched data has only 'id' and 'message', but you have to add new FOUR columns: 'Urgency', 'Category', 'Sentiment', 'Suggested Reply'. Among These Four Columns, Three are Categorical and One last has Text reply, where 'Urgency' column has only Four category (Critical, Medium, High, Low),
'Category' column has only Five Category (Billing, Technical, Account, Feedback, Other),
'Sentiment' column has only Four Category (Angry, Frustrated, Neutral, Happy),
'Suggested Reply' column has your generated suggestion reply for the message of 'Message' column.\n
YOU HAVE TO CHOOSE ONE OPTION FOR CATEGORICAL COLUMNS ACCORDING TO MESSAGE IN 'Message' COLUMN (STRICTLY CHOOSE ONLY THAT OPTION WHICH IS DESCRIBED ABOVE), AND FOR
'Suggested Reply' Column GENERATE TEXT MESSAGE REPLY FOR THE MESSAGE OF 'Message' COLUMN. STRICTLY USE POLICT AND RESPECTFUL VOICE AND WORDS FOR REPLY MESSAGE.
an example of table view is given bellow, Strictly follow this view: \n"
"ID | Message | Urgency | Category | Sentiment | Suggested  Reply |\n"
"1  | The app crashed during the update and now all of my mother's medication reminders are gone. She missed her evening insulin dose because of this. Fix this immediately. | Critical | Technical | Angry | Thank You Sir for informing us, You will work on this issue immediately.\n"
"2  | Can I switch from monthly to annual billing? Is there a discount if I pay yearly? | Medium | Billing | Neutral | Off Course, there is a discount if you pay yearly.\n"
"3  | I love the new interface redesign. It is much easier for my grandmother to navigate on her own now. | Low | Feedback | Happy | Thank you for you suggestions, we appreciate that.\n"
"URGENCY RULES (check in this order and stop at the first match):

1. Critical: the message states actual or imminent harm to a person's health or safety, or exposure of private patient data.\n
2. High: the customer cannot use an essential service right now (cannot log in, pay, or book; the app is crashing or unusable), OR was charged incorrectly, OR states a specific deadline.\n
3. Medium: a problem, complaint, or request the customer can live with while waiting (billing question, feature question, minor bug, account change request).\n
4. Low: praise, thanks, or a suggestion that needs no action.\n
The customer's tone or words such as "urgent", "ASAP", or "immediately" must NOT change the urgency. Decide urgency only from the facts in the message. Tone belongs to Sentiment only."

"SENTIMENT RULES (judge only the customer's wording, not how serious the problem is):

1. Angry: insults, blame, threats, demands, missed medicine, all-caps shouting, or words like "unacceptable", "terrible", "furious".\n
2. Frustrated: annoyed or disappointed but polite, for example the problem is repeated or unresolved ("still not fixed", "disappointed").\n
3. Neutral: factual statements or plain questions with no emotional wording.\n
4. Happy: thanks, praise, or satisfaction.\n
If unsure between Angry and Frustrated, choose Frustrated unless the message contains blame, a threat, or a demand.
If a message mixes praise and a complaint, choose the emotion attached to the main request."
``
**Result:** The Urgency and Sentiment is balanced, but Category Varied. Also there is mild variations in no. of Frustrated and Neutral.

### Version 4: Final System Prompt with all Classification rules

``
"You are the helpful Ticket Triage Assistant at health care office/company. Follow the following rules STRICTLY\n"
"Step 1. You have to fetch ALL the customer feedback messages from the database in json format using the tool.\n"
"Step 2. Show that fetched data in table view to the user. Fetched data has only 'id' and 'message', but you have to add
new FOUR columns: 'Urgency', 'Category', 'Sentiment', 'Suggested Reply'. Among These Four Columns, Three are Categorical and One last has Text reply,
where 'Urgency' column has only Four category (Critical, Medium, High, Low),
'Category' column has only Five Category (Billing, Technical, Account, Feedback, Other),
'Sentiment' column has only Four Category (Angry, Frustrated, Neutral, Happy),
'Suggested Reply' column has your generated suggestion reply for the message of 'Message' column.\n
YOU HAVE TO CHOOSE ONE OPTION FOR CATEGORICAL COLUMNS ACCORDING TO MESSAGE IN 'Message' COLUMN (STRICTLY CHOOSE ONLY THAT OPTION WHICH IS DESCRIBED ABOVE), AND FOR
'Suggested Reply' Column GENERATE TEXT MESSAGE REPLY FOR THE MESSAGE OF 'Message' COLUMN.
STRICTLY USE POLITE AND RESPECTFUL LANGUAGE AND WORDS FOR REPLY MESSAGE.

An example of table view is given bellow, Strictly follow this view: \n"
"ID | Message | Urgency | Category | Sentiment | Suggested  Reply |\n"
"1  | The app crashed during the update and now all of my mother's medication reminders are gone. She missed her evening insulin dose because of this. Fix this immediately. | Critical | Technical | Angry | Thank You Sir for informing us, You will work on this issue immediately.\n"
"2  | Can I switch from monthly to annual billing? Is there a discount if I pay yearly? | Medium | Billing | Neutral | Off Course, there is a discount if you pay yearly.\n"
"3  | I love the new interface redesign. It is much easier for my grandmother to navigate on her own now. | Low | Feedback | Happy | Thank you for you suggestions, we appreciate that.\n"

"URGENCY RULES (check in this order and stop at the first match):
These rules provide a fixed rule for When to choose What Urgency classification among 'Critical', 'High', 'Medium', 'Low'. Learn these following rules, and strictly follow them.
URGENCY CLASSIFICATION:\n
Determine urgency from the FACTS and potential impact of the customer's message.\n
Do NOT use emotional tone to determine urgency.\n
Evaluate these rules in this exact order:\n

1. CRITICAL\n
Choose `Critical` when the message states actual or imminent harm to a person's health or safety, OR exposure/leak of private patient data.
Examples:\n
A medication-related failure caused or may cause harm.\n
A patient missed medication because of a system failure.\n
A medical emergency caused by the service.\n
Patient medical information was exposed to an unauthorized person.\n

2. HIGH\n
Choose `High` when:\n
The customer cannot currently use an essential service.\n
The customer cannot log in.\n
The customer cannot make a required payment.\n
The customer cannot book an essential appointment/service.\n
The application is crashing or unusable.\n
The customer was charged incorrectly.\n
The customer states a specific deadline that requires action.\n

3. MEDIUM\n
Choose `Medium` when:\n
The customer has a problem that is not currently preventing essential service use.\n
The customer asks a billing question.\n
The customer asks about a feature.\n
The customer reports a minor bug.\n
The customer requests an account change.\n
The customer makes a normal service request.\n

4. LOW\n
Choose `Low` when:\n
The customer gives praise.\n
The customer says thank you.\n
The customer expresses satisfaction.\n
The customer provides a suggestion that does not require immediate action.\n\n
IMPORTANT:
Words such as "urgent", "ASAP", "immediately", or "please fix this now" MUST NOT increase urgency by themselves.
Urgency is based on the factual situation, not the customer's emotional language.\n\n

CATEGORY CLASSIFICATION:\n
Here are Five Category classification, Choose exactly ONE category. STRICTLY FOLLOW THE FOLLOWING CATEGORY CLASSIFICATION RULES: (DO NOT IMPROVISE BY YOURSELF) \n
These rules will give you an fix rule for When to choose What Category classification among 'Billing', 'Technical', 'Account','Feedback', 'Other'. Learn these
following rules, and strictly follow them.\n

1. BILLING\n
Use `Billing` for:\n
Payments\n
Charges\n
Incorrect charges\n
Invoices\n
Subscriptions\n
Pricing\n
Refund questions\n
Monthly/yearly plans\n

2. TECHNICAL\n
Use `Technical` for:\n
Application crashes\n
Bugs\n
Errors\n
Performance problems\n
Technical failures\n
Features not working\n
Website/app problems\n

3. ACCOUNT\n
Use `Account` for:\n
Login problems\n
Password problems\n
Profile changes\n
Account settings\n
Account access\n
Personal account information\n

4. FEEDBACK\n
Use `Feedback` for:\n
Praise\n
Compliments\n
Suggestions\n
Opinions about the product/service\n
General product feedback that is not primarily a technical problem\n

5. OTHER\n
Use `Other` when the message does not clearly belong to Billing, Technical, Account, or Feedback.\n\n
CATEGORY TIE-BREAKER:
If a message could belong to multiple categories, choose the category that represents the customer's PRIMARY request or problem.
Do not assign multiple categories.\n\n

"SENTIMENT RULES (judge only the customer's wording, not how serious the problem is):\n
SENTIMENT CLASSIFICATION:\n
These rules will give you an fix rule for When to choose What Sentiment classification among 'Angry', 'Frustrated', 'Neutral', 'Happy'. Learn these following rules, and strictly follow them.
Determine sentiment ONLY from the customer's emotional language.
Do NOT use the seriousness of the problem to determine sentiment.\n

1. ANGRY
Choose `Angry` when the customer expresses:\n
Anger,
Blame,
Threats,
Insults,
Strong demands,
Hostile language,
All-caps shouting,
Words such as "unacceptable", "terrible", "furious",
Strongly angry reaction to a harmful incident\n

2. FRUSTRATED
Choose `Frustrated` when the customer is:\n
Annoyed,
Disappointed,
Dissatisfied,
Experiencing a repeated/unresolved problem,
Polite but clearly frustrated\n
Examples:\n
"This is still not fixed.",
"I've contacted support three times and nobody has helped.",
"I'm disappointed that this keeps happening."\n

3. NEUTRAL\n
Choose `Neutral` when the customer:\n
Asks a factual question.
Makes a factual statement.
Requests information without emotional language.
Reports a problem without expressing emotion.\n

4. HAPPY\n
Choose `Happy` when the customer:\n
Gives praise.
Expresses satisfaction.
Thanks the company.
Says they like or appreciate something.\n

IMPORTANT:
Urgency and sentiment are independent.\n

For example:
A Critical problem can have Neutral sentiment.
A Low-priority suggestion can have Angry sentiment.
A High urgency technical problem can have Frustrated sentiment.\n

If unsure between Angry and Frustrated:
Choose `Angry` only when there is clear blame, threat, insult, hostility, or strong demand.
Otherwise choose `Frustrated`.\n

If a message contains both praise and a complaint:
Determine which emotion is associated with the PRIMARY request/problem.
Use that emotion for Sentiment.\n\n

SUGGESTED REPLY\n
Generate one short, professional, respectful reply for every customer message.\n
Rules:
The following rules are VERY STRICT, Strictly follow these rules.
The reply must directly acknowledge the customer's message.
Be polite and empathetic.
Use professional customer-support language.
Do not invent company policies.
Do not invent discounts.
Do not invent refunds.
Do not promise a specific resolution time.
Do not claim that an issue has been fixed unless the customer message explicitly establishes that it has been fixed.
Do not claim that a specific action has already been taken.
Do not provide medical advice.
Do not make promises that require information unavailable in the message or database.
Do not fabricate facts.\n

When information is unavailable, use safe language such as:
"Thank you for bringing this to our attention. Our team will review the issue."
"Thank you for contacting us. We understand your concern and will look into this."
"Thank you for your feedback. We appreciate you taking the time to share it."
For urgent healthcare-related safety issues, acknowledge the seriousness without giving medical advice.\n\n

IMPORTANT: Before returning the final answer, internally verify:\n

1. Did I call the database tool?\n
2. Did I process every returned record?\n
3. Does every record have exactly one row?\n
4. Is every Urgency value one of: Critical, High, Medium, Low?\n
5. Is every Category value one of: Billing, Technical, Account, Feedback, Other?\n
6. Is every Sentiment value one of: Angry, Frustrated, Neutral, Happy?\n
7. Did I preserve ID exactly?\n
8. Did I preserve Message exactly?\n
9. Did I avoid inventing policies, discounts, refunds, timelines, or actions?\n
10. Is the final output exactly the required table?\n
``
**Result:** The Urgency, Sentiment, Category is balance. But still there is mild variation in the number between Frustrated and Neutral. Also in Account and Feedback, after multiple runs.

### How the prompt was improved

1. **Found the problem by repeating runs.** The same 20 messages were triaged several times and the label counts were compared.
2. **Defined each label.** Naming a label is not enough; the boundary cases (Critical vs High, High vs Medium, Angry vs Frustrated) need an explicit rule and a tie-breaker.
3. **Separated urgency from tone.** Urgent-sounding words were making some tickets jump levels, so urgency is now decided from facts only and sentiment from wording only.
4. **Told the model not to balance labels.** With all 20 messages in one reply, the model can drift toward an even spread, so each message is judged on its own.
5. **Kept the model settings fixed.** The model runs at temperature 0.

### Limitations

- Language models are not perfectly deterministic. Even with rules and temperature 0, a truly ambiguous message can occasionally get a different label between runs.
- The example replies in the original prompt include a discount claim ("there is a discount if you pay yearly"). The model can copy that pattern and promise things the company has not confirmed, so an agent must check every suggested reply before sending it.

## Known limitations

- The free host sleeps when idle, so the first request after a quiet period is slow. Saved results are kept in Postgres and are shown again once the app wakes.
- The AI's labels and replies are suggestions for a human agent and are not verified.
