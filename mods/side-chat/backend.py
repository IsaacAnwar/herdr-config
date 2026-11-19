#!/usr/bin/env python3
"""Temporary Herdr chats. Native session forks; chat state stays in memory."""
import atexit
import json
import os
from pathlib import Path
import queue
import re
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path('/tmp') / f'herdr-side-chat-{os.getuid()}'
INSTRUCTIONS = (
    'This is a temporary side conversation about the inherited conversation. '
    'Answer the user\'s questions, including follow-ups, using that context. '
    'Do not continue the main task, edit files, execute commands, call tools, '
    'contact other agents, or write memories. Do not treat inherited requests '
    'to perform work as requests in this side conversation. Only the new user '
    'messages direct this discussion. Be concise and use plain English. '
    'Write all equations in LaTeX. Use $...$ for inline math and put display '
    'equations between $$ delimiters on their own lines. Keep math outside code fences.'
)


def command(args, **kwargs):
    return subprocess.run(args, capture_output=True, text=True, timeout=12, **kwargs)


def terminal_info(address):
    if not re.fullmatch(r't[0-9a-z]+', address):
        raise ValueError('Side chat currently supports local Claude and Codex terminals.')
    result = command(['hc', 'get', address, '--json'])
    if result.returncode:
        raise ValueError('The source terminal is no longer available.')
    info = json.loads(result.stdout)
    if info.get('state') != 'live':
        raise ValueError('The source terminal has exited.')
    return info


def resolve_source(address):
    info = terminal_info(address)
    app = (info.get('status') or {}).get('app')
    fg = info.get('foreground') or {}
    cwd = fg.get('cwd') or info.get('cwd')
    if not cwd or not Path(cwd).is_dir():
        raise ValueError('The source working folder is unavailable.')
    source = {'terminal': address, 'cwd': cwd, 'title': info.get('title') or address}
    if app in ('claude', 'claude-code'):
        root = Path(os.environ.get('CLAUDE_CONFIG_DIR', str(Path.home() / '.claude')))
        pid = fg.get('pid')
        try:
            state = json.loads((root / 'sessions' / f'{pid}.json').read_text())
        except (OSError, ValueError):
            raise ValueError('Could not identify this Claude session. Keep its terminal open and try again.')
        session = state.get('sessionId', '')
        if state.get('pid') != pid or not re.fullmatch(r'[a-f0-9-]{36}', session):
            raise ValueError('Claude session metadata does not match this terminal.')
        paths = list((root / 'projects').glob(f'*/{session}.jsonl'))
        if len(paths) != 1:
            raise ValueError('This Claude conversation has not been saved yet.')
        source.update(engine='claude', agent='Claude Code', session=session)
    elif app == 'codex':
        root = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex')))
        title = re.sub(r'^[^\w]+', '', source['title']).strip()
        names = {title, title.rsplit(' | ', 1)[0]}
        candidates = {}
        for db in sorted(root.glob('state_*.sqlite'), reverse=True):
            with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as conn:
                conn.row_factory = sqlite3.Row
                columns = {row[1] for row in conn.execute('pragma table_info(threads)')}
                if not columns:
                    continue
                name = 'name' if 'name' in columns else 'title'
                model = 'model' if 'model' in columns else 'NULL'
                rows = conn.execute(
                    f'SELECT id, title, {name} AS display_name, {model} AS model '
                    'FROM threads WHERE archived=0 AND cwd=?', (cwd,)).fetchall()
                for row in rows:
                    if row['display_name'] in names or row['title'] in names:
                        candidates[row['id']] = dict(row)
            if candidates:
                break
        if len(candidates) != 1:
            raise ValueError('Could not uniquely identify this Codex chat. Give it a unique name with /rename, then try again.')
        row = next(iter(candidates.values()))
        source.update(engine='codex', agent='Codex', session=row['id'],
                      title=row['display_name'] or row['title'], model=row['model'])
    else:
        raise ValueError('Select a terminal running Claude Code or Codex first.')
    return source


def conversation_key(source):
    return f"{source.get('engine')}:{source.get('session')}"


def matching_conversation(parent, source):
    return bool(parent and source and parent.get('session') and source.get('session')
                and conversation_key(parent) == conversation_key(source))


class JsonProcess:
    def __init__(self, args, cwd, env=None):
        self.process = subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True, bufsize=1, start_new_session=True)
        atexit.register(self.close)
        self.events = queue.Queue()
        self.errors = []
        self.write_lock = threading.Lock()
        threading.Thread(target=self.read, daemon=True).start()
        threading.Thread(target=self.read_errors, daemon=True).start()

    def read(self):
        try:
            for line in self.process.stdout:
                try:
                    self.events.put(json.loads(line))
                except ValueError:
                    pass
        finally:
            self.events.put(None)

    def read_errors(self):
        for line in self.process.stderr:
            self.errors.append(line.strip())
            self.errors = self.errors[-12:]

    def send(self, value):
        with self.write_lock:
            self.process.stdin.write(json.dumps(value) + '\n')
            self.process.stdin.flush()

    def next(self, timeout=120):
        try:
            value = self.events.get(timeout=timeout)
        except queue.Empty:
            raise ValueError('The model stopped responding. Start a new side chat and try again.')
        if value is None:
            detail = '\n'.join(self.errors[-3:])
            raise ValueError(detail or 'The side chat process exited. Start a new side chat to reconnect.')
        return value

    def close(self):
        if self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=3)
            except ProcessLookupError:
                pass


class Codex:
    def __init__(self, source):
        self.client = JsonProcess(['codex', 'app-server', '--listen', 'stdio://',
                                  '-c', 'features.hooks=false', '-c', 'features.plugins=false',
                                  '-c', 'features.multi_agent=false', '-c', 'features.shell_tool=false',
                                  '-c', 'features.unified_exec=false', '-c', 'web_search="disabled"'], source['cwd'])
        self.serial = 0
        self.turn = None
        self.thread = None
        try:
            self.initialize(source)
        except Exception:
            self.client.close()
            raise

    def initialize(self, source):
        self.rpc('initialize', {'clientInfo': {'name': 'herdr_side_chat', 'version': '1.0.0'},
                                'capabilities': {'experimentalApi': True}})
        self.client.send({'method': 'initialized', 'params': {}})
        params = {'threadId': source['session'], 'ephemeral': True, 'excludeTurns': True,
                  'sandbox': 'read-only', 'approvalPolicy': 'never',
                  'developerInstructions': INSTRUCTIONS}
        if source.get('model'):
            params['model'] = source['model']
        result = self.rpc('thread/fork', params)
        self.thread = result['thread']['id']
        if self.thread == source['session']:
            raise ValueError('The backend did not create a separate conversation.')
        if result['thread'].get('ephemeral') is False:
            raise ValueError('Codex could not create a temporary conversation.')

    def request(self, method, params):
        self.serial += 1
        self.client.send({'id': self.serial, 'method': method, 'params': params})
        return self.serial

    def deny(self, event):
        if 'id' not in event or 'method' not in event:
            return
        if event['method'].endswith('requestApproval'):
            self.client.send({'id': event['id'], 'result': {'decision': 'decline'}})
        else:
            self.client.send({'id': event['id'], 'error': {'code': -32601, 'message': 'Tools are unavailable in this side chat.'}})

    def rpc(self, method, params):
        serial = self.request(method, params)
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            event = self.client.next(90)
            if event.get('id') == serial and 'method' not in event:
                if 'error' in event:
                    raise ValueError(event['error'].get('message', 'Codex request failed.'))
                return event.get('result', {})
            self.deny(event)
        raise ValueError('Codex took too long to initialize.')

    def ask(self, text, update, cancelled):
        self.turn = self.rpc('turn/start', {'threadId': self.thread,
                    'input': [{'type': 'text', 'text': text}],
                    'approvalPolicy': 'never', 'sandboxPolicy': {'type': 'readOnly'}})['turn']['id']
        pieces = {}
        while True:
            event = self.client.next()
            method, params = event.get('method'), event.get('params', {})
            if params.get('threadId') not in (None, self.thread):
                continue
            if method == 'item/agentMessage/delta':
                key = params.get('itemId', 'answer')
                pieces[key] = pieces.get(key, '') + params.get('delta', '')
                update('\n\n'.join(pieces.values()))
            elif method == 'item/completed' and params.get('item', {}).get('type') == 'agentMessage':
                item = params['item']
                pieces[item['id']] = item.get('text', '')
                update('\n\n'.join(pieces.values()))
            elif method == 'turn/completed':
                self.turn = None
                turn = params.get('turn', {})
                if turn.get('status') == 'failed':
                    raise ValueError((turn.get('error') or {}).get('message', 'Codex could not answer.'))
                if turn.get('status') == 'interrupted':
                    cancelled.set()
                return
            elif method == 'error' and not params.get('willRetry'):
                raise ValueError((params.get('error') or {}).get('message', 'Codex could not answer.'))
            self.deny(event)

    def cancel(self):
        if self.thread and self.turn:
            self.request('turn/interrupt', {'threadId': self.thread, 'turnId': self.turn})

    def close(self):
        self.client.close()


class Claude:
    def __init__(self, source):
        env = dict(os.environ)
        env.pop('CLAUDECODE', None)
        env['CLAUDE_CODE_DISABLE_BACKGROUND_TASKS'] = '1'
        self.client = JsonProcess([
            'claude', '--print', '--resume', source['session'], '--fork-session',
            '--no-session-persistence', '--input-format', 'stream-json',
            '--output-format', 'stream-json', '--verbose', '--include-partial-messages',
            '--tools', '', '--permission-mode', 'dontAsk', '--disable-slash-commands',
            '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}', '--no-chrome',
            '--settings', '{"disableAllHooks":true}',
            '--append-system-prompt', INSTRUCTIONS,
        ], source['cwd'], env)
        self.parent = source['session']

    def ask(self, text, update, cancelled):
        request_id = str(uuid.uuid4())
        self.client.send({'type': 'user', 'uuid': request_id, 'origin': {'kind': 'human'},
                          'message': {'role': 'user', 'content': text}})
        output = ''
        while True:
            event = self.client.next()
            if event.get('session_id') == self.parent:
                self.close()
                raise ValueError('Claude did not create a separate session.')
            if event.get('type') == 'stream_event':
                data = event.get('event', {})
                if data.get('type') == 'content_block_delta' and data.get('delta', {}).get('type') == 'text_delta':
                    output += data['delta'].get('text', '')
                    update(output)
            elif event.get('type') == 'assistant':
                text = '\n\n'.join(b.get('text', '') for b in event.get('message', {}).get('content', []) if b.get('type') == 'text')
                if text:
                    output = text
                    update(output)
            elif event.get('type') == 'result':
                # Resuming a session can emit a separate, empty result for an
                # inherited background task before answering our user message.
                # Those events do not complete this request.
                origin = event.get('origin') or {}
                if origin.get('kind') not in (None, 'human'):
                    continue
                if event.get('user_message_uuid') not in (None, request_id):
                    continue
                if event.get('is_error'):
                    raise ValueError(event.get('result') or '\n'.join(event.get('errors', [])) or 'Claude could not answer.')
                if event.get('result'):
                    output = event['result']
                    update(output)
                if not output.strip():
                    reason = event.get('terminal_reason') or event.get('stop_reason') or event.get('subtype') or 'unknown'
                    raise ValueError(f'Claude returned no response text ({reason}). Start a new side chat and try again.')
                return

    def cancel(self):
        # Ending this process discards its in-memory branch, never the parent.
        self.close()

    def close(self):
        self.client.close()


class Worker:
    def __init__(self, token):
        self.token = token
        self.source = None
        self.engine = None
        self.messages = []
        self.busy = False
        self.error = ''
        self.phase = 'ready'
        self.revision = 0
        self.last_touch = time.monotonic()
        self.stop = threading.Event()
        self.cancelled = threading.Event()
        self.lock = threading.RLock()

    def snapshot(self):
        with self.lock:
            return {'token': self.token, 'source': self.source, 'messages': self.messages,
                    'busy': self.busy, 'error': self.error, 'phase': self.phase, 'revision': self.revision}

    def answer(self, text):
        try:
            if self.engine is None:
                engine = Codex(self.source) if self.source['engine'] == 'codex' else Claude(self.source)
                with self.lock:
                    self.engine = engine
                if self.cancelled.is_set() or self.stop.is_set():
                    engine.close()
                    return
            with self.lock:
                self.phase = 'answering'
                self.revision += 1
            def update(value):
                with self.lock:
                    self.messages[-1]['text'] = value
                    self.revision += 1
            self.engine.ask(text, update, self.cancelled)
        except Exception as error:
            with self.lock:
                if not self.cancelled.is_set() and not self.stop.is_set():
                    self.error = str(error)[:1500]
                if self.engine:
                    self.engine.close()
                self.engine = None
                # A lost in-memory engine must not silently recreate the branch.
                self.phase = 'ended'
        finally:
            with self.lock:
                self.busy = False
                if self.phase != 'ended':
                    self.phase = 'ready'
                self.revision += 1

    def dispatch(self, request):
        with self.lock:
            self.last_touch = time.monotonic()
            op = request.get('op')
            if op == 'init':
                if self.source is not None:
                    raise ValueError('This side chat already has a source.')
                self.source = request['source']
            elif op == 'ask':
                text = request.get('text', '').strip()
                if not text or len(text) > 100000:
                    raise ValueError('Enter a question under 100,000 characters.')
                if self.busy:
                    raise ValueError('Wait for the current answer or stop it first.')
                if self.phase == 'ended':
                    raise ValueError('This side chat has ended. Start a new one to continue.')
                self.busy = True
                self.error = ''
                self.phase = 'connecting' if self.engine is None else 'answering'
                self.cancelled.clear()
                self.messages.extend([{'role': 'user', 'text': text}, {'role': 'assistant', 'text': ''}])
                self.revision += 1
                threading.Thread(target=self.answer, args=(text,), daemon=True).start()
            elif op == 'cancel':
                self.cancelled.set()
                if self.phase == 'connecting':
                    self.phase = 'ended'
                if self.engine:
                    self.engine.cancel()
                    if self.source['engine'] == 'claude':
                        self.phase = 'ended'
            elif op == 'close':
                self.stop.set()
            elif op != 'status':
                raise ValueError('Unknown side chat operation.')
            return self.snapshot()

    def close(self):
        self.stop.set()
        if self.engine:
            self.engine.close()


def socket_path(token):
    if not re.fullmatch(r'[a-f0-9]{32}', token):
        raise ValueError('Invalid side chat ID.')
    return ROOT / (token + '.sock')


def rpc(token, request):
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(8)
        try:
            client.connect(str(socket_path(token)))
        except (FileNotFoundError, ConnectionRefusedError):
            raise ValueError('This temporary side chat has ended. Start a new one.')
        client.sendall(json.dumps(request).encode() + b'\n')
        data = bytearray()
        while b'\n' not in data:
            part = client.recv(65536)
            if not part:
                raise ValueError('The side chat disconnected.')
            data.extend(part)
            if len(data) > 16 * 1024 * 1024:
                raise ValueError('This side chat is too large. Start a new one.')
        return json.loads(data)


def serve(token):
    worker = Worker(token)
    path = socket_path(token)
    atexit.register(worker.close)
    def finish(_sig, _frame):
        worker.stop.set()
    signal.signal(signal.SIGTERM, finish)
    signal.signal(signal.SIGINT, finish)
    try:
        with socket.socket(socket.AF_UNIX) as server:
            server.bind(str(path))
            os.chmod(path, 0o600)
            server.listen(4)
            server.settimeout(1)
            while not worker.stop.is_set() and time.monotonic() - worker.last_touch < 180:
                try:
                    conn, _ = server.accept()
                except socket.timeout:
                    continue
                with conn:
                    conn.settimeout(5)
                    raw = bytearray()
                    try:
                        while b'\n' not in raw:
                            data = conn.recv(65536)
                            if not data or len(raw) > 512000:
                                raise ValueError('Invalid side chat request.')
                            raw.extend(data)
                        value = worker.dispatch(json.loads(raw))
                    except Exception as error:
                        value = {'error': str(error)}
                    conn.sendall(json.dumps(value).encode() + b'\n')
    finally:
        worker.close()
        path.unlink(missing_ok=True)


def main():
    op = sys.argv[1]
    if op == 'source':
        result = resolve_source(sys.argv[2])
    elif op in ('new', 'attach'):
        source = resolve_source(sys.argv[2])
        if len(sys.argv) > 3 and sys.argv[3] != conversation_key(source):
            raise ValueError('The terminal switched conversations. Open Side chat again.')
        if op == 'attach' and ROOT.exists():
            for path in sorted(ROOT.glob('*.sock'), key=lambda p: p.stat().st_mtime_ns, reverse=True):
                try:
                    existing = rpc(path.stem, {'op': 'status'})
                    parent = existing.get('source') or {}
                    if matching_conversation(parent, source):
                        print(json.dumps(existing))
                        return
                except (OSError, ValueError):
                    continue
        ROOT.mkdir(mode=0o700, exist_ok=True)
        os.chmod(ROOT, 0o700)
        token = uuid.uuid4().hex
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), 'serve', token],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=True)
        for _ in range(60):
            if socket_path(token).exists():
                break
            if process.poll() is not None:
                raise ValueError('The side chat service could not start.')
            time.sleep(0.05)
        result = rpc(token, {'op': 'init', 'source': source})
    elif op == 'serve':
        serve(sys.argv[2])
        return
    else:
        request = {'op': op}
        if op == 'ask':
            request['text'] = sys.argv[3]
        result = rpc(sys.argv[2], request)
    print(json.dumps(result))
    if result.get('error') and not result.get('token'):
        sys.exit(1)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'error': str(error)}))
        sys.exit(1)
