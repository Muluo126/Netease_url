"""后台批量下载任务：逐首落盘、打包 ZIP，并保留失败清单。"""

import copy
import json
import logging
import re
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from pathlib import Path

from music_downloader import MusicDownloader, QualityLevel


class BatchBusyError(Exception):
    """当前批量任务已达到并发上限。"""


class BatchDownloadManager:
    MAX_TRACKS = 500

    def __init__(self, download_dir, max_active_jobs=2, retention_seconds=3600,
                 downloader_factory=MusicDownloader):
        self.root = Path(download_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_active_jobs = max_active_jobs
        self.retention_seconds = retention_seconds
        self.downloader_factory = downloader_factory
        self.jobs = {}
        self.lock = threading.Lock()
        self.logger = logging.getLogger('music_api')

    def _cleanup(self):
        """在持锁状态清理过期的任务和文件。"""
        now = time.time()
        for job_id, job in list(self.jobs.items()):
            if job.get('_finished_at') and now - job['_finished_at'] > self.retention_seconds:
                shutil.rmtree(job['_directory'], ignore_errors=True)
                del self.jobs[job_id]
        # 服务重启会丢失内存状态，过期的遗留目录也需要回收。
        known_directories = {job['_directory'] for job in self.jobs.values()}
        for directory in self.root.glob('batch-*'):
            if directory not in known_directories and directory.is_dir():
                if now - directory.stat().st_mtime > self.retention_seconds:
                    shutil.rmtree(directory, ignore_errors=True)

    @staticmethod
    def _snapshot(job):
        return copy.deepcopy({key: value for key, value in job.items() if not key.startswith('_')})

    def create(self, ids, quality='lossless', name='音乐批量下载'):
        if not isinstance(ids, list) or not 1 <= len(ids) <= self.MAX_TRACKS:
            raise ValueError(f'ids 必须是包含 1 至 {self.MAX_TRACKS} 个歌曲 ID 的数组')
        normalized = []
        for song_id in ids:
            if isinstance(song_id, bool) or not re.fullmatch(r'[0-9]{1,20}', str(song_id)) or int(song_id) <= 0:
                raise ValueError('歌曲 ID 必须是正整数')
            normalized.append(int(song_id))
        normalized = list(dict.fromkeys(normalized))
        if quality not in [level.value for level in QualityLevel]:
            raise ValueError('无效的音质参数')
        if not isinstance(name, str):
            raise ValueError('name 必须是字符串')
        safe_name = re.sub(r'[\x00-\x1f<>:"/\\|?*]', '_', name).strip(' .')[:80] or '音乐批量下载'

        with self.lock:
            self._cleanup()
            active = sum(job['state'] in ('queued', 'running') for job in self.jobs.values())
            if active >= self.max_active_jobs:
                raise BatchBusyError('批量下载任务繁忙，请稍后重试')
            job_id = uuid.uuid4().hex
            directory = Path(tempfile.mkdtemp(prefix='batch-', dir=self.root))
            job = {
                'id': job_id, 'state': 'queued', 'quality': quality,
                'total': len(normalized), 'completed': 0, 'succeeded': 0, 'failed': 0,
                'current_id': None, 'failures': [], 'message': '等待下载',
                'filename': f'{safe_name} [{quality}].zip',
                '_directory': directory, '_archive': directory / 'music.zip',
            }
            self.jobs[job_id] = job
            try:
                threading.Thread(target=self._run, args=(job_id, normalized), daemon=True).start()
            except Exception:
                del self.jobs[job_id]
                shutil.rmtree(directory, ignore_errors=True)
                raise
            return self._snapshot(job)

    def get(self, job_id):
        with self.lock:
            self._cleanup()
            job = self.jobs.get(job_id)
            return self._snapshot(job) if job else None

    def get_archive(self, job_id):
        with self.lock:
            self._cleanup()
            job = self.jobs.get(job_id)
            if job and job['state'] == 'completed' and job['_archive'].is_file():
                return job['_archive'], job['filename']
            return None

    def _update(self, job_id, **values):
        with self.lock:
            self.jobs[job_id].update(values)

    def _run(self, job_id, ids):
        job = self.jobs[job_id]
        directory = job['_directory']
        results = []
        succeeded = 0
        failures = []
        try:
            self._update(job_id, state='running', message='正在下载')
            # 音频已压缩，ZIP_STORED 避免再次压缩耗费 CPU；始终使用磁盘文件。
            with zipfile.ZipFile(job['_archive'], 'w', compression=zipfile.ZIP_STORED) as archive:
                for index, song_id in enumerate(ids, 1):
                    song_dir = directory / str(song_id)
                    self._update(job_id, current_id=song_id)
                    try:
                        # 每首独立目录，避免同名歌曲、不同音质和其他任务的缓存混用。
                        downloader = self.downloader_factory(download_dir=str(song_dir))
                        result = downloader.download_music_file(song_id, job['quality'])
                        if not result.success or not result.file_path:
                            raise RuntimeError(result.error_message or '下载失败')
                        file_path = Path(result.file_path)
                        if not file_path.is_file() or file_path.stat().st_size == 0:
                            raise RuntimeError('下载文件为空或不存在')
                        filename = f'{index:03d} - {song_id} - {file_path.name}'
                        archive.write(file_path, arcname=filename)
                        results.append({'id': song_id, 'success': True, 'filename': filename})
                        succeeded += 1
                    except Exception as exc:
                        self.logger.warning('批量任务 %s 歌曲 %s 下载失败: %s', job_id, song_id, exc)
                        failure = {'id': song_id, 'message': str(exc)}
                        failures.append(failure)
                        results.append({'id': song_id, 'success': False, 'message': str(exc)})
                    finally:
                        shutil.rmtree(song_dir, ignore_errors=True)
                    self._update(job_id, completed=index, succeeded=succeeded,
                                 failed=len(failures), failures=list(failures))
                manifest = {'quality': job['quality'], 'total': len(ids),
                            'succeeded': succeeded, 'failed': len(failures), 'songs': results}
                archive.writestr('下载清单.json', json.dumps(manifest, ensure_ascii=False, indent=2))
            if not succeeded:
                job['_archive'].unlink(missing_ok=True)
            self._update(job_id, state='completed' if succeeded else 'failed', current_id=None,
                         message='打包完成' if succeeded else '所有歌曲下载失败，请检查 Cookie、版权或音质',
                         _finished_at=time.time())
        except Exception:
            self.logger.exception('批量任务 %s 失败', job_id)
            job['_archive'].unlink(missing_ok=True)
            self._update(job_id, state='failed', current_id=None,
                         message='批量下载失败，请检查服务器日志和可用磁盘空间', _finished_at=time.time())
