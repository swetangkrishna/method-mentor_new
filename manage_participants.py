"""Create/revoke invited accounts in a private JSON file; never print passwords."""
import argparse
import getpass
import json
import os
from pathlib import Path
from werkzeug.security import generate_password_hash


def main():
    p = argparse.ArgumentParser()
    p.add_argument('username')
    p.add_argument('--file', default=os.environ.get('PARTICIPANTS_FILE'))
    p.add_argument('--admin', action='store_true')
    p.add_argument('--remove', action='store_true')
    args = p.parse_args()
    if not args.file:
        p.error('Set PARTICIPANTS_FILE or --file')
    path = Path(args.file)
    data = json.loads(path.read_text()) if path.exists() else {}
    if args.remove:
        data.pop(args.username, None)
    else:
        password = getpass.getpass('New password (at least 14 characters): ')
        if len(password) < 14 or password != getpass.getpass('Confirm password: '):
            p.error('Passwords must match and contain at least 14 characters')
        data[args.username] = {'role': 'admin' if args.admin else 'participant',
                               'password_hash': generate_password_hash(password)}
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(data, f)
    temp.replace(path)
    print('Account file updated.')


if __name__ == '__main__':
    main()
