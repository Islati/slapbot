import pytest

from slapbot.ai.chatgpt import ChatGPT3APIWrapper


@pytest.fixture()
def chat_gpt_bot():
    chat_gpt = ChatGPT3APIWrapper()
    chat_gpt.init()

    return chat_gpt



def test_free_chat_gpt_usage():
    """Test that the free ChatGPT API can be used"""
    from slapbot.ai.chatgpt import ChatGPT3APIWrapper

    chat_gpt = ChatGPT3APIWrapper()
    chat_gpt.init()

    api_response = chat_gpt.generate_text_from_prompt("Reply")
    assert api_response is not None
    assert len(api_response) > 0
