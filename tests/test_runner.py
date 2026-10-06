import os
import time
import unittest
from unittest.mock import patch, MagicMock

from threaded_function_runner import FunctionCall, ThreadedFunctionRunner


def work(value, delay=0):
    time.sleep(delay)
    if value < 0:
        raise ValueError('negative value')
    return value * 2, os.getpid()


def return_unpicklable():
    return lambda: None


class RunnerTests(unittest.TestCase):
    def test_threads_and_processes_preserve_order_and_failures(self):
        for backend in ('thread', 'process'):
            with self.subTest(backend=backend):
                progress = MagicMock()
                runner = ThreadedFunctionRunner(work,
                    [FunctionCall((3,), {'delay': 0.1}), {'value': -1}, (2,), 1],
                    backend=backend, worker_count=2, show_progress=True)
                with patch.object(runner, '_make_progress', return_value=progress):
                    results = runner.run()
                self.assertEqual([r.index for r in results], [0, 1, 2, 3])
                self.assertEqual([r.value[0] for r in results if r.succeeded], [6, 4, 2])
                with self.assertRaisesRegex(ValueError, 'negative value'):
                    results[1].result()
                pids = {r.value[1] for r in results if r.succeeded}
                if backend == 'process':
                    self.assertNotIn(os.getpid(), pids)
                    self.assertEqual(len(pids), 2)
                else:
                    self.assertEqual(pids, {os.getpid()})
                self.assertEqual(progress.update.call_count, 4)
                progress.close.assert_called_once()

    def test_serialization_failure_is_reported_per_call(self):
        runner = ThreadedFunctionRunner(work, [1, lambda: 1, 2], backend='process', worker_count=2)
        results = runner.run()
        self.assertTrue(results[0].succeeded)
        self.assertFalse(results[1].succeeded)
        self.assertTrue(results[2].succeeded)
        result = ThreadedFunctionRunner(return_unpicklable, [()], backend='process').run()[0]
        self.assertFalse(result.succeeded)

    def test_legacy_thread_interface_and_empty_calls(self):
        runner = ThreadedFunctionRunner(lambda value: value + 1, thread_count=2)
        self.assertEqual(runner.run(), [])
        self.assertEqual(runner.run([1])[0].result(), 2)

    def test_invalid_configuration(self):
        for count in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                ThreadedFunctionRunner(work, worker_count=count)
        with self.assertRaises(ValueError):
            ThreadedFunctionRunner(work, backend='invalid')


if __name__ == '__main__':
    unittest.main()
