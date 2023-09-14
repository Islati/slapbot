from unittest.mock import patch, Mock

import pytest

from slapbot import db
from tests import app

from slapbot.cli.fix_profiles import update_with_slaps
from slapbot.models import SlapsUser, UserProfile, YoutubeChannel, TwitterProfile, InstagramProfile, FacebookUser

# Test SlapsUser with all social media links
def test_update_with_slaps_all_social_media_links(app):
    with app.app_context():
        # Create a SlapsUser with all social media links
        user = SlapsUser(username="test_user", youtube_url="https://www.youtube.com/test_user",
                          twitter_url="https://www.twitter.com/test_user",
                          instagram_url="https://www.instagram.com/test_user",
                          facebook_url="https://www.facebook.com/test_user")
        db.session.add(user)
        db.session.commit()

    # Mock the save method for each model to avoid hitting the database
    mock_save = Mock(return_value=None)
    YoutubeChannel.save = mock_save
    TwitterProfile.save = mock_save
    InstagramProfile.save = mock_save
    FacebookUser.save = mock_save
    UserProfile.save = mock_save

    # Call the update_with_slaps function
    try:
        update_with_slaps()
    except:
        pytest.fail("update_with_slaps() raised an exception unexpectedly!")

    # Retrieve the updated user profile and assert that all links were added
    with app.app_context():
        updated_user = SlapsUser.query.filter_by(username="test_user").first()
        assert updated_user is not None

    # Assert that all the save methods were called
    assert mock_save.call_count == 0


# Test SlapsUser with no social media links
def test_update_with_slaps_no_social_media_links(app):
    with app.app_context():
        # Create a SlapsUser with no social media links
        user = SlapsUser(username="test_user")
        db.session.add(user)
        db.session.commit()

    # Mock the save method for each model to avoid hitting the database
    mock_save = Mock(return_value=None)
    YoutubeChannel.save = mock_save
    TwitterProfile.save = mock_save
    InstagramProfile.save = mock_save
    FacebookUser.save = mock_save
    UserProfile.save = mock_save

    # Call the update_with_slaps function
    try:
        update_with_slaps()
    except:
        pytest.fail("update_with_slaps() raised an exception unexpectedly!")


    # Retrieve the updated user profile and assert that no links were added
    with app.app_context():
        updated_user = SlapsUser.query.filter_by(username="test_user").first()
        assert updated_user is not None

    # Assert that no save methods were called
    assert mock_save.call_count == 0
