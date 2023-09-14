from slapbot import utils
from slapbot.ai import ArtificialIntelligenceService

import requests

import openai


class ChatGPT3APIWrapper(ArtificialIntelligenceService):
    """
    Component built around a free service hosted by the community (https://github.com/ayaka14732/ChatGPTAPIFree) to provide fast responses
    compared to the paid service.
    """

    name = "FreeChatGPT"
    _service = None
    _on_rate_limit_cooldown = False
    _base_url = "https://api.openai.com/v1"
    _api_key = ""

    def init(self):
        utils.debug("Initializing FreeChatGPT service module...", fg="green")
        openai.api_key = self._api_key
        self.setup()

    def _perform_chat_completions_post_request(self, prompt: str) -> str:
        """
        Generate text with the ChatGPT service from a prompt.
        """
        if self._on_rate_limit_cooldown is True:
            raise Exception("FreeChatGPT rate limit cooldown is active.")

        try:
            response = requests.post(f"{self._base_url}/chat/completions",
                                     json={
                                         "model": "gpt-3.5-turbo",
                                         "messages": [{"role": "user", "content": prompt}],
                                         "temperature": 1.0
                                     }, headers={"Content-Type": "application/json",
                                                 "Authorization": f"Bearer {self._api_key}"})
        except Exception as e:
            utils.debug(f"Rate limit hit: {e}", fg="red")
            self._on_rate_limit_cooldown = True
            raise Exception("ChatGPT Api rate limit hit.")

        return response.json()

    def generate_text_from_prompt(self, prompt: str) -> str:
        return self._perform_chat_completions_post_request(prompt=prompt)['choices'][0]['message']['content']

    def generate_text_from_prompt_with_context(self, message: str,
                                               system_role: str = "You are a rapper promoting their music to another, and want to gain their attention to have them play your music.") -> str:
        """
        Generate text with the ChatGPT service from a prompt.
        :param message:
        :param system_role:
        :return:
        """
        messages = [{"role": "system", "content": f"{system_role}"}, {"role": "user", "content": message}]

        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages
        )

        return completion.choices[0].message.content

    def setup(self):
        """
        Setup the ChatGPT service.
        """
        self.setup_complete = True
