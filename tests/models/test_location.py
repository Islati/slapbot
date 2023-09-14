import pytest

from slapbot import db
from tests import app
from slapbot.models import Location


@pytest.fixture
def location():
    """Fixture that returns a Location instance."""

    return Location(name='New York City')

def test_location_creation(location):
    """Test that a Location instance can be created."""
    assert isinstance(location, Location)

def test_location_name(location):
    """Test that the Location instance has the correct name."""
    assert location.name == 'New York City'

def test_location_unique_name(location):
    """Test that a Location instance cannot be created with a non-unique name."""
    db.session.add(location)
    db.session.commit()
    with pytest.raises(Exception):
        Location(name='New York City').save(commit=True)

def test_location_nullable_name():
    """Test that a Location instance cannot be created with a null name."""
    with pytest.raises(Exception):
        Location(name=None).save(commit=True)