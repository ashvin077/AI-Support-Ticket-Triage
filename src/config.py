import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def _get_secret(key:str, default:str | None = None):
    """ 
    This function gets secret uri, api, key, token from .env file,
    returns str or None
    """
    val = os.environ.get(key, default)
    if val is not None:
        return val
    
    try:
        import streamlit as st 
        return st.secrets.get(key, default)
    except Exception:
        return default


DATABASE_USER_NAME = _get_secret("DATABASE_USER_NAME")
DATABASE_PASSWORD = _get_secret("DATABASE_PASSWORD")
GROQ_API_KEY= _get_secret("GROQ_API_KEY")
NEON_DATABASE_URL= _get_secret("NEON_DATABASE_URL")

database_url = f"postgresql://postgres:{DATABASE_PASSWORD}@localhost:{DATABASE_USER_NAME}"

database_url_psycopg=f"postgresql+psycopg://postgres:{DATABASE_PASSWORD}@localhost:{DATABASE_USER_NAME}"
