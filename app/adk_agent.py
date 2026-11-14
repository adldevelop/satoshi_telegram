from google.adk.agents import Agent
from dotenv import load_dotenv

load_dotenv()

from .prompt import ROOT_AGENT_PROMPT
from .tools.get_accounts_status import get_account_status_tool
from .tools.get_fib_levels import get_fib_levels
from .tools.get_market_data import get_market_data
from .tools.sell_market import sell_market_tool


satoshi_agent = Agent(
    name="satoshi",
    model="gemini-2.0-flash",
    description="Agente autônomo para trading MARGIN BTC com base em retrações de Fibonacci e alavancagem 5x.",
    instruction=ROOT_AGENT_PROMPT,
    tools=[get_fib_levels, get_market_data, sell_market_tool, get_account_status_tool],
)