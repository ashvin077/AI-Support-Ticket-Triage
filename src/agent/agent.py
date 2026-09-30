import os
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langchain_groq import ChatGroq
from src import config
from sqlalchemy import create_engine, text
import json

load_dotenv()

llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0)
engine = create_engine(config.NEON_DATABASE_URL)


@tool
def get_customers_messages():
    """
        Search in the customer_messages table of ticket_triage database, and fetch all the data in that table with their 'id'
        and 'message'. 
    Returns: a json array of 'id' and 'message'.
    """
    sql_query = """SELECT * FROM customer_messages"""
    
    sql_query = text(sql_query)
    
    with engine.connect() as conn:
        result = conn.execute(sql_query)
        result = result.mappings().all()
    
    messages = [dict(row) for row in result]
    return json.dumps(messages)



agent = create_agent(
    llm,
    tools=[get_customers_messages],
    system_prompt=(
        """
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
        
    """),
    checkpointer=InMemorySaver()
)


if __name__ == "__main__":
    config = {"configurable": {"thread_id": "user-alice-session-1"}}
    result = agent.invoke({
       "messages": [{
           "role": "user",
           "content": ("Show the customer messages details to me")
       }]
    }, config)
    print(result["messages"][-1].content)
