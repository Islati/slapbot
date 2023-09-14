import faker
import pytest

from slapbot import create_app, teardown_app, destroy_database, db
from slapbot.config import TestConfig
from slapbot.models import SlapsUser, Location, UserProfile, YoutubeChannel

faker = faker.Faker()


@pytest.fixture(scope='function', autouse=True)
def app():
    print("Destroying database incase anything was left behind during an error...")
    app = create_app(TestConfig())

    yield app
    print("Tearing down application...")
    destroy_database()

    teardown_app(app)


@pytest.fixture(scope="function")
def client(app):
    return app.test_client()


@pytest.fixture()
def runner(app):
    return app.test_cli_runner()


@pytest.fixture(autouse=True)
def location():
    location = Location(name=faker.city())
    yield location.save(commit=True)


@pytest.fixture(autouse=True)
def random_location():
    location = Location(name=faker.city())
    yield location.save(commit=True)


@pytest.fixture(scope='function')
def slaps_user(app, location):
    user = SlapsUser(profile_url="http://slaps.com/Islati", username="Islati", description="I am a test user",
                     location=location)
    yield user.save(commit=True)


@pytest.fixture(scope='function')
def random_fake_slaps_user(app, random_location):
    name = faker.name()
    user = SlapsUser(profile_url=f"http://slaps.com/{name}", username=name, description=faker.text(),
                     location=random_location)
    yield user.save(commit=True)


@pytest.fixture(scope='function')
def youtube_channel():
    youtube_channel = YoutubeChannel(name="Islati", url="https://www.youtube.com/channel/UC1HBD9-ZHbEe1cN8Pa2BL_g")
    yield youtube_channel.save(commit=True)


@pytest.fixture(scope='function')
def user_profile(slaps_user):
    profile = UserProfile(slaps_user=slaps_user).save(commit=True)
    yield profile
