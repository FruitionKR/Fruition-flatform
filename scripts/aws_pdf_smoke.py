#!/usr/bin/env python3
"""Authenticated production probe: synthetic PDF only; never print tokens or signed URLs."""
import argparse
import hashlib
import json
import os
import re
import tempfile
import time
import uuid
from pathlib import Path
from urllib import error, request
from urllib.parse import urlsplit

from aws_release_safety import NoRedirect, smoke_settings


def write_pdf(path, pages=11, padding_bytes=65 * 1024 * 1024):
    """A valid text PDF with padding before xref to exercise multipart without huge OCR input."""
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    kids = []
    for number in range(1, pages + 1):
        page_id = len(objects) + 1
        stream_id = page_id + 1
        kids.append(f'{page_id} 0 R')
        objects.append((f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] '
                        f'/Resources << /Font << /F1 3 0 R >> >> /Contents {stream_id} 0 R >>').encode())
        text = (f'BT /F1 16 Tf 72 720 Td (Deployment verification page {number}) Tj '
                '0 -30 Td (Multipart storage and page batch processing.) Tj ET').encode()
        objects.append(f'<< /Length {len(text)} >>\nstream\n'.encode() + text + b'\nendstream')
    objects[1] = f'<< /Type /Pages /Count {pages} /Kids [{" ".join(kids)}] >>'.encode()
    with Path(path).open('wb') as out:
        out.write(b'%PDF-1.4\n')
        offsets = [0]
        for index, body in enumerate(objects, 1):
            offsets.append(out.tell())
            out.write(f'{index} 0 obj\n'.encode() + body + b'\nendobj\n')
        remaining = max(0, padding_bytes - out.tell())
        while remaining:
            count = min(remaining, 1024 * 1024)
            out.write(b' ' * count)
            remaining -= count
        out.write(b'\n')
        xref = out.tell()
        out.write(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
        for offset in offsets[1:]:
            out.write(f'{offset:010d} 00000 n \n'.encode())
        out.write((f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n'
                   f'startxref\n{xref}\n%%EOF\n').encode())


def storage_url(url, bucket):
    parsed = urlsplit(url)
    approved = {f'{bucket}.s3.ap-northeast-2.amazonaws.com', 's3.ap-northeast-2.amazonaws.com'}
    if parsed.scheme != 'https' or parsed.hostname not in approved or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Unexpected storage URL')
    if parsed.hostname == 's3.ap-northeast-2.amazonaws.com' and not parsed.path.startswith('/' + bucket + '/'):
        raise ValueError('Unexpected storage bucket')
    return url


class ApiStatusError(ValueError):
    def __init__(self, status):
        super().__init__('Unexpected PDF smoke API status')
        self.status = status


def failure_report(exc, stage):
    # Never serialize exception messages: HTTPError can contain a signed URL.
    report = {'status': 'failed', 'error_type': type(exc).__name__, 'stage': stage}
    status = exc.status if isinstance(exc, ApiStatusError) else exc.code if isinstance(exc, error.HTTPError) else None
    if type(status) is int and 100 <= status <= 599:
        report['http_status'] = status
    return report


class Probe:
    def __init__(self, config, settings):
        self.config, self.settings = config, settings
        self.opener = request.build_opener(NoRedirect())
        self.stage = "login"
        self.token = None
        self.created = []
        self.base = f"https://api.{config['domain']}/api/workspaces/{settings['AWS_SMOKE_WORKSPACE_ID']}/documents"

    def api(self, method, url, payload=None, expected=(200,), key=None, renew=True):
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        if key:
            headers['Idempotency-Key'] = key
        req = request.Request(url, method=method, headers=headers,
                              data=None if payload is None else json.dumps(payload).encode())
        try:
            with self.opener.open(req, timeout=120) as response:
                if response.status not in expected:
                    raise ApiStatusError(response.status)
                raw = response.read(8 * 1024 * 1024)
                return json.loads(raw) if raw else {}
        except error.HTTPError as exc:
            status = exc.code
            exc.close()
            if status == 401 and renew and self.token:
                self.token = None
                self.login()
                return self.api(method, url, payload, expected, key, renew=False)
            raise ApiStatusError(status) from None
        except (error.URLError, json.JSONDecodeError):
            raise ValueError('PDF smoke API transport or JSON failure') from None

    def remember(self, doc):
        doc_id = doc.get('id')
        if not isinstance(doc_id, str) or not re.fullmatch(r'doc_[0-9a-f]{32}', doc_id):
            raise ValueError('Invalid created document ID')
        if doc_id not in self.created:
            self.created.append(doc_id)
        return doc_id

    def cleanup(self):
        failures = 0
        for doc_id in reversed(self.created):
            try:
                doc = self.api('GET', self.base + '/' + doc_id)
                version = doc.get('current_version')
                if type(version) is not int or version < 1:
                    raise ValueError('Missing cleanup version')
                self.api('DELETE', self.base + '/' + doc_id, {'base_version': version},
                         expected=(200, 202, 204), key=str(uuid.uuid4()))
            except Exception:
                failures += 1
        return failures

    def login(self):
        self.token = self.api('POST', f"https://access.{self.config['domain']}/api/auth/login", {
            'email': self.settings['AWS_SMOKE_EMAIL'], 'password': self.settings['AWS_SMOKE_PASSWORD']}).get('access_token')
        if not self.token:
            raise ValueError('PDF smoke login failed')
    def run(self, path, timeout):
        self.login()
        self.stage = 'multipart-start'
        started = self.api('POST', self.base + '/uploads',
                           {'filename': 'deployment-' + uuid.uuid4().hex + '.pdf', 'size': path.stat().st_size})
        ticket = started['ticket']
        try:
            if started['part_count'] < 2:
                raise ValueError('Fixture did not exercise multipart upload')
            with path.open('rb') as source:
                for part in range(1, started['part_count'] + 1):
                    self.stage = 'multipart-part-url'
                    urls = self.api('POST', self.base + '/uploads/parts',
                                    {'ticket': ticket, 'first_part': part, 'count': 1})['parts']
                    signed = storage_url(urls[0]['url'], self.config['s3_bucket'])
                    # Only the signed storage URL receives these bytes; no API Bearer/cookies.
                    self.stage = 'multipart-part-put'
                    req = request.Request(signed, data=source.read(started['part_size']), method='PUT')
                    with self.opener.open(req, timeout=180) as response:
                        if response.status not in (200, 204):
                            raise ApiStatusError(response.status)
            key = str(uuid.uuid4())
            self.stage = 'multipart-complete'
            original = self.remember(self.api('POST', self.base + '/uploads/complete', {'ticket': ticket}, expected=(201,), key=key))
            self.stage = 'multipart-completion-replay'
            replay = self.api('POST', self.base + '/uploads/complete', {'ticket': ticket}, expected=(201,), key=key)
            if replay.get('id') != original:
                raise ValueError('Completion replay created a duplicate')
        except Exception:
            try:
                self.api('POST', self.base + '/uploads/abort', {'ticket': ticket}, expected=(200, 204))
            except Exception:
                pass
            raise
        self.stage = 'range-preview'
        signed = storage_url(self.api('GET', self.base + '/' + original + '/original-url')['url'], self.config['s3_bucket'])
        req = request.Request(signed, headers={'Range': 'bytes=0-4'}, method='GET')
        with self.opener.open(req, timeout=30) as response:
            if response.status != 206 or response.read(6) != b'%PDF-':
                raise ValueError('Original Range read failed')
        self.stage = 'conversion-and-ai'
        parent = self.remember(self.api('POST', self.base + '/' + original + '/convert-markdown',
                                      expected=(202,), key=str(uuid.uuid4())))
        last_part = 'doc_' + uuid.UUID(bytes=hashlib.md5((parent + ':11:0').encode()).digest(), version=3).hex
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rows = self.api('GET', self.base).get('documents', [])
            parts = [row for row in rows if row['id'] == parent or
                     (row['id'] == last_part and row.get('source_document_id') == parent)]
            for part in parts:
                self.remember(part)
            if len(parts) >= 2 and all(part.get('status') == 'completed'
                                      and part.get('pipeline_run_id')
                                      and not part['pipeline_run_id'].startswith('convert:') for part in parts):
                return {'status': 'passed', 'bytes': path.stat().st_size, 'upload_parts': started['part_count'],
                        'converted_documents': len(parts), 'range_read': 'passed', 'completion_replay': 'passed',
                        'ai_processing': 'completed'}
            # Converter retries can briefly mark failed; allow its checkpoint retry window.
            time.sleep(5)
        raise ValueError('PDF conversion/AI smoke timed out')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=1800)
    args = parser.parse_args()
    probe = Probe(json.loads(args.config.read_text()), smoke_settings())
    report = {'status': 'failed'}
    try:
        with tempfile.TemporaryDirectory(prefix='fruition-pdf-smoke-') as temp:
            pdf = Path(temp) / 'probe.pdf'
            write_pdf(pdf)
            report = probe.run(pdf, args.timeout)
    except Exception as exc:
        report = failure_report(exc, probe.stage)
    finally:
        report['cleanup_failures'] = probe.cleanup()
        if report['cleanup_failures']:
            report['status'] = 'failed'
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
        os.chmod(args.report, 0o600)
        print(json.dumps(report))
    raise SystemExit(0 if report['status'] == 'passed' else 1)


if __name__ == '__main__':
    main()
