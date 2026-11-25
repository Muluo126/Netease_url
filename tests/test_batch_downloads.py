import json
import logging
import os
import tempfile
import threading
import time
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from batch_downloads import BatchBusyError, BatchDownloadManager
from music_downloader import DownloadException, DownloadResult


class FakeDownloader:
    """生成测试字节，不访问网易云或读取用户 Cookie。"""
    def __init__(self, download_dir):
        self.directory = Path(download_dir)
        self.directory.mkdir()

    def download_music_file(self, song_id, quality):
        if song_id == 2:
            raise DownloadException('无可用的下载链接')
        if song_id == 4:
            return DownloadResult(success=False, error_message='网络中断')
        path = self.directory / '同名歌曲.flac'
        path.write_bytes(b'' if song_id == 5 else f'audio:{song_id}:{quality}'.encode())
        return DownloadResult(success=True, file_path=str(path))


def wait_for_job(manager, job_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = manager.get(job_id)
        if job['state'] in ('completed', 'failed'):
            return job
        time.sleep(0.01)
    raise AssertionError('后台任务未在测试期限内结束')


class BatchDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manager = BatchDownloadManager(self.temp.name, downloader_factory=FakeDownloader)

    def test_zip_order_deduplication_and_partial_success(self):
        job = self.manager.create(['1', 2, '01', 3, 4, 5], 'hires', '../测试/歌单')
        final = wait_for_job(self.manager, job['id'])
        self.assertEqual((final['total'], final['completed'], final['succeeded'], final['failed']), (5, 5, 2, 3))
        self.assertEqual(final['state'], 'completed')
        path, filename = self.manager.get_archive(job['id'])
        self.assertNotIn('/', filename)
        with zipfile.ZipFile(path) as archive:
            manifest = json.loads(archive.read('下载清单.json'))
            self.assertEqual([song['id'] for song in manifest['songs']], [1, 2, 3, 4, 5])
            files = [entry for entry in manifest['songs'] if entry['success']]
            self.assertEqual(len({entry['filename'] for entry in files}), 2)
            self.assertEqual(archive.read(files[0]['filename']), b'audio:1:hires')
            self.assertEqual(archive.read(files[1]['filename']), b'audio:3:hires')
        self.assertEqual(list(path.parent.iterdir()), [path])
        self.assertFalse(any(key.startswith('_') for key in final))

    def test_all_failures_do_not_offer_zip(self):
        job = self.manager.create([2, 4, 5])
        final = wait_for_job(self.manager, job['id'])
        self.assertEqual(final['state'], 'failed')
        self.assertEqual(final['failed'], 3)
        self.assertIsNone(self.manager.get_archive(job['id']))

    def test_rejects_invalid_input_before_downloading(self):
        for ids in (None, [], '1,2', [True], [1.2], [-1], [0], ['1e2'], ['../1'], [1] * 501, ['9' * 21]):
            with self.subTest(ids=repr(ids)[:50]), self.assertRaises(ValueError):
                self.manager.create(ids)
        with self.assertRaises(ValueError):
            self.manager.create([1], 'invalid')
        with self.assertRaises(ValueError):
            self.manager.create([1], name=[])
        self.assertEqual(self.manager.jobs, {})

    def test_active_job_limit_and_pending_archive(self):
        release, started = threading.Event(), threading.Event()

        class BlockedDownloader(FakeDownloader):
            def download_music_file(self, song_id, quality):
                started.set()
                release.wait(5)
                return super().download_music_file(song_id, quality)

        manager = BatchDownloadManager(self.temp.name, max_active_jobs=1, downloader_factory=BlockedDownloader)
        job = manager.create([1])
        try:
            self.assertTrue(started.wait(2))
            self.assertIsNone(manager.get_archive(job['id']))
            with self.assertRaises(BatchBusyError):
                manager.create([3])
        finally:
            release.set()
            wait_for_job(manager, job['id'])

    def test_expiry_removes_files_and_status(self):
        job = self.manager.create([1])
        wait_for_job(self.manager, job['id'])
        path, _ = self.manager.get_archive(job['id'])
        self.manager.jobs[job['id']]['_finished_at'] = time.time() - 3601
        self.assertIsNone(self.manager.get(job['id']))
        self.assertFalse(path.parent.exists())

    def test_fatal_packaging_error_finishes_task(self):
        with patch('batch_downloads.zipfile.ZipFile', side_effect=OSError('disk full')):
            job = self.manager.create([1])
            final = wait_for_job(self.manager, job['id'])
        self.assertEqual(final['state'], 'failed')
        self.assertIsNone(self.manager.get_archive(job['id']))

    def test_expired_orphans_after_restart_are_removed(self):
        old = Path(self.temp.name) / 'batch-orphan'
        recent = Path(self.temp.name) / 'batch-recent'
        unrelated = Path(self.temp.name) / 'single-download'
        for directory in (old, recent, unrelated):
            directory.mkdir()
        os.utime(old, (time.time() - 3601, time.time() - 3601))
        self.assertIsNone(self.manager.get('unknown'))
        self.assertFalse(old.exists())
        self.assertTrue(recent.exists())
        self.assertTrue(unrelated.exists())


class BatchRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch('logging.FileHandler', return_value=logging.NullHandler()):
            import main
        cls.main = main

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manager = BatchDownloadManager(self.temp.name, downloader_factory=FakeDownloader)
        self.replace_manager = patch.object(self.main, 'batch_downloads', self.manager)
        self.replace_manager.start()
        self.addCleanup(self.replace_manager.stop)
        self.client = self.main.app.test_client()

    def test_create_poll_and_download_zip(self):
        response = self.client.post('/download/batch', json={'ids': [1, 2, 3], 'quality': 'lossless', 'name': '测试歌单'})
        self.assertEqual(response.status_code, 202)
        job_id = response.json['data']['id']
        wait_for_job(self.manager, job_id)
        status = self.client.get(f'/download/batch/{job_id}')
        self.assertEqual(status.json['data']['succeeded'], 2)
        response = self.client.get(f'/download/batch/{job_id}/file')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/zip')
        self.assertIn('attachment;', response.headers['Content-Disposition'])
        with zipfile.ZipFile(BytesIO(response.data)) as archive:
            self.assertEqual(len(archive.namelist()), 3)
        response.close()

    def test_bad_requests_unknown_jobs_and_failed_download(self):
        for payload in (None, [], {'ids': []}, {'ids': [1], 'quality': 'bad'}):
            self.assertEqual(self.client.post('/download/batch', json=payload).status_code, 400)
        self.assertEqual(self.client.get('/download/batch/unknown').status_code, 404)
        self.assertEqual(self.client.get('/download/batch/unknown/file').status_code, 404)
        job = self.manager.create([2])
        wait_for_job(self.manager, job['id'])
        self.assertEqual(self.client.get(f"/download/batch/{job['id']}/file").status_code, 409)

    def test_existing_page_and_single_download_still_available(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'/static/batch-downloads.js', response.data)
        response = self.client.get('/static/batch-downloads.js')
        self.assertEqual(response.status_code, 200)
        response.close()
        self.assertEqual(self.client.post('/Download', data={}).status_code, 400)


if __name__ == '__main__':
    unittest.main()
