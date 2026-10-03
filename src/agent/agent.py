import os
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from src import config
from sqlalchemy import create_engine, text
import json
from src.prompt import system_prompt

load_dotenv()

llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0, model_kwargs={"seed": 42}, reasoning_effort="medium")
engine = create_engine(config.NEON_DATABASE_URL)

openai_llm = ChatOpenAI(
    model="google/gemma-4-31b-it",
    api_key=config.OPEN_ROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1",
)


@tool
def get_customers_messages():
    """
        From the 'customer_messages' table of 'ticket_triage' database, fetch all the '20' records in that table with their 'id'
        and 'message'.
    Returns: a json array of 'id' and 'message'.
    """
    sql_query = """SELECT * FROM customer_messages LIMIT 20;"""
    
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


fallback_agent = create_agent(
    openai_llm,
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
