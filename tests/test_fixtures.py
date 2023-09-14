from tests import *
def test_slaps_user_fixture(slaps_user):
    assert slaps_user is not None
    assert slaps_user.username == "Islati"