from __future__ import annotations

from ..models.chat import ChatResponse


async def query_data(question: str) -> ChatResponse:
    """
    TODO(Member 2): Implement LangChain Text-to-SQL agent.

    Steps:
    1. Create a read-only PostgreSQL connection (or use a read-only role).
    2. Initialize LangChain SQLDatabase with the read-only connection.
    3. Create a LangChain agent with:
       - OpenAI GPT-4o as the LLM
       - SQLDatabaseToolkit with the read-only DB
       - System prompt that restricts to SELECT queries only
    4. Run the agent with the user's question.
    5. Return the SQL, results, and explanation.

    Example:
        from langchain_openai import ChatOpenAI
        from langchain_community.utilities import SQLDatabase
        from langchain_community.agent_toolkits import SQLDatabaseToolkit
        from langgraph.prebuilt import create_react_agent

        llm = ChatOpenAI(model="gpt-4o", temperature=0)
        db = SQLDatabase.from_uri(settings.pg_dsn)
        toolkit = SQLDatabaseToolkit(db=db, llm=llm)
        agent = create_react_agent(llm, toolkit.get_tools())
        result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    """
    return ChatResponse(
        question=question,
        error="Chat with Data is not yet implemented. "
              "TODO(Member 2): Implement in backend/app/services/chat.py",
    )
