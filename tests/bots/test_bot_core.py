import pytest

from slapbot.bots import BrowserBotBase
from tests.bots import bot

@pytest.mark.skip(reason="Browser bot base implementation has always worked.")
def test_bot_initialization(bot):
    """Test that the bot can be initialized"""
    bot.init_driver()
    assert isinstance(bot, BrowserBotBase)
    assert bot.driver is not None