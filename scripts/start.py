"""Cross-platform local launcher. Run from any directory with Python 3.12+."""
import errno
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / '.venv'
PY = VENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
NPM = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
BACKEND = 'http://127.0.0.1:8000'
FRONTEND = 'http://127.0.0.1:5173'


def run(args, cwd=ROOT):
    subprocess.run([str(a) for a in args], cwd=cwd, check=True)


def port_busy(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(('127.0.0.1', port))
        except OSError as exc:
            if exc.errno in (errno.EADDRINUSE, 10048):
                return True
            raise
    return False


def read_url(url):
    with urllib.request.urlopen(url, timeout=2) as response:
        if response.status != 200:
            raise RuntimeError('Сервер не готов')
        return response.read()


def meetingflow_running():
    """Verify both app identities and the frontend's connection to the API."""
    try:
        schema = json.loads(read_url(BACKEND + '/openapi.json'))
        health = json.loads(read_url(FRONTEND + '/api/health'))
        html = read_url(FRONTEND).decode('utf-8')
        return (schema.get('info', {}).get('title') == 'MeetingFlow API'
                and health.get('status') == 'ok'
                and '<title>MeetingFlow' in html)
    except (OSError, ValueError, RuntimeError):
        return False


def show_urls(already_running=False):
    if already_running:
        print('MeetingFlow уже запущен. Используется работающий экземпляр.')
    print('\nMeetingFlow: http://localhost:5173\nSwagger API: http://localhost:8000/docs', flush=True)
    if already_running:
        print('Для остановки используйте Ctrl+C в терминале первоначального запуска.\n')
    else:
        print('Для остановки нажмите Ctrl+C.\n', flush=True)


def spawn(args, cwd):
    # Give each owned server its own process group so npm's Vite child is stopped too.
    options = ({'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
               if os.name == 'nt' else {'start_new_session': True})
    return subprocess.Popen([str(a) for a in args], cwd=cwd, **options)


def stop(children):
    for child in reversed(children):
        if os.name == 'nt':
            if child.poll() is None:
                subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    for child in children:
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name == 'nt':
                child.kill()
            else:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            child.wait(timeout=5)


def main():
    if sys.version_info < (3, 12):
        raise RuntimeError('Требуется Python 3.12 или новее.')
    busy = [port for port in (8000, 5173) if port_busy(port)]
    if busy:
        if len(busy) == 2 and meetingflow_running():
            if '--demo' in sys.argv:
                run([PY, '-m', 'app.seed'], ROOT / 'backend')
            show_urls(already_running=True)
            return
        ports = ', '.join(map(str, busy))
        raise RuntimeError(
            f'Порты заняты: {ports}. Полный работающий экземпляр MeetingFlow не найден. '
            'Остановите приложение, занимающее эти порты, затем повторите ./start.sh. '
            'Новые серверы не запущены.')
    if not NPM:
        raise RuntimeError('Установите Node.js 22.12+ (с npm).')
    if not PY.exists():
        run([sys.executable, '-m', 'venv', VENV])
    run([PY, '-m', 'pip', 'install', '--quiet', '--disable-pip-version-check',
         '-r', ROOT / 'backend/requirements.txt'])
    run([PY, '-m', 'alembic', '-c', 'alembic.ini', 'upgrade', 'head'], ROOT / 'backend')
    if '--demo' in sys.argv:
        run([PY, '-m', 'app.seed'], ROOT / 'backend')
    if not (ROOT / 'frontend/node_modules').exists():
        run([NPM, 'ci'], ROOT / 'frontend')
    children = []
    try:
        children.append(spawn([PY, '-m', 'uvicorn', 'app.main:app', '--host',
                               '127.0.0.1', '--port', '8000'], ROOT / 'backend'))
        children.append(spawn([NPM, 'run', 'dev'], ROOT / 'frontend'))
        for _ in range(60):
            if any(p.poll() is not None for p in children):
                raise RuntimeError('Сервер завершился при запуске. Проверьте сообщения выше.')
            if meetingflow_running():
                # Catch a server that exited while the HTTP probes were in flight.
                if any(p.poll() is not None for p in children):
                    raise RuntimeError('Сервер завершился при запуске. Проверьте сообщения выше.')
                break
            time.sleep(.5)
        else:
            raise RuntimeError('Не удалось дождаться запуска серверов.')
        show_urls()
        while True:
            if any(p.poll() is not None for p in children):
                raise RuntimeError('Один из серверов остановился. Проверьте сообщения выше.')
            time.sleep(.5)
    finally:
        stop(children)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nMeetingFlow остановлен.')
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f'Ошибка запуска: {exc}', file=sys.stderr)
        sys.exit(1)
