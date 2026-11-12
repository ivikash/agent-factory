"""Agent Factory: a Strands Graph that turns a one-line software request into a plan, code and a review.

A System 1 decider (Strands Decider 2B, or a cheap Bedrock model standing in for it) makes the fast
routing choices at the gate. Cheap Bedrock models do the slower System 2 work in the nodes.
"""

from agent_factory.config import Settings
from agent_factory.factory import build_graph, run

__all__ = ["Settings", "build_graph", "run"]
__version__ = "0.1.0"
