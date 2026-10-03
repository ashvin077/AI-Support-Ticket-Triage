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
from src.prompt import system_prompt

load_dotenv()

llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0, model_kwargs={"seed": 42}, reasoning_effort="medium")
engine = create_engine(config.NEON_DATABASE_URL)


@tool
def get_customers_messages():
    """
        Search in the customer_messages table of ticket_triage database, and fetch all the records (that is '20') in that table with their 'id'
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
    system_prompt=(system_prompt),
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
