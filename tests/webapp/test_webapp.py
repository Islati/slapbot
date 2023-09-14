from tests import app

def test_app_initialization(app):
    """Test that the app can be initialized"""
    assert app is not None