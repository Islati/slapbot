import os

import pytest

from slapbot.bots import BrowserBotBase, DriverType


@pytest.fixture()
def bot():
    """Return a new instance of the browserbot application configured for testing. Is not initialized."""
    bot = BrowserBotBase(driver_type=DriverType.FIREFOX, late_init=True)
    yield bot

    bot.driver.quit()

    if os.path.exists(bot.config_file_name):
        os.remove(bot.config_file_name)

@pytest.fixture()
def headless_bot():
    """Return a new instance of the browserbot application configured for testing. Is not initialized."""
    bot = BrowserBotBase(driver_type=DriverType.FIREFOX, late_init=True, headless=True)
    yield bot

    bot.driver.quit()

    if os.path.exists(bot.config_file_name):
        os.remove(bot.config_file_name)




