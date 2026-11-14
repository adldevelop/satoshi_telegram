__all__ = ["root_agent"]


def __getattr__(name: str):
	if name == "root_agent":
		from .adk_agent import satoshi_agent

		return satoshi_agent
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")