"""Run independent function calls in threads or spawned worker processes."""

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from multiprocessing import get_context
from dataclasses import dataclass, field
from threading import Lock
from time import perf_counter
from typing import Any, Callable, Iterable, Mapping, Optional, Tuple


@dataclass(frozen=True)
class FunctionCall:
    """Arguments for one function call."""

    args: Tuple[Any, ...] = ()
    kwargs: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_item(cls, item: Any) -> "FunctionCall":
        """Normalize a call description.

        A FunctionCall is used unchanged, a tuple becomes positional arguments,
        a mapping becomes keyword arguments, and anything else becomes one
        positional argument.
        """
        if isinstance(item, cls):
            return item
        if isinstance(item, tuple):
            return cls(args=item)
        if isinstance(item, Mapping):
            return cls(kwargs=item)
        return cls(args=(item,))


@dataclass(frozen=True)
class FunctionResult:
    """Outcome of one call, associated with its original arguments."""

    index: int
    call: FunctionCall
    value: Any = None
    exception: Optional[Exception] = None
    duration: float = 0.0

    @property
    def succeeded(self) -> bool:
        return self.exception is None

    def result(self) -> Any:
        """Return the value, or re-raise the exception raised by the function."""
        if self.exception is not None:
            raise self.exception
        return self.value


def _invoke(function, index, call):
    """Top-level worker entry point: never pickle the runner or its thread lock."""
    started = perf_counter()
    try:
        return FunctionResult(index, call, value=function(*call.args, **dict(call.kwargs)),
                              duration=perf_counter() - started)
    except Exception as error:
        return FunctionResult(index, call, exception=error,
                              duration=perf_counter() - started)


class ThreadedFunctionRunner:
    """Run independent calls using a thread or process pool.

    Results are returned in input order. Exceptions are captured in their
    FunctionResult instead of stopping the other calls.

    backend="process" uses spawn, including on macOS. Functions must be importable
    module-level callables, and arguments/results/exceptions must be picklable.
    Call run() under an if __name__ == "__main__" guard in executable scripts.
    worker_count is the neutral name; thread_count remains supported for callers.
    Progress and logging stay in the parent process.
    """

    def __init__(
        self,
        function: Callable[..., Any],
        calls: Iterable[Any] = (),
        thread_count: int = 1,
        verbosity: int = 0,
        show_progress: bool = False,
        progress_description: str = "Processing",
        progress_unit: str = "item",
        *,
        backend: str = "thread",
        worker_count: Optional[int] = None,
    ) -> None:
        if not callable(function):
            raise TypeError("function must be callable")
        self.function = function
        self.calls = calls
        if backend not in {"thread", "process"}:
            raise ValueError("backend must be 'thread' or 'process'")
        self.backend = backend
        self.thread_count = thread_count if worker_count is None else worker_count
        self.verbosity = verbosity
        self.show_progress = show_progress
        self.progress_description = progress_description
        self.progress_unit = progress_unit
        self._print_lock = Lock()

    @property
    def thread_count(self) -> int:
        return self._thread_count

    @thread_count.setter
    def thread_count(self, value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("thread_count must be a positive integer")
        self._thread_count = value

    def _log(self, message: str, level: int = 1) -> None:
        if self.verbosity >= level:
            with self._print_lock:
                print(message)

    def run(self, calls: Optional[Iterable[Any]] = None):
        """Execute calls and return a list of FunctionResult in input order."""
        selected_calls = self.calls if calls is None else calls
        normalized = [FunctionCall.from_item(item) for item in selected_calls]
        if not normalized:
            return []

        self._log(
            f"Running {len(normalized)} call(s) with {self.thread_count} {self.backend} worker(s)",
            level=1,
        )
        progress = self._make_progress(len(normalized))
        ordered_results = [None] * len(normalized)

        try:
            executor_class = ProcessPoolExecutor if self.backend == "process" else ThreadPoolExecutor
            options = {"max_workers": min(self.thread_count, len(normalized))}
            if self.backend == "process":
                options["mp_context"] = get_context("spawn")
            with executor_class(**options) as executor:
                futures = {
                    executor.submit(_invoke, self.function, index, call): index
                    for index, call in enumerate(normalized)
                }
                for future in as_completed(futures):
                    index = futures[future]
                    try:
                        result = future.result()
                    except Exception as error:
                        # Includes serialization errors and abruptly terminated workers.
                        result = FunctionResult(index, normalized[index], exception=error)
                    ordered_results[index] = result
                    if result.succeeded:
                        self._log(f"Completed call {index + 1} in {result.duration:.2f}s", level=2)
                    else:
                        self._log(f"Call {index + 1} failed: {result.exception}", level=1)
                    if progress is not None:
                        progress.update(1)
        finally:
            if progress is not None:
                progress.close()

        failures = sum(not result.succeeded for result in ordered_results)
        self._log(
            f"Finished {len(ordered_results)} call(s), {failures} failure(s)",
            level=1,
        )
        return ordered_results

    def _make_progress(self, total: int):
        if not self.show_progress:
            return None
        try:
            from tqdm import tqdm
        except ImportError as error:
            raise RuntimeError(
                "Progress display requires the optional 'tqdm' package"
            ) from error
        return tqdm(total=total, desc=self.progress_description, unit=self.progress_unit)
