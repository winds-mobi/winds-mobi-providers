import base64
import json
import os
import subprocess
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def save_file(data: bytes):
    with open('out.gpm', 'wb') as f:
        f.write(data)


def m2a_to_json(data: bytes):
    proc = subprocess.Popen(['php', 'm2a_to_json.php'], stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    proc.stdin.write(base64.b64encode(data))
    proc.stdin.close()
    result = proc.stdout.read()
    proc.wait()
    return json.loads(result)


if __name__ == '__main__':
    paths = Path(os.path.join(BASE_DIR, './gpm-files')).glob('**/*.gpm')
    for path in paths:
        with open(str(path), 'rb') as f:
            output = m2a_to_json(f.read())
            print(json.dumps(output, indent=2, ensure_ascii=False))
