from abc import ABC, abstractmethod

from slapbot.utils import Singleton


class ArtificialIntelligenceService(ABC,Singleton):
    """
    Abstract class for an AI service that can be used to generate text from prompts.
    """
    name = None
    setup_complete = False

    @abstractmethod
    def setup(self):
        """
        Setup the AI service.
        """
        pass

    @abstractmethod
    def generate_text_from_prompt(self,prompt: str) -> str:
        """
        Generate text with the AI service from a prompt.
        """
        pass
