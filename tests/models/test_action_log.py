import json

from tests import app
from slapbot.models import ActionLog


def test_action_log_json_serialization(app):
    assert ActionLog.get('test_action_log_json_serialization',[]).value == json.dumps([])
    assert json.loads(ActionLog.get('test_action_log_json_serialization',[]).value) == []
    ActionLog.log('test_action_log_json_serialization', [1,2,3,4,5])
    assert ActionLog.get('test_action_log_json_serialization',[]).value == json.dumps([1,2,3,4,5])

