"""Tests cho cải tiến Bài 4: lượt cuối không gửi tools và yêu cầu model trả lời (case A1)."""
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent import run_agent
from status_tools import StatusTools
from test_lab import FakeProvider, tool_call, final


class RecordingProvider(FakeProvider):
    def __init__(self, responses):
        super().__init__(responses)
        self.schemas = []
    def complete(self, messages, schemas):
        self.schemas.append(schemas)
        return super().complete(messages, schemas)


class BudgetTests(unittest.TestCase):
    def test_last_step_has_no_tools_and_asks_for_answer_with_sources(self):
        url = 'https://stspg.io/pjgptg3cfc6n'
        fake = RecordingProvider([tool_call('1', 'get_status', '{"provider":"github"}'),
                                  tool_call('2', 'get_incident_details', '{"provider":"github","incident_id":"xr3myzj7ms51"}'),
                                  final('Đã xử lý. ' + url)])
        result = run_agent('x', fake, StatusTools(), max_steps=3)
        self.assertEqual(result['status'], 'completed')
        self.assertTrue(fake.schemas[0] and fake.schemas[1])
        self.assertEqual(fake.schemas[2], [])
        last_note = fake.histories[2][-1]
        self.assertEqual(last_note['role'], 'user')
        self.assertIn(url, last_note['content'])
        self.assertTrue(any(x['event'] == 'budget_final_step' for x in result['trace']))

    def test_single_step_budget_keeps_tools(self):
        fake = RecordingProvider([final()])
        self.assertEqual(run_agent('x', fake, StatusTools(), max_steps=1)['status'], 'completed')
        self.assertTrue(fake.schemas[0])

    def test_system_prompt_states_budget(self):
        fake = RecordingProvider([final()])
        run_agent('x', fake, StatusTools(), max_steps=8)
        self.assertIn('tối đa 8 lượt', fake.histories[0][0]['content'])


class LinkedIncidentAndErrorNoteTests(unittest.TestCase):
    def test_unread_linked_incident_is_requested_once(self):
        # h02n9572mx9y trỏ sang xr3myzj7ms51 trong update "resolved".
        fake = RecordingProvider([tool_call('1', 'get_incident_details', '{"provider":"github","incident_id":"h02n9572mx9y"}'),
                                  final('Xong https://stspg.io/7pwv28hvkmz8'),
                                  tool_call('2', 'get_incident_details', '{"provider":"github","incident_id":"xr3myzj7ms51"}'),
                                  final('Xong https://stspg.io/7pwv28hvkmz8 https://stspg.io/pjgptg3cfc6n')])
        result = run_agent('x', fake, StatusTools(), max_steps=6)
        self.assertEqual(result['status'], 'completed')
        events = [x for x in result['trace'] if x['event'] == 'validation_unread_linked_incident']
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['incident_ids'], ['xr3myzj7ms51'])
        self.assertIn('xr3myzj7ms51', fake.histories[2][-1]['content'])

    def test_linked_check_skipped_on_last_step(self):
        fake = RecordingProvider([tool_call('1', 'get_incident_details', '{"provider":"github","incident_id":"h02n9572mx9y"}'),
                                  final('Xong https://stspg.io/7pwv28hvkmz8')])
        self.assertEqual(run_agent('x', fake, StatusTools(), max_steps=2)['status'], 'completed')

    def test_failed_tool_result_carries_note(self):
        fake = RecordingProvider([tool_call('1', 'get_status', '{"provider":"github"}'), final('Chưa kiểm tra được')])
        result = run_agent('x', fake, StatusTools(fail=True), max_steps=3)
        self.assertEqual(result['status'], 'completed')
        sent = json.loads(fake.histories[1][-1]['content'])
        self.assertEqual(sent['error'], 'TimeoutError')
        self.assertIn('operational', sent['agent_note'])


if __name__ == '__main__':
    unittest.main()
