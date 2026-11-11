"""Bonus: giới hạn retry 429 và liên kết incident khác provider (không gọi LLM API)."""
import json
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent import run_agent, _linked_incidents
from bonus.tools import BonusTools
from bonus.test_agent import ScriptedProvider, call, final


class RetryLimitTests(unittest.TestCase):
    def test_persistent_429_is_blocked_after_three_calls(self):
        t = BonusTools(scenario='rate_limit_always')
        p = ScriptedProvider([call(str(i), 'get_vercel_status', {}) for i in range(5)] + [final('Vercel: chưa biết')])
        result = run_agent('Kiểm tra Vercel', p, t, max_steps=8)
        self.assertEqual(result['status'], 'completed')
        executed = [x for x in result['trace'] if x['event'] == 'tool' and x['name'] == 'get_vercel_status']
        self.assertEqual(len(executed), 3)
        self.assertEqual(sum(x['event'] == 'retry_limit_blocked' for x in result['trace']), 2)
        self.assertEqual(json.loads(p.histories[4][-1]['content'])['error'], 'RETRY_LIMIT_REACHED')

    def test_single_429_then_success_is_not_blocked(self):
        t = BonusTools(scenario='rate_limit_once')
        p = ScriptedProvider([call('a', 'get_vercel_status', {}), call('b', 'get_vercel_status', {}), final()])
        result = run_agent('Kiểm tra', p, t, max_steps=5)
        self.assertEqual(json.loads(p.histories[2][-1]['content'])['provider'], 'vercel')
        self.assertFalse(any(x['event'] == 'retry_limit_blocked' for x in result['trace']))


class CrossProviderLinkTests(unittest.TestCase):
    def test_link_provider_comes_from_url_host(self):
        result = {'id': 'sps6n39gm4sg', 'updates': [
            {'body': 'See https://www.githubstatus.com/incidents/93njd414rpbx for details.'},
            {'body': 'Unknown host https://example.com/incidents/abcdefghijkl ignored.'}]}
        self.assertEqual(_linked_incidents(result), [('93njd414rpbx', 'github')])


if __name__ == '__main__':
    unittest.main()
