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

If you choose variable name: 'DATABASE_URL', then you have to replace the variable name from 'config.NEON_DATABASE_URL' TO 'config.DATABASE_URL'.

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

**Result:** the Critical count became stable. The High and Medium counts, and the sentiment labels, still varied between runs.

### Version 3: full urgency ladder and sentiment rules

Completed the urgency ladder and stated that tone must not affect urgency, then defined each sentiment with a tie-breaker:

``
URGENCY RULES (check in this order and stop at the first match):

1. Critical: the message states actual or imminent harm to a person's health or safety, or exposure of private patient data.
2. High: the customer cannot use an essential service right now (cannot log in, pay, or book; the app is crashing or unusable), OR was charged incorrectly, OR states a specific deadline.
3. Medium: a problem, complaint, or request the customer can live with while waiting (billing question, feature question, minor bug, account change request).
4. Low: praise, thanks, or a suggestion that needs no action.
The customer's tone or words such as "urgent", "ASAP", or "immediately" must NOT change the urgency. Decide urgency only from the facts in the message. Tone belongs to Sentiment only.

SENTIMENT RULES (judge only the customer's wording, not how serious the problem is):
Angry: insults, blame, threats, demands, all-caps shouting, or words like "unacceptable", "terrible", "furious".
Frustrated: annoyed or disappointed but polite, for example the problem is repeated or unresolved ("still not fixed", "disappointed").
Neutral: factual statements or plain questions with no emotional wording.
Happy: thanks, praise, or satisfaction.
If unsure between Angry and Frustrated, choose Frustrated unless the message contains blame, a threat, or a demand.
If a message mixes praise and a complaint, choose the emotion attached to the main request.
``

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
