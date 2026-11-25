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
from types import SimpleNamespace
from unittest.mock import patch

from batch_downloads import BatchBusyError, BatchDownloadManager
from music_downloader import DownloadException, DownloadResult, MusicDownloader, MusicInfo


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
            self.assertEqual([entry['filename'] for entry in files], ['同名歌曲.flac', '同名歌曲 (2).flac'])
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

    def test_zip_uses_metadata_title_and_preserves_extension_without_artist_or_id(self):
        names = {1: '歌曲 - 副标题', 3: '歌曲 - 副标题', 6: '歌曲 - 副标题 (2)',
                 7: '歌曲 - 副标题', 8: '歌曲 - 副标题'}

        class NamedDownloader(FakeDownloader):
            def download_music_file(self, song_id, quality):
                result = super().download_music_file(song_id, quality)
                if song_id == 8:
                    renamed = Path(result.file_path).with_suffix('.mp3')
                    Path(result.file_path).rename(renamed)
                    result.file_path = str(renamed)
                result.music_info = SimpleNamespace(name=names[song_id], quality=quality)
                return result

        manager = BatchDownloadManager(self.temp.name, downloader_factory=NamedDownloader)
        job = manager.create([1, 3, 6, 7, 8], 'lossless')
        self.assertEqual(wait_for_job(manager, job['id'])['succeeded'], 5)
        path, _ = manager.get_archive(job['id'])
        with zipfile.ZipFile(path) as archive:
            expected = ['歌曲 - 副标题.flac', '歌曲 - 副标题 (2).flac',
                        '歌曲 - 副标题 (2) (2).flac', '歌曲 - 副标题 (3).flac', '歌曲 - 副标题.mp3']
            manifest = json.loads(archive.read('下载清单.json'))
            self.assertEqual([song['filename'] for song in manifest['songs']], expected)
            self.assertEqual(archive.namelist(), expected + ['下载清单.json'])
            for song in manifest['songs']:
                self.assertEqual(archive.read(song['filename']), f"audio:{song['id']}:lossless".encode())

    def test_archive_names_are_safe_and_case_insensitive_duplicates_are_distinct(self):
        used_names = set()
        for title, expected in [('Track', 'Track.flac'), ('track', 'track (2).flac'),
                                ('../曲名:/\\?*\x00', '_曲名______.flac'),
                                ('CON', '_CON.flac'), (' . ', '未知歌曲.flac')]:
            with self.subTest(title=title):
                filename = self.manager._archive_filename(title, '.flac', used_names)
                self.assertEqual(filename, expected)
                used_names.add(filename.casefold())

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


class QualityFallbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.calls = []
        self.responses = {}
        test = self

        class ScriptedDownloader(FakeDownloader):
            def download_music_file(self, song_id, quality):
                test.calls.append((song_id, quality))
                path = self.directory / '歌曲.mp3'
                test.assertFalse(path.exists(), '下一音质不得复用失败文件')
                response = test.responses.get((song_id, quality), quality)
                if isinstance(response, Exception):
                    path.write_bytes(b'incomplete')
                    raise response
                if response is False:
                    path.write_bytes(b'incomplete')
                    return DownloadResult(success=False, error_message='读取超时')
                if response == 'empty':
                    path.touch()
                else:
                    path.write_bytes(f'{song_id}:{response}'.encode())
                return DownloadResult(success=True, file_path=str(path),
                                      music_info=SimpleNamespace(quality=response))

        self.manager = BatchDownloadManager(self.temp.name, downloader_factory=ScriptedDownloader)

    def manifest(self, job_id):
        path, _ = self.manager.get_archive(job_id)
        with zipfile.ZipFile(path) as archive:
            result = json.loads(archive.read('下载清单.json'))
            for song in result['songs']:
                if song['success']:
                    self.assertEqual(archive.read(song['filename']), f"{song['id']}:{song['quality']}".encode())
        self.assertEqual(list(path.parent.iterdir()), [path])
        return result

    def test_lossless_timeout_falls_back_once_and_next_song_keeps_original_quality(self):
        self.responses[(1, 'lossless')] = False
        job = self.manager.create([1, 3], 'lossless')
        final = wait_for_job(self.manager, job['id'])
        self.assertEqual(self.calls, [(1, 'lossless'), (1, 'exhigh'), (3, 'lossless')])
        self.assertEqual((final['succeeded'], final['failed'], final['fallback_count']), (2, 0, 1))
        self.assertEqual(final['fallbacks'], [{'id': 1, 'requested_quality': 'lossless', 'quality': 'exhigh'}])
        manifest = self.manifest(job['id'])
        self.assertEqual(manifest['fallback_count'], 1)
        song = manifest['songs'][0]
        self.assertEqual((song['requested_quality'], song['quality']), ('lossless', 'exhigh'))
        self.assertEqual([attempt['success'] for attempt in song['attempts']], [False, True])

    def test_retries_exceptions_failed_results_and_empty_files_down_to_standard(self):
        self.responses.update({(1, 'hires'): DownloadException('超时'),
                               (1, 'lossless'): False, (1, 'exhigh'): 'empty'})
        job = self.manager.create([1], 'hires')
        final = wait_for_job(self.manager, job['id'])
        self.assertEqual(self.calls, [(1, quality) for quality in ('hires', 'lossless', 'exhigh', 'standard')])
        self.assertEqual(final['state'], 'completed')
        song = self.manifest(job['id'])['songs'][0]
        self.assertEqual(song['quality'], 'standard')
        self.assertEqual(len(song['attempts']), 4)

    def test_all_qualities_fail_only_counts_song_once_then_continues(self):
        for quality in ('lossless', 'exhigh', 'standard'):
            self.responses[(1, quality)] = DownloadException('Read timed out')
        job = self.manager.create([1, 3], 'lossless')
        final = wait_for_job(self.manager, job['id'])
        self.assertEqual(self.calls, [(1, 'lossless'), (1, 'exhigh'), (1, 'standard'), (3, 'lossless')])
        self.assertEqual((final['completed'], final['succeeded'], final['failed']), (2, 1, 1))
        self.assertEqual(len(final['failures'][0]['attempts']), 3)
        self.assertEqual(self.manifest(job['id'])['songs'][0]['success'], False)

    def test_standard_is_attempted_only_once(self):
        self.responses[(1, 'standard')] = False
        job = self.manager.create([1], 'standard')
        final = wait_for_job(self.manager, job['id'])
        self.assertEqual(self.calls, [(1, 'standard')])
        self.assertEqual(final['state'], 'failed')

    def test_special_modes_fall_back_to_hires_without_trying_other_effects(self):
        for mode in ('jyeffect', 'sky', 'jymaster', 'vivid', 'dolby'):
            with self.subTest(mode=mode):
                self.calls.clear()
                self.responses[(1, mode)] = False
                job = self.manager.create([1], mode)
                final = wait_for_job(self.manager, job['id'])
                self.assertEqual(self.calls, [(1, mode), (1, 'hires')])
                self.assertEqual(final['fallback_count'], 1)

    def test_provider_returned_quality_is_reported_without_extra_downloads(self):
        self.responses[(1, 'lossless')] = 'standard'
        job = self.manager.create([1], 'lossless')
        final = wait_for_job(self.manager, job['id'])
        self.assertEqual(self.calls, [(1, 'lossless')])
        self.assertEqual(final['fallbacks'][0]['quality'], 'standard')
        self.assertEqual(self.manifest(job['id'])['songs'][0]['quality'], 'standard')

    def test_real_downloader_re_resolves_url_after_mid_stream_timeout(self):
        import requests
        from unittest.mock import Mock, call

        def info(song_id, quality):
            return MusicInfo(song_id, '歌曲', '歌手', '专辑', '', 1, 1,
                             f'https://example.invalid/{quality}', 'mp3', 0, quality)

        def timeout_chunks(**kwargs):
            yield b'incomplete'
            raise requests.exceptions.ReadTimeout('Read timed out')

        failed_response, success_response = Mock(), Mock()
        failed_response.iter_content.side_effect = timeout_chunks
        success_response.iter_content.return_value = [b'complete audio']
        manager = BatchDownloadManager(self.temp.name)
        with patch.object(MusicDownloader, 'get_music_info', side_effect=info) as resolve, \
             patch.object(MusicDownloader, '_write_metadata_with_ffmpeg', return_value=False), \
             patch('music_downloader.requests.get', side_effect=[failed_response, success_response]) as get:
            job = manager.create([1], 'lossless')
            final = wait_for_job(manager, job['id'])
        self.assertEqual(resolve.call_args_list, [call(1, 'lossless'), call(1, 'exhigh')])
        self.assertEqual([args.args[0] for args in get.call_args_list],
                         ['https://example.invalid/lossless', 'https://example.invalid/exhigh'])
        self.assertEqual((final['succeeded'], final['failed']), (1, 0))
        path, _ = manager.get_archive(job['id'])
        with zipfile.ZipFile(path) as archive:
            manifest = json.loads(archive.read('下载清单.json'))
            self.assertEqual(archive.read(manifest['songs'][0]['filename']), b'complete audio')

    def test_music_info_records_quality_from_provider(self):
        downloader = MusicDownloader(download_dir=self.temp.name)
        with patch('music_downloader.load_cookies', return_value={}), \
             patch.object(downloader.api, 'get_song_url', return_value={'data': [
                 {'url': 'https://example.invalid/audio', 'type': 'mp3', 'level': 'exhigh'}]}), \
             patch.object(downloader.api, 'get_song_detail', return_value={'songs': [{'name': '歌曲'}]}), \
             patch.object(downloader.api, 'get_lyric', return_value={}), patch('builtins.print'):
            self.assertEqual(downloader.get_music_info(1, 'lossless').quality, 'exhigh')

    def test_status_shows_retry_without_marking_song_failed(self):
        release, started = threading.Event(), threading.Event()

        class BlockedFallback(FakeDownloader):
            def download_music_file(self, song_id, quality):
                if quality == 'lossless':
                    return DownloadResult(success=False, error_message='Read timed out')
                started.set()
                release.wait(5)
                return super().download_music_file(song_id, quality)

        manager = BatchDownloadManager(self.temp.name, downloader_factory=BlockedFallback)
        job = manager.create([1], 'lossless')
        try:
            self.assertTrue(started.wait(2))
            current = manager.get(job['id'])
            self.assertEqual(current['state'], 'running')
            self.assertEqual(current['current_quality'], 'exhigh')
            self.assertEqual((current['completed'], current['failed']), (0, 0))
            self.assertEqual(current['message'], '正在降低音质重试')
        finally:
            release.set()
            wait_for_job(manager, job['id'])


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
