## 问题分析

从测试可以看出：
1. **单独测试 DownloadService 正常** - 视频和音频都能下载
2. **GUI 中失败** - 出现 HTTP 416 错误

两者的区别：
1. **输出目录** - 测试使用临时目录，GUI 使用配置目录
2. **回调函数** - 测试使用简单打印，GUI 使用 Qt 信号发射
3. **线程环境** - GUI 在 QThread 中运行

## 根本原因推测

HTTP 416 错误可能是由于：
1. **线程竞争** - yt_dlp 回调中发射 Qt 信号可能导致线程问题
2. **网络状态** - GUI 运行时网络状态不同
3. **并发问题** - 可能有其他任务在运行

## 解决方案

### 方案 1: 移除回调中的信号发射（测试）
暂时移除 `download_progress` 回调中的信号发射，看看是否能正常下载。

### 方案 2: 使用队列缓冲进度更新
将进度更新放入队列，由主线程统一处理。

### 方案 3: 使用 Qt 的 invokeMethod
确保信号从正确的线程发射。

## 实施计划

先实施方案 1 进行测试：
1. 修改 `_process_download_only`，暂时禁用进度回调中的信号发射
2. 测试是否能正常下载
3. 如果能正常下载，说明是线程问题，再实施方案 2 或 3

## 代码修改

```python
def download_progress(status: str, percent: float):
    # 暂时禁用信号发射，测试是否是线程问题
    if self._check_cancelled():
        self._should_stop = True
        return
    # self.progress_updated.emit(task_id, int(percent), status)  # 暂时禁用
```

## 预期结果
- 如果禁用信号后能正常下载，说明是 Qt 信号线程问题
- 如果仍然失败，说明是其他问题（网络、yt_dlp 配置等）