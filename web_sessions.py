"""Private, atomic JSON checkpoints for single-instance browser sessions."""
import json
import os
from pathlib import Path
import re
from stage_tracker import StageTracker


def directory():
    default = Path(os.environ.get('DB_PATH', 'db/pedagogy_rl.db')).parent / 'web_sessions'
    return Path(os.environ.get('WEB_SESSIONS_DIR', str(default)))


def path_for(session_id):
    if not isinstance(session_id, str) or not re.fullmatch(r'HV_[A-Za-z0-9_]+', session_id):
        raise ValueError('Invalid session ID')
    return directory() / (session_id + '.json')


def encode_session(sess):
    data = {k: v for k, v in sess.items() if k not in ('tracker', 'rag_cache')}
    state = vars(sess['tracker']).copy()
    for key, value in state.items():
        if isinstance(value, set):
            state[key] = sorted(value)
    state['filled_parameters'] = {str(k): sorted(v) for k, v in state['filled_parameters'].items()}
    data['tracker_state'] = state
    return json.loads(json.dumps(data))


def save(sess):
    data = encode_session(sess)
    target = path_for(sess['session_id'])
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix('.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(data, f)
        f.flush()
        os.fsync(f.fileno())
    temp.replace(target)


def load(session_id):
    try:
        data = json.loads(path_for(session_id).read_text())
    except (FileNotFoundError, ValueError):
        return None
    return decode_session(data)


def decode_session(data):
    data = json.loads(json.dumps(data))
    tracker = StageTracker()
    state = data.pop('tracker_state')
    for key, default in vars(tracker).items():
        if key in state:
            value = state[key]
            if isinstance(default, set):
                value = set(value)
            if key == 'filled_parameters':
                value = {int(k): set(v) for k, v in value.items()}
            setattr(tracker, key, value)
    data.update(tracker=tracker, rag_cache={})
    return data
