"""Exercise session identity, fork isolation, and side-chat lifecycle without model calls."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from contextlib import closing
import os
import subprocess
import sys
import time
import uuid
import socket

spec = importlib.util.spec_from_file_location('side_backend', Path(__file__).with_name('backend.py'))
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class SideChatTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows transport')
    def test_windows_service_starts_without_unix_sockets(self):
        token = uuid.uuid4().hex
        b.ROOT.mkdir(exist_ok=True)
        process = subprocess.Popen([sys.executable, str(Path(__file__).with_name('backend.py')), 'serve', token],
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            for _ in range(60):
                if b.socket_path(token).exists():
                    break
                self.assertIsNone(process.poll())
                time.sleep(0.05)
            self.assertEqual(b.rpc(token, {'op': 'status'})['phase'], 'ready')
            port = json.loads(b.socket_path(token).read_text())['port']
            with socket.create_connection(('127.0.0.1', port), timeout=3) as client:
                client.sendall(b'{"op":"status","_token":"wrong"}\n')
                self.assertIn('Invalid side chat connection', json.loads(client.recv(8192))['error'])
            b.rpc(token, {'op': 'close'})
            process.wait(timeout=4)
            self.assertFalse(b.socket_path(token).exists())
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()

    @unittest.skipUnless(os.name == 'nt', 'Windows path normalization')
    def test_windows_extended_paths_and_activity_titles(self):
        with tempfile.TemporaryDirectory() as folder:
            with closing(sqlite3.connect(Path(folder) / 'state_1.sqlite')) as conn, conn:
                conn.execute('CREATE TABLE threads (id TEXT, title TEXT, name TEXT, model TEXT, cwd TEXT, archived INTEGER)')
                conn.execute('INSERT INTO threads VALUES (?,?,?,?,?,0)', ('session', 'Original prompt', 'Fix panels', 'model', '\\\\?\\' + folder.upper()))
            info = {'title': '[ . ] Action Required | Fix panels | user', 'status': {'app': 'codex'}, 'foreground': {'cwd': folder}}
            with patch.object(b, 'terminal_info', return_value=info), patch.dict(b.os.environ, {'CODEX_HOME': folder}):
                self.assertEqual(b.resolve_source('t1')['session'], 'session')

    def test_same_conversation_matches_across_terminals_but_not_across_sessions(self):
        parent = {'engine': 'codex', 'session': 'a', 'terminal': 't1'}
        self.assertTrue(b.matching_conversation(parent, {**parent, 'terminal': 't2'}))
        self.assertFalse(b.matching_conversation(parent, {**parent, 'session': 'b'}))
        self.assertFalse(b.matching_conversation(parent, {**parent, 'engine': 'claude'}))
        self.assertFalse(b.matching_conversation({}, {}))

    def test_conversation_switch_between_lookup_and_attach_cannot_create_wrong_fork(self):
        with patch.object(b.sys, 'argv', ['backend.py', 'attach', 't1', 'codex:old']), \
             patch.object(b, 'resolve_source', return_value={'engine': 'codex', 'session': 'new'}), \
             patch.object(b.subprocess, 'Popen') as launch:
            with self.assertRaisesRegex(ValueError, 'switched conversations'):
                b.main()
            launch.assert_not_called()

    def test_ambiguous_codex_titles_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / 'state_1.sqlite'
            with closing(sqlite3.connect(db)) as conn, conn:
                conn.execute('CREATE TABLE threads (id TEXT, title TEXT, name TEXT, model TEXT, cwd TEXT, archived INTEGER)')
                conn.executemany('INSERT INTO threads VALUES (?,?,?,?,?,0)', [
                    ('first', 'Same task', 'Same task', 'model-a', folder),
                    ('second', 'Same task', 'Same task', 'model-b', folder),
                ])
            info = {'title': '⠹ Same task | project', 'status': {'app': 'codex'}, 'foreground': {'cwd': folder}}
            with patch.object(b, 'terminal_info', return_value=info), patch.dict(b.os.environ, {'CODEX_HOME': folder}):
                with self.assertRaisesRegex(ValueError, 'uniquely identify'):
                    b.resolve_source('t1')
                with closing(sqlite3.connect(db)) as conn, conn:
                    conn.execute("DELETE FROM threads WHERE id='second'")
                self.assertEqual(b.resolve_source('t1')['session'], 'first')

    def test_codex_forks_ephemerally_and_never_starts_parent(self):
        class Client:
            def __init__(self, *args, **kwargs): self.sent = []; self.events = []
            def send(self, event):
                self.sent.append(event)
                if event.get('method') == 'initialize': self.events.append({'id': event['id'], 'result': {}})
                if event.get('method') == 'thread/fork': self.events.append({'id': event['id'], 'result': {'thread': {'id': 'child'}}})
                if event.get('method') == 'turn/start':
                    self.events.extend([{'id': event['id'], 'result': {'turn': {'id': 'turn'}}},
                        {'method': 'item/agentMessage/delta', 'params': {'threadId': 'child', 'itemId': 'a', 'delta': 'answer'}},
                        {'method': 'turn/completed', 'params': {'threadId': 'child', 'turn': {'status': 'completed'}}}])
            def next(self, *args): return self.events.pop(0)
            def close(self): pass
        with patch.object(b, 'JsonProcess', Client):
            engine = b.Codex({'session': 'parent', 'cwd': '/tmp', 'model': 'source-model'})
            answers = []
            engine.ask('question', answers.append, threading.Event())
            fork = next(e for e in engine.client.sent if e.get('method') == 'thread/fork')
            turn = next(e for e in engine.client.sent if e.get('method') == 'turn/start')
            self.assertTrue(fork['params']['ephemeral'])
            self.assertEqual(fork['params']['threadId'], 'parent')
            self.assertIn('Write all equations in LaTeX.', fork['params']['developerInstructions'])
            self.assertEqual(turn['params']['threadId'], 'child')
            self.assertEqual(answers[-1], 'answer')

    def test_claude_keeps_a_stream_for_followups_and_has_no_tools(self):
        class Client:
            def __init__(self, args, *rest): self.args = args; self.events = []; self.prompts = []
            def send(self, event):
                self.prompts.append(event['message']['content'])
                self.events.extend([{'type': 'assistant', 'session_id': 'child', 'message': {'content': [{'type': 'text', 'text': str(len(self.prompts))}]}},
                                    {'type': 'result', 'session_id': 'child', 'result': str(len(self.prompts))}])
            def next(self): return self.events.pop(0)
            def close(self): pass
        with patch.object(b, 'JsonProcess', Client):
            engine = b.Claude({'session': 'parent', 'cwd': '/tmp'})
            answers = []
            engine.ask('one', answers.append, threading.Event())
            engine.ask('two', answers.append, threading.Event())
            self.assertEqual(answers[-1], '2')
            self.assertIn('--fork-session', engine.client.args)
            self.assertIn('--no-session-persistence', engine.client.args)
            prompt = engine.client.args[engine.client.args.index('--append-system-prompt') + 1]
            self.assertIn('Write all equations in LaTeX.', prompt)
            index = engine.client.args.index('--tools')
            self.assertEqual(engine.client.args[index + 1], '')

    def test_parent_session_reuse_is_rejected(self):
        class Client:
            def __init__(self, *args): self.closed = False
            def send(self, value): pass
            def next(self): return {'type': 'system', 'session_id': 'parent'}
            def close(self): self.closed = True
        with patch.object(b, 'JsonProcess', Client):
            engine = b.Claude({'session': 'parent', 'cwd': '/tmp'})
            with self.assertRaisesRegex(ValueError, 'separate session'):
                engine.ask('question', lambda text: None, threading.Event())
            self.assertTrue(engine.client.closed)

    def test_claude_ignores_background_results_and_matches_each_followup(self):
        class Client:
            def __init__(self, *args): self.events = []; self.prompts = []
            def send(self, event):
                self.prompts.append(event)
                self.events.extend([
                    {'type': 'result', 'session_id': 'child', 'subtype': 'success',
                     'origin': {'kind': 'task-notification'}, 'num_turns': 0, 'result': ''},
                    {'type': 'result', 'session_id': 'child', 'subtype': 'success',
                     'user_message_uuid': 'other-request', 'result': 'unrelated'},
                    {'type': 'stream_event', 'session_id': 'child', 'event': {
                        'type': 'content_block_delta', 'delta': {'type': 'text_delta', 'text': 'answer'}}},
                    {'type': 'result', 'session_id': 'child', 'subtype': 'success',
                     'origin': {'kind': 'human'}, 'user_message_uuid': event['uuid'],
                     'result': f'answer {len(self.prompts)}'},
                ])
            def next(self): return self.events.pop(0)
            def close(self): pass
        with patch.object(b, 'JsonProcess', Client):
            engine = b.Claude({'session': 'parent', 'cwd': '/tmp'})
            answers = []
            engine.ask('one', answers.append, threading.Event())
            self.assertEqual(answers, ['answer', 'answer 1'])
            self.assertEqual(engine.client.events, [])
            engine.ask('two', answers.append, threading.Event())
            self.assertEqual(answers[-1], 'answer 2')
            self.assertNotEqual(engine.client.prompts[0]['uuid'], engine.client.prompts[1]['uuid'])
            self.assertEqual(engine.client.prompts[0]['origin'], {'kind': 'human'})

    def test_claude_reports_a_genuinely_empty_answer(self):
        class Client:
            def __init__(self, *args): pass
            def send(self, event): self.request = event
            def next(self):
                return {'type': 'result', 'session_id': 'child', 'is_error': False,
                        'stop_reason': 'end_turn', 'result': '', 'user_message_uuid': self.request['uuid']}
            def close(self): pass
        with patch.object(b, 'JsonProcess', Client):
            engine = b.Claude({'session': 'parent', 'cwd': '/tmp'})
            with self.assertRaisesRegex(ValueError, 'no response text.*end_turn'):
                engine.ask('question', lambda text: None, threading.Event())

    def test_pi_forks_into_a_temporary_folder_without_tools(self):
        class Client:
            def __init__(self, args, *rest): self.args = args; self.events = []; self.sent = []; self.closed = False
            def send(self, event):
                self.sent.append(event)
                if event['type'] != 'prompt':
                    return
                answer = f"answer {len([e for e in self.sent if e['type'] == 'prompt'])}"
                self.events.extend([
                    {'id': event['id'], 'type': 'response', 'command': 'prompt', 'success': True, 'data': {'disposition': 'started'}},
                    {'type': 'message_start', 'message': {'role': 'user'}},
                    {'type': 'message_start', 'message': {'role': 'assistant'}},
                    {'type': 'message_update', 'assistantMessageEvent': {'type': 'text_delta', 'delta': answer}},
                    {'type': 'message_end', 'message': {'role': 'assistant', 'stopReason': 'stop', 'content': [{'type': 'text', 'text': answer}]}},
                    {'type': 'agent_settled', 'aborted': False}])
            def next(self): return self.events.pop(0)
            def close(self): self.closed = True
        with patch.object(b, 'JsonProcess', Client):
            engine = b.Pi({'session': 'parent', 'session_file': '/sessions/parent.jsonl', 'cwd': '/tmp'})
            folder = engine.folder
            answers = []
            engine.ask('one', answers.append, threading.Event())
            engine.ask('two', answers.append, threading.Event())
            self.assertEqual(answers[-1], 'answer 2')
            args = engine.client.args
            self.assertEqual(args[args.index('--fork') + 1], '/sessions/parent.jsonl')
            self.assertEqual(args[args.index('--session-dir') + 1], folder)
            self.assertIn('--no-tools', args)
            self.assertIn('--no-extensions', args)
            self.assertIn('Write all equations in LaTeX.', args[args.index('--append-system-prompt') + 1])
            engine.close()
            self.assertFalse(Path(folder).exists())

    def test_pi_reports_provider_errors_and_aborts(self):
        class Client:
            def __init__(self, *args): self.events = []
            def send(self, event):
                if event['type'] == 'prompt':
                    self.events.extend([
                        {'type': 'message_start', 'message': {'role': 'assistant'}},
                        {'type': 'message_end', 'message': {'role': 'assistant', 'stopReason': 'error', 'errorMessage': 'usage limit', 'content': []}},
                        {'type': 'agent_settled', 'aborted': self.abort}])
            def next(self): return self.events.pop(0)
            def close(self): pass
        with patch.object(b, 'JsonProcess', Client):
            engine = b.Pi({'session': 'parent', 'session_file': '/p.jsonl', 'cwd': '/tmp'})
            engine.client.abort = False
            with self.assertRaisesRegex(ValueError, 'usage limit'):
                engine.ask('question', lambda text: None, threading.Event())
            engine.client.abort = True
            cancelled = threading.Event()
            engine.ask('question', lambda text: None, cancelled)
            self.assertTrue(cancelled.is_set())
            engine.close()

    def test_pi_session_comes_from_the_terminal_process_tree(self):
        with tempfile.TemporaryDirectory() as folder:
            session = Path(folder) / 'sessions' / '2026_abc-1.jsonl'
            session.parent.mkdir()
            session.write_text('{}\n')
            registry = Path(folder) / 'herdr-side-chat'
            registry.mkdir()
            (registry / '200.json').write_text(json.dumps({'pid': 200, 'sessionId': 'abc-1', 'sessionFile': str(session)}))
            (registry / '999.json').write_text(json.dumps({'pid': 999, 'sessionId': 'other', 'sessionFile': str(session)}))
            with patch.dict(b.os.environ, {'PI_CODING_AGENT_DIR': folder}), \
                 patch.object(b, 'install_pi_extension', return_value=False), \
                 patch.object(b, 'process_tree', return_value=[100, 200]):
                self.assertEqual(b.pi_session(100), {'session': 'abc-1', 'session_file': str(session)})
            with patch.dict(b.os.environ, {'PI_CODING_AGENT_DIR': folder}), \
                 patch.object(b, 'install_pi_extension', return_value=True), \
                 patch.object(b, 'process_tree', return_value=[300]):
                with self.assertRaisesRegex(ValueError, '/reload'):
                    b.pi_session(300)

    def test_backend_failure_does_not_silently_restart_a_conversation(self):
        class Engine:
            def __init__(self, source): pass
            def ask(self, *args): raise ValueError('provider limit')
            def close(self): pass
        worker = b.Worker('abc')
        worker.source = {'engine': 'codex'}
        worker.messages = [{'role': 'user', 'text': 'question'}, {'role': 'assistant', 'text': ''}]
        worker.busy = True
        with patch.object(b, 'Codex', Engine): worker.answer('question')
        self.assertFalse(worker.busy)
        self.assertEqual(worker.phase, 'ended')
        self.assertIn('provider limit', worker.error)
        with self.assertRaisesRegex(ValueError, 'ended'):
            worker.dispatch({'op': 'ask', 'text': 'follow-up'})


if __name__ == '__main__':
    unittest.main()
