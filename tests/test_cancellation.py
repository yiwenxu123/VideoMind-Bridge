"""下载/转录/任务链路的取消与超时测试（批次B）

覆盖:
- yt-dlp 下载器: cancel_event 在进度钩子中断下载; timeout 触发 TIMEOUT 语义
- 转录服务: 片段边界取消; 按音频时间的真实进度
- TaskManager: 运行中取消 → CANCELLED 终态 + 令牌清理; 删除任务不复活写库
- CLI: --timeout 令牌透传到转录服务
"""

import asyncio
import sys
import threading
import time
from types import SimpleNamespace
from unittest import mock

import pytest
import yt_dlp

sys.path.insert(0, "src")


from src.api.task_manager import TaskManager
from src.models.task import TaskStatus
from src.services.downloaders.base import DownloadOptions
from src.services.downloaders.ytdlp import YtdlpDownloader
from src.services.task_database import TaskDatabase
from src.services.transcribe_service import TranscribeService, TranscriptResult
from src.utils.exceptions import OperationCancelledError

# ---------------- 下载层 ----------------


class _FakeYDL:
    """伪装 YoutubeDL: 反复调用 progress_hooks 直到钩子抛出或轮次耗尽"""

    def __init__(self, opts):
        self._opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download=True):
        hooks = self._opts.get("progress_hooks", [])
        for _ in range(100):
            for hook in hooks:
                hook({"status": "downloading", "total_bytes": 100, "downloaded_bytes": 50})
            time.sleep(0.02)
        return {"id": "x", "title": "t", "duration": 10}


def _make_options(tmp_path, **kwargs):
    return DownloadOptions(output_dir=tmp_path / "out", **kwargs)


def test_progress_hook_raises_downloadcancelled_when_event_set(tmp_path):
    d = YtdlpDownloader()
    ev = threading.Event()
    ev.set()
    with pytest.raises(yt_dlp.utils.DownloadCancelled):
        d._progress_hook({"status": "downloading"}, None, ev)


def test_progress_hook_ignores_event_when_none():
    d = YtdlpDownloader()
    # 不应抛异常: callback=None + event=None
    d._progress_hook({"status": "downloading"}, None, None)


def test_download_user_cancel_raises_cancelled(tmp_path):
    d = YtdlpDownloader()
    ev = threading.Event()
    threading.Timer(0.05, ev.set).start()
    url = "https://example.com/v"
    # 预置一个 .part 文件模拟断点续传现场
    temp_dir = tmp_path / "out" / ".temp" / YtdlpDownloader._url_key(url)
    temp_dir.mkdir(parents=True, exist_ok=True)
    part_file = temp_dir / "video.mp4.part"
    part_file.write_bytes(b"partial")
    with mock.patch("src.services.downloaders.ytdlp.yt_dlp.YoutubeDL", _FakeYDL):
        with pytest.raises(OperationCancelledError) as excinfo:
            d.download(url, _make_options(tmp_path, cancel_event=ev))
    assert excinfo.value.error_code == "CANCELLED"
    # 中断现场保留 (.part 不删): 同 URL 重建任务即可断点续传
    assert part_file.exists()


def test_download_timeout_raises_timeout(tmp_path):
    d = YtdlpDownloader()
    # 不传 cancel_event, 由 timeout 自建令牌; FakeYDL 循环 2s 远超 0.1s 超时
    with mock.patch("src.services.downloaders.ytdlp.yt_dlp.YoutubeDL", _FakeYDL):
        with pytest.raises(OperationCancelledError) as excinfo:
            d.download("https://example.com/v", _make_options(tmp_path, timeout=1))
    assert excinfo.value.error_code == "TIMEOUT"


def test_download_timeout_not_triggered_when_fast(tmp_path):
    """下载在超时前完成 → 正常返回结果"""
    d = YtdlpDownloader()

    class _FastYDL(_FakeYDL):
        def extract_info(self, url, download=True):
            return {"id": "x", "title": "t", "duration": 10}

    with mock.patch("src.services.downloaders.ytdlp.yt_dlp.YoutubeDL", _FastYDL):
        result = d.download("https://example.com/v", _make_options(tmp_path, timeout=30))
    assert result.success is True


def test_download_preset_cancelled_event_aborts_immediately(tmp_path):
    d = YtdlpDownloader()
    ev = threading.Event()
    ev.set()
    fake_cls = mock.MagicMock(side_effect=_FakeYDL)
    with mock.patch("src.services.downloaders.ytdlp.yt_dlp.YoutubeDL", fake_cls):
        with pytest.raises(OperationCancelledError):
            d.download("https://example.com/v", _make_options(tmp_path, cancel_event=ev))
    fake_cls.assert_not_called()  # 未进入 yt-dlp 即中止


def test_video_quality_maps_to_format_height(tmp_path):
    d = YtdlpDownloader()
    opts = _make_options(tmp_path, keep_video=True, video_quality="720p")
    built = d._build_options(opts, tmp_path, None)
    assert "bestvideo[ext=mp4][height<=720]" in built["format"]


def test_video_quality_worst_maps_to_worst(tmp_path):
    d = YtdlpDownloader()
    opts = _make_options(tmp_path, keep_video=True, video_quality="worst")
    built = d._build_options(opts, tmp_path, None)
    assert built["format"].startswith("worstvideo")


# ---------------- 转录层 ----------------


class _Seg:
    def __init__(self, start, end, text):
        self.start = start
        self.end = end
        self.text = text


def _fake_transcribe(segments, duration=10.0, language="zh"):
    info = SimpleNamespace(language=language, language_probability=0.95, duration=duration)

    class _Model:
        def __init__(self, segs):
            self._segs = segs

        def transcribe(self, path, **kwargs):
            return iter(self._segs), info

    return _Model(list(segments)), info


def test_transcribe_cancel_between_segments(tmp_path):
    service = TranscribeService("tiny")
    ev = threading.Event()
    model, _ = _fake_transcribe([_Seg(0, 2, "第一句"), _Seg(2, 4, "第二句"), _Seg(4, 6, "第三句")])
    service._model = model

    def gen():
        yield model._segs[0]
        ev.set()  # 第一段完成后置位取消
        yield model._segs[1]
        yield model._segs[2]

    service._model.transcribe = mock.Mock(return_value=(gen(), SimpleNamespace(
        language="zh", language_probability=0.95, duration=6.0)))

    audio = tmp_path / "a.wav"
    audio.write_text("fake")
    with pytest.raises(OperationCancelledError):
        service.transcribe(audio, cancel_event=ev)


def test_transcribe_preset_cancelled_event(tmp_path):
    service = TranscribeService("tiny")
    ev = threading.Event()
    ev.set()
    model, _ = _fake_transcribe([_Seg(0, 2, "a")])
    service._model = model
    audio = tmp_path / "a.wav"
    audio.write_text("fake")
    with pytest.raises(OperationCancelledError):
        service.transcribe(audio, cancel_event=ev)


def test_transcribe_progress_is_time_based(tmp_path):
    """进度按音频时间推进且单调递增 (修复假进度: 旧实现一次性 list 后瞬时跑完)"""
    service = TranscribeService("tiny")
    model, _ = _fake_transcribe([
        _Seg(0, 2, "a"), _Seg(2, 4, "b"), _Seg(4, 6, "c"),
    ], duration=6.0)
    service._model = model

    values = []
    audio = tmp_path / "a.wav"
    audio.write_text("fake")
    result = service.transcribe(
        audio,
        progress_callback=lambda msg, pct: values.append(pct),
    )

    assert len(result.segments) == 3
    per_segment = [p for p in values if 20 < p < 100]
    assert len(per_segment) == 3
    assert per_segment == sorted(per_segment)  # 单调递增
    assert per_segment[-1] > 90


# ---------------- TaskManager 层 ----------------


def _make_manager(tmp_path):
    with mock.patch(
        "src.api.task_manager.get_task_database",
        return_value=TaskDatabase(db_path=tmp_path / "tasks.db"),
    ):
        mgr = TaskManager(output_dir=tmp_path / "out")
    return mgr


def _blocking_download(cancelled_flag: dict):
    """模拟慢下载: 阻塞直到 cancel_event 置位, 然后抛取消异常"""

    def fake_download(url, **kwargs):
        ev = kwargs.get("cancel_event")
        cancelled_flag["event"] = ev
        deadline = time.time() + 5
        while ev is None or not ev.is_set():
            if time.time() > deadline:
                raise AssertionError("cancel_event 未在期限内置位")
            time.sleep(0.01)
        raise OperationCancelledError("下载已取消")

    return fake_download


async def _wait_until(predicate, timeout_s=3.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return False


async def test_task_manager_cancel_marks_cancelled_and_cleans_event(tmp_path):
    mgr = _make_manager(tmp_path)
    flag = {}
    mgr._download_service = mock.Mock()
    mgr._download_service.download.side_effect = _blocking_download(flag)

    await mgr.start()
    try:
        task = await mgr.create_task("https://example.com/v")
        assert await _wait_until(
            lambda: mgr._tasks[task.id].status == TaskStatus.DOWNLOADING
        )
        assert await mgr.cancel_task(task.id) is True

        assert await _wait_until(
            lambda: mgr._tasks[task.id].status == TaskStatus.CANCELLED
            and "已取消" in (mgr._tasks[task.id].current_step or "")
            and task.id not in mgr._cancel_events
        )
        assert flag["event"].is_set()
        # 取消不是失败
        assert mgr._tasks[task.id].status != TaskStatus.FAILED
    finally:
        await mgr.stop()


async def test_task_manager_delete_tombstone_prevents_db_write(tmp_path):
    db = TaskDatabase(db_path=tmp_path / "tasks.db")
    save_calls: list = []
    real_save = db.save_task

    def _spy_save(task_history):
        save_calls.append(task_history.id)
        return real_save(task_history)

    db.save_task = _spy_save
    with mock.patch("src.api.task_manager.get_task_database", return_value=db):
        mgr = TaskManager(output_dir=tmp_path / "out")
    flag = {}
    mgr._download_service = mock.Mock()
    mgr._download_service.download.side_effect = _blocking_download(flag)

    await mgr.start()
    try:
        task = await mgr.create_task("https://example.com/v")
        assert await _wait_until(
            lambda: mgr._tasks[task.id].status == TaskStatus.DOWNLOADING
        )
        assert await mgr.delete_task(task.id) is True
        assert task.id in mgr._deleted_tasks
        saves_at_delete = len(save_calls)

        # executor 收尾后不得再写库 (旧 bug: 删除的任务被复活写回)
        assert await _wait_until(lambda: task.id not in mgr._cancel_events)
        await asyncio.sleep(0.05)
        assert len(save_calls) == saves_at_delete
    finally:
        await mgr.stop()


async def test_task_manager_stop_sets_all_events(tmp_path):
    mgr = _make_manager(tmp_path)
    flag = {}
    mgr._download_service = mock.Mock()
    mgr._download_service.download.side_effect = _blocking_download(flag)

    await mgr.start()
    task = await mgr.create_task("https://example.com/v")
    assert await _wait_until(
        lambda: mgr._tasks[task.id].status == TaskStatus.DOWNLOADING
    )
    await mgr.stop()
    assert flag["event"].is_set()


# ---------------- CLI 层 ----------------


def test_cli_timeout_token_passed_to_transcribe(tmp_path, monkeypatch):
    from src import cli as cli_module

    media = tmp_path / "a.mp3"
    media.write_text("fake")

    captured = {}

    class _FakeTS:
        def __init__(self, model_size="small"):
            pass

        def transcribe(self, path, language="zh", progress_callback=None, cancel_event=None):
            captured["cancel_event"] = cancel_event
            return TranscriptResult(
                segments=[], language="zh", language_probability=1.0,
                full_text="", formatted_text="",
            )

    monkeypatch.setattr(cli_module, "TranscribeService", _FakeTS)

    args = cli_module.parse_args([
        str(media),
        "--mode", "transcribe",
        "--output-dir", str(tmp_path / "out"),
        "--json",
        "--timeout", "600",
    ])
    rc = cli_module._process_single(args, time.time())

    assert rc == 0
    assert isinstance(captured["cancel_event"], threading.Event)
    assert not captured["cancel_event"].is_set()


def test_cli_timeout_fires_and_exits_nonzero(tmp_path, monkeypatch, capsys):
    """--timeout 到点触发令牌, 阻塞中的下载被中断, 退出码非 0"""
    import time as _time

    from src import cli as cli_module
    from src.utils.exceptions import OperationCancelledError

    class _BlockingDL:
        def __init__(self, output_dir):
            pass

        def download(self, url, **kwargs):
            ev = kwargs.get("cancel_event")
            # --timeout 设的是 1 秒，这里给 15 秒等待窗口。
            # 原为 5 秒：整仓并行跑测试时线程调度会被拖慢，曾出现假红
            # （单独跑必过，全量跑偶发失败）。放宽窗口只降低误报，不削弱断言本身。
            deadline = _time.time() + 15
            while ev is None or not ev.is_set():
                if _time.time() > deadline:
                    raise AssertionError("CLI --timeout 令牌未在期限内触发")
                _time.sleep(0.02)
            raise OperationCancelledError("下载超时", error_code="TIMEOUT")

    monkeypatch.setattr(cli_module, "DownloadService", _BlockingDL)

    args = cli_module.parse_args([
        "https://example.com/video",
        "--mode", "download",
        "--output-dir", str(tmp_path / "out"),
        "--json",
        "--timeout", "1",
    ])
    start = _time.time()
    rc = cli_module._process_single(args, start)

    assert rc == 1
    assert _time.time() - start < 4  # 在超时后 promptly 退出, 而非等满阻塞期
    output = capsys.readouterr().out
    assert '"success": false' in output
    assert "TIMEOUT" in output
