import contextlib
import io
import json
import unittest
import urllib.error
from unittest.mock import MagicMock, patch
import upload


class BatteryTests(unittest.TestCase):
    def response(self, body):
        response=MagicMock()
        response.__enter__.return_value=response
        response.read.return_value=body
        return response

    def test_one_get_and_both_charge_states_including_zero(self):
        for percent, charging in [(73,True),(0,False),(100,None),(42.5,False)]:
            response=self.response(json.dumps({'battery':{'percent':percent,'charging':charging}}).encode())
            with patch('upload.urllib.request.urlopen',return_value=response) as get:
                battery=upload.read_battery('frame.local:8080')
                self.assertEqual(battery,dict(percent=percent,charging=charging))
                get.assert_called_once()
                self.assertEqual(get.call_args.args[0].full_url,'http://frame.local:8080/api/info')
                self.assertEqual(get.call_args.args[0].get_method(),'GET')
                self.assertEqual(get.call_args.kwargs['timeout'],2)
                self.assertIn(f'{percent:g}%',upload.battery_message(battery))
                self.assertEqual(' · charging' in upload.battery_message(battery),charging is True)

    def test_missing_invalid_or_unreachable_is_not_zero(self):
        bodies=[b'no JSON',b'[]',b'{}',b'{"battery":null}',b'x'*65537]
        for percent in [None,True,'80',-1,101,float('nan'),10**400]:
            bodies.append(json.dumps({'battery':{'percent':percent}}).encode())
        for body in bodies:
            with patch('upload.urllib.request.urlopen',return_value=self.response(body)) as get:
                self.assertIsNone(upload.read_battery('frame'))
                get.assert_called_once()
        for error in [TimeoutError(),urllib.error.URLError('sleeping'),urllib.error.HTTPError('http://frame',404,'Missing',{},io.BytesIO())]:
            with patch('upload.urllib.request.urlopen',side_effect=error) as get:
                self.assertIsNone(upload.read_battery('frame'))
                get.assert_called_once()

    def test_cli_only_reads_after_accepted_upload(self):
        for body,expected in [('{}',1),('{"status":"rendering"}',1),('{"error":"bad image"}',0),('{"success":false}',0)]:
            output=io.StringIO()
            with patch('sys.argv',['upload.py','frame','photo.bin']),patch('upload.upload_bin',return_value=(200,body)),patch('upload.read_battery',return_value=None) as battery,contextlib.redirect_stdout(output):
                upload.main()
            self.assertEqual(battery.call_count,expected)
            if expected:
                self.assertIn('Battery level unavailable',output.getvalue())


if __name__=='__main__':unittest.main()
