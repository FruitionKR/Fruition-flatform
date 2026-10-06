import importlib.util
import re
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import aws_pdf_smoke as smoke


class PdfSmokeTests(unittest.TestCase):
    def test_api_failure_preserves_status_without_sensitive_http_details(self):
        probe = smoke.Probe({'domain': 'example.test'}, {'AWS_SMOKE_WORKSPACE_ID': 'ws_test'})
        probe.opener = Mock()
        probe.opener.open.side_effect = HTTPError(
            'https://example.test/?signature=secret', 500, 'private body', {}, None)
        with self.assertRaises(smoke.ApiStatusError) as raised:
            probe.api('POST', probe.base + '/uploads', {})
        self.assertEqual(smoke.failure_report(raised.exception, 'multipart-start'), {
            'status': 'failed', 'error_type': 'ApiStatusError',
            'stage': 'multipart-start', 'http_status': 500})

    def test_storage_failure_report_does_not_expose_signed_url(self):
        failure = HTTPError('https://storage.test/?signature=secret', 403, 'private', {}, None)
        self.addCleanup(failure.close)
        self.assertEqual(smoke.failure_report(failure, 'multipart-part-put'), {
            'status': 'failed', 'error_type': 'HTTPError',
            'stage': 'multipart-part-put', 'http_status': 403})

    def test_fixture_has_consistent_xref_and_multiple_text_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'probe.pdf'
            smoke.write_pdf(path, pages=11, padding_bytes=1024 * 1024)
            data = path.read_bytes()
        self.assertGreater(len(data), 1024 * 1024)
        self.assertIn(b'/Count 11', data)
        xref = int(re.search(rb'startxref\n(\d+)', data).group(1))
        self.assertEqual(data[xref:xref + 4], b'xref')
        entries = data[xref:].split(b'\n')[3:]
        for number, entry in enumerate(entries, 1):
            if not re.fullmatch(rb'\d{10} 00000 n ', entry):
                break
            offset = int(entry[:10])
            self.assertTrue(data[offset:].startswith(f'{number} 0 obj\n'.encode()))
        self.assertEqual(data.count(b'/Type /Page '), 11)

    def test_signed_url_is_limited_to_expected_s3_bucket_and_https(self):
        bucket = 'example-storage'
        allowed = [f'https://{bucket}.s3.ap-northeast-2.amazonaws.com/object?signature=secret',
                   f'https://s3.ap-northeast-2.amazonaws.com/{bucket}/object?signature=secret']
        for url in allowed:
            self.assertEqual(smoke.storage_url(url, bucket), url)
        rejected = ['http://169.254.169.254/latest',
                    'https://example.test/object',
                    'https://s3.ap-northeast-2.amazonaws.com/other/object',
                    f'https://user:password@{bucket}.s3.ap-northeast-2.amazonaws.com/object',
                    f'https://{bucket}.s3.ap-northeast-2.amazonaws.com:8443/object']
        for url in rejected:
            with self.assertRaises(ValueError):
                smoke.storage_url(url, bucket)

    def test_cleanup_only_touches_ids_created_by_this_probe(self):
        probe = smoke.Probe({'domain': 'example.test'}, {'AWS_SMOKE_WORKSPACE_ID': 'ws_' + '0' * 32})
        created = 'doc_' + '1' * 32
        probe.remember({'id': created})
        probe.remember({'id': created})
        calls = []
        def api(method, url, payload=None, **kwargs):
            calls.append((method, url, payload))
            return {'current_version': 7}
        probe.api = api
        self.assertEqual(probe.cleanup(), 0)
        self.assertEqual([method for method, _, _ in calls], ['GET', 'DELETE'])
        self.assertTrue(all(url.endswith(created) for _, url, _ in calls))
        self.assertEqual(calls[1][2], {'base_version': 7})


    PARENT = 'doc_' + 'b' * 32

    def _run_conversion(self, documents):
        bucket = 'example-storage'
        probe = smoke.Probe({'domain': 'example.test', 's3_bucket': bucket}, {'AWS_SMOKE_WORKSPACE_ID': 'ws_' + '0' * 32})
        probe.login = lambda: None
        signed = f'https://{bucket}.s3.ap-northeast-2.amazonaws.com/object?signature=secret'
        responses = {'/uploads': {'ticket': 't', 'part_count': 2, 'part_size': 1024},
                     '/uploads/parts': {'parts': [{'url': signed}]},
                     '/uploads/complete': {'id': 'doc_' + 'a' * 32},
                     '/original-url': {'url': signed},
                     '/convert-markdown': {'id': self.PARENT},
                     '': {'documents': documents}}
        def api(method, url, payload=None, **kwargs):
            path = url[len(probe.base):]
            return next(body for suffix, body in responses.items() if path.endswith(suffix))
        probe.api = api
        def storage(req, timeout):
            response = Mock(status=200 if req.get_method() == 'PUT' else 206)
            response.read.return_value = b'%PDF-'
            context = Mock()
            context.__enter__ = Mock(return_value=response)
            context.__exit__ = Mock(return_value=False)
            return context
        probe.opener = Mock()
        probe.opener.open.side_effect = storage
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'probe.pdf'
            path.write_bytes(b'%PDF-' + b'0' * 2048)
            return probe, probe.run(path, timeout=1)

    def test_small_pdf_conversion_passes_as_single_document_after_ai(self):
        _, report = self._run_conversion([{'id': self.PARENT, 'status': 'completed', 'pipeline_run_id': 'run_1'}])
        self.assertEqual(report['converted_documents'], 1)
        self.assertEqual(report['ai_processing'], 'completed')

    def test_small_pdf_conversion_rejects_split_documents(self):
        part = 'doc_' + 'c' * 32
        with self.assertRaisesRegex(ValueError, 'split documents'):
            self._run_conversion([{'id': self.PARENT, 'status': 'completed', 'pipeline_run_id': 'run_1'},
                                  {'id': part, 'source_document_id': self.PARENT}])

    def test_conversion_waits_until_ai_replaces_convert_run(self):
        with self.assertRaisesRegex(ValueError, 'timed out'), patch.object(smoke.time, 'sleep'):
            self._run_conversion([{'id': self.PARENT, 'status': 'completed', 'pipeline_run_id': 'convert:q1'}])

if __name__ == '__main__':
    unittest.main()
