"""ADK discovers this package as the agent app named "rca_system".

The `root_agent` symbol re-exported here is what ADK looks for when the
agents directory points at this folder's parent.
"""

from rca_system.agent import root_agent

__all__ = ["root_agent"]
