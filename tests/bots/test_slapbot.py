import json
import os

from slapbot.bots import DriverType
from slapbot.bots.slaps import SlapBot

from tests import *

@pytest.fixture
def slapbot():
    """Return a new instance of the slapbot application configured for testing"""
    bot = SlapBot(driver_type=DriverType.FIREFOX, testing=True)

    yield bot

    if bot.driver is not None:
        bot.driver.quit()

    if os.path.exists(bot.config_file_name):
        os.remove(bot.config_file_name)