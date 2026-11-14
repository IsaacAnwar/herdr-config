"""Exercise session identity, fork isolation, and side-chat lifecycle without model calls."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('side_backend', Path(__file__).with_name('backend.py'))
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class SideChatTests(unittest.TestCase):
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
            with sqlite3.connect(db) as conn:
                conn.execute('CREATE TABLE threads (id TEXT, title TEXT, name TEXT, model TEXT, cwd TEXT, archived INTEGER)')
                conn.executemany('INSERT INTO threads VALUES (?,?,?,?,?,0)', [
                    ('first', 'Same task', 'Same task', 'model-a', folder),
                    ('second', 'Same task', 'Same task', 'model-b', folder),
                ])
            info = {'title': '⠹ Same task | project', 'status': {'app': 'codex'}, 'foreground': {'cwd': folder}}
            with patch.object(b, 'terminal_info', return_value=info), patch.dict(b.os.environ, {'CODEX_HOME': folder}):
                with self.assertRaisesRegex(ValueError, 'uniquely identify'):
                    b.resolve_source('t1')
                with sqlite3.connect(db) as conn:
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
