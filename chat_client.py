import os, asyncio, datetime
import jwt
from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

load_dotenv()

class SessionExpired(Exception):
    pass

def make_token(user_id: int) -> str:
    return jwt.encode(
        {"sub": str(user_id),
         "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=15)},
        os.environ["JWT_SECRET"], algorithm="HS256")

def _system():
    return (
        f"Today's date is {datetime.date.today()}.\n"
        "You are Spendly's expense tracking assistant. You manage the user's expenses with the tools provided.\n"
        "STRICT GUARDRAIL: You are ONLY allowed to assist with expenses, personal finance, spending, budgets, and expense tracking.\n"
        "If the user asks any off-topic question or request (such as writing code, programming, prime numbers, math problems, homework, jokes, general knowledge, or anything unrelated to tracking or managing their expenses), you MUST refuse and reply with EXACTLY this fixed message:\n"
        "\"I can only help you with managing and tracking your expenses.\"\n"
        "Do not answer off-topic questions under any circumstances.\n\n"
        "Formatting & Style Rules:\n"
        "- Always format amounts using the Indian Rupee symbol '₹' (e.g. ₹50, ₹200, ₹1,500). Never use '$' or any other currency symbol.\n"
        "- Do NOT show raw internal database expense IDs (like id: 133) in user confirmations or summaries. Instead, clearly state the amount, category, date, and description (e.g. 'Added ₹50 for tea today under Food.').\n"
        "- Make your responses clean, concise, polite, and well-structured.\n"
        "- When listing expenses, keep it very concise (e.g. • YYYY-MM-DD: ₹amount — Description) without raw IDs so it fits neatly.\n"
        "- Use YYYY-MM-DD dates. Never ask for or invent a user id.\n"
        "- Prefer 'Other' over a loosely related category.\n"
        "- After tools run, reply with a short, polished final answer."
    )

async def _chat(user_id: int, history: list, message: str) -> str:
    client = MultiServerMCPClient({
        "expense": {
            "transport": "streamable_http",
            "url": os.environ["MCP_URL"],
            "headers": {"Authorization": f"Bearer {make_token(user_id)}"},
        }
    })
    tools = await client.get_tools()
    named = {t.name: t for t in tools}

    llm = ChatOpenAI(
        model=os.getenv("LLM_MODEL", "openai/gpt-oss-20b"),
        api_key=os.getenv("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
        max_tokens=300,
    ).bind_tools(tools)

    messages = [SystemMessage(content=_system())]
    for m in history[-10:]:
        cls = HumanMessage if m.get("role") == "user" else AIMessage
        messages.append(cls(content=str(m.get("content", ""))[:2000]))
    messages.append(HumanMessage(content=message))

    for _ in range(5):
        resp = await llm.ainvoke(messages)
        messages.append(resp)
        if not resp.tool_calls:
            return resp.content
        for tc in resp.tool_calls:
            try:
                result = await named[tc["name"]].ainvoke(tc["args"])
            except Exception as e:
                result = f"Tool error: {e}"
            if "unauthorized" in str(result).lower():
                raise SessionExpired()
            messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
    return "Sorry, I couldn't finish that. Please try again."

def chat_reply(user_id: int, history: list, message: str) -> str:
    try:
        from langchain_openai.chat_models._client_utils import _cached_async_httpx_client
        _cached_async_httpx_client.cache_clear()
    except Exception:
        pass
    try:
        return asyncio.run(_chat(user_id, history, message))
    finally:
        try:
            from langchain_openai.chat_models._client_utils import _cached_async_httpx_client
            _cached_async_httpx_client.cache_clear()
        except Exception:
            pass
