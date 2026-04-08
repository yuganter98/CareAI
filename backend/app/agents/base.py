from abc import ABC, abstractmethod
from typing import Dict, Any
import logging

class BaseAgent(ABC):
    """
    Abstract Base Class representing a single Node in the CareAI Orchestration Graph.
    Ensures all AI Agents share an identical interface, allowing the Orchestrator to swap them dynamically.
    """
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes the agent's core capability.
        
        Args:
            state (Dict[str, Any]): The globally shared memory/context payload spanning the workflow.
            
        Returns:
            Dict[str, Any]: The mutated/expanded state dictionary containing the Agent's new outputs.
        """
        pass
