from slapbot.models import SlapsUser
from tests import *


def test_get_random(slaps_user, random_fake_slaps_user):
    # Test that the get_random method returns a random record
    # from the table
    random_slaps_user = SlapsUser.get_random()
    assert random_slaps_user is not None
    assert random_slaps_user.id > -1
