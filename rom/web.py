"""Browser upload API with isolated jobs, a bounded queue and persistent results."""
import json
import logging
import math
import os
import re
import shutil
import subprocess
import threading
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .report import write_report
from .pdf_report import write_pdf
from .service import run_analysis
from .validation import read_rows
from .yolo_pose import DEFAULT_MODEL

ROOT = Path(__file__).resolve().parent.parent
logger = logging.getLogger(__name__)


def now():
    return datetime.now(timezone.utc).isoformat()


def inspect_video(path):
    import cv2
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened(): raise ValueError('This file could not be opened as a video. Try exporting it as an MP4.')
        fps = cap.get(cv2.CAP_PROP_FPS)
        width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if not math.isfinite(fps) or not 0 < fps <= 1000 or min(width, height) < 1:
            raise ValueError('The video has invalid timing or dimensions. Try exporting it again.')
        ok, _ = cap.read()
        if not ok: raise ValueError('No video frames could be read. Try an MP4 using H.264 encoding.')
        count = int(count) if math.isfinite(count) and count > 0 else 0
        return {'fps': fps, 'width': width, 'height': height,
                'frame_count': count, 'duration_s': count/fps if count else None}
    finally:
        cap.release()


def process_video(source, output, progress, filename):
    summary, paths = run_analysis(source, output, progress=progress)
    import cv2
    check = cv2.VideoCapture(str(output))
    code = int(check.get(cv2.CAP_PROP_FOURCC))
    check.release()
    codec = ''.join(chr((code >> 8*i) & 255) for i in range(4)).lower()
    if codec not in ('avc1', 'h264'):
        encoder = shutil.which('ffmpeg')
        if not encoder:
            raise ValueError('This server needs an H.264 encoder for browser playback. Ask the server operator to install FFmpeg.')
        progress('Preparing video playback')
        converted = output.with_name('browser.mp4')
        subprocess.run([encoder, '-v', 'error', '-y', '-i', str(output), '-an', '-c:v', 'libx264',
                        '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(converted)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        converted.replace(output)
        summary['warnings'] = [w for w in summary['warnings'] if 'MPEG-4' not in w]
    progress('Packaging your results')
    summary['input_name'] = filename
    summary['source_video'] = source.name
    paths['summary'].write_text(json.dumps(summary, indent=2, allow_nan=False))
    rows = list(read_rows(paths['csv']).values())
    write_report(paths['report'], summary, rows)
    progress('Creating PDF report')
    pdf = write_pdf(output.with_suffix('.pdf'), summary, rows, output)
    playback = output.parent / 'playback.json'
    playback.write_text(json.dumps({'fps':summary['fps'],
        'left':[row['left_raw_flexion_deg'] for row in rows],
        'right':[row['right_raw_flexion_deg'] for row in rows]}, allow_nan=False))
    bundle = output.parent / 'results.zip'
    with zipfile.ZipFile(bundle, 'w') as archive:
        for path in (*paths.values(), source, playback, pdf):
            compression = zipfile.ZIP_STORED if path.suffix.lower() in ('.mp4','.mov','.avi','.mkv','.webm') else zipfile.ZIP_DEFLATED
            archive.write(path, arcname=path.name, compress_type=compression)
    return summary


class JobManager:
    def __init__(self, root, runner=process_video, max_pending=8):
        self.root, self.runner, self.max_pending = Path(root), runner, max_pending
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.jobs = {}
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='rom-analysis')
        for path in self.root.glob('*/job.json'):
            try:
                job = json.loads(path.read_text())
                if job['status'] in ('uploading','queued','processing'):
                    job.update(status='interrupted', message='The server restarted during this analysis. Please upload the video again.')
                self.jobs[job['id']] = job
                self._save(job)
            except (OSError, ValueError, KeyError):
                logger.warning('Ignoring an unreadable job record: %s', path)

    def _save(self, job):
        directory = self.root / job['id']
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / 'job.tmp'
        temporary.write_text(json.dumps(job, allow_nan=False))
        temporary.replace(directory / 'job.json')

    def reserve(self, filename, source_name):
        with self.lock:
            if sum(job['status'] in ('uploading','queued','processing') for job in self.jobs.values()) >= self.max_pending:
                raise HTTPException(429, 'The analysis queue is full. Please try again shortly.')
            identifier = uuid.uuid4().hex
            job = {'id': identifier, 'filename': filename, 'source_name': source_name,
                   'status': 'uploading', 'message': 'Receiving video', 'progress': 0,
                   'frames_processed': 0, 'created_at': now(), 'updated_at': now()}
            self.jobs[identifier] = job
            self._save(job)
            return identifier

    def update(self, identifier, **values):
        with self.lock:
            self.jobs[identifier].update(values, updated_at=now())
            self._save(self.jobs[identifier])

    def get(self, identifier):
        if not re.fullmatch(r'[a-f0-9]{32}', identifier): raise HTTPException(404, 'Analysis not found')
        with self.lock:
            if identifier not in self.jobs: raise HTTPException(404, 'Analysis not found')
            return json.loads(json.dumps(self.jobs[identifier]))

    def discard(self, identifier):
        with self.lock:
            self.jobs.pop(identifier, None)
            shutil.rmtree(self.root / identifier, ignore_errors=True)

    def submit(self, identifier, metadata):
        self.update(identifier, status='queued', message='Waiting for analysis', metadata=metadata)
        self.executor.submit(self._work, identifier)

    def _work(self, identifier):
        job = self.get(identifier)
        directory = self.root / identifier
        self.update(identifier, status='processing', message='Preparing the analysis', progress=None)
        def progress(message):
            match = re.search(r'Processed (\d+) frames', message)
            if match:
                frames = int(match.group(1))
                total = job['metadata']['frame_count']
                self.update(identifier, message='Analyzing movement', frames_processed=frames,
                            progress=min(.95, frames/total*.95) if total else None)
            else:
                self.update(identifier, message=message, progress=.98 if 'Packaging' in message else None)
        try:
            summary = self.runner(directory/job['source_name'], directory/'result.mp4', progress, job['filename'])
            self.update(identifier, status='complete', message='Your results are ready', progress=1,
                        frames_processed=summary['frames'], summary=summary)
        except Exception as exc:
            logger.exception('Analysis failed: %s', identifier)
            message = str(exc) if isinstance(exc, (ValueError, FileNotFoundError)) else 'The analysis could not finish. Try a different video or ask the server operator to check its logs.'
            self.update(identifier, status='failed', message=message, progress=None)

    def close(self):
        self.executor.shutdown(wait=True, cancel_futures=True)


class UploadLimitMiddleware:
    def __init__(self, app, max_bytes): self.app, self.max_bytes = app, max_bytes
    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('method') != 'POST':
            return await self.app(scope, receive, send)
        length = dict(scope.get('headers', [])).get(b'content-length')
        if length:
            try: oversized = int(length) > self.max_bytes
            except ValueError: oversized = True
            if oversized:
                await send({'type':'http.response.start','status':413,'headers':[(b'content-type',b'application/json')]})
                await send({'type':'http.response.body','body':b'{"detail":"This upload exceeds the file size limit."}'})
                return
        received = 0
        async def limited_receive():
            nonlocal received
            message = await receive()
            if message['type'] == 'http.request':
                received += len(message.get('body', b''))
                if received > self.max_bytes:
                    raise HTTPException(413, 'This upload exceeds the file size limit.')
            return message
        await self.app(scope, limited_receive, send)


def create_app(job_root=None, runner=process_video, max_upload_bytes=None):
    limit = max_upload_bytes or int(os.environ.get('ROM_MAX_UPLOAD_MB', '1024')) * 1024 * 1024
    if limit < 1: raise ValueError('The upload limit must be positive')
    manager = JobManager(job_root or ROOT/'outputs'/'uploads', runner)
    @asynccontextmanager
    async def lifespan(app):
        yield
        manager.close()
    app = FastAPI(title='Elbow ROM', lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.manager = manager
    app.add_middleware(UploadLimitMiddleware, max_bytes=limit+128*1024)
    app.mount('/assets', StaticFiles(directory=ROOT/'web'), name='assets')

    @app.get('/')
    def index(): return FileResponse(ROOT/'web'/'index.html')

    @app.get('/api/config')
    def config():
        return {'max_upload_bytes':limit, 'model_ready':DEFAULT_MODEL.is_file()}

    @app.post('/api/jobs', status_code=202)
    async def upload(video: UploadFile = File(...)):
        if runner is process_video and not DEFAULT_MODEL.is_file():
            await video.close()
            raise HTTPException(503, 'The analysis engine is not ready on this server. Ask the server operator to run setup.')
        filename = (video.filename or 'video').replace('\\','/').split('/')[-1]
        filename = ''.join(c for c in filename if c.isprintable())[:200] or 'video'
        suffix = Path(filename).suffix.lower()
        if not re.fullmatch(r'\.[a-z0-9]{1,10}', suffix): suffix = '.video'
        try:
            identifier = manager.reserve(filename, 'source'+suffix)
        except Exception:
            await video.close()
            raise
        source = manager.root / identifier / ('source'+suffix)
        submitted = False
        try:
            size = 0
            with source.open('wb') as destination:
                while chunk := await video.read(1024*1024):
                    size += len(chunk)
                    if size > limit: raise HTTPException(413, 'This video exceeds the file size limit.')
                    destination.write(chunk)
            if size == 0: raise HTTPException(422, 'The uploaded file is empty.')
            import asyncio
            metadata = await asyncio.to_thread(inspect_video, source)
            manager.submit(identifier, metadata)
            submitted = True
        except (HTTPException, ValueError) as exc:
            manager.discard(identifier)
            if isinstance(exc, HTTPException): raise
            raise HTTPException(422, str(exc)) from exc
        except Exception:
            manager.discard(identifier)
            raise
        finally:
            await video.close()
            if not submitted: manager.discard(identifier)
        return {'id':identifier, 'status_url':f'/api/jobs/{identifier}'}

    @app.get('/api/jobs/{identifier}')
    def status(identifier: str):
        job = manager.get(identifier)
        base = f'/api/jobs/{identifier}/files/'
        job['source_url'] = base + job['source_name']
        if job['status'] == 'complete':
            job['files'] = {key:base+name for key,name in (
                ('video','result.mp4'),('report','result.html'),('csv','result.csv'),('summary','result.json'),('bundle','results.zip'),('playback','playback.json'),('pdf','result.pdf'))}
        return job

    @app.get('/api/jobs/{identifier}/files/{name}')
    def download(identifier: str, name: str, download: bool = False):
        job = manager.get(identifier)
        allowed = {job['source_name']} if job['status'] in ('queued','processing','complete') else set()
        if job['status'] == 'complete': allowed.update(('result.mp4','result.csv','result.json','result.html','results.zip','playback.json','result.pdf'))
        if name not in allowed: raise HTTPException(404, 'File not found')
        path = manager.root / identifier / name
        if not path.is_file(): raise HTTPException(404, 'File not found')
        return FileResponse(path, filename=name if download else None,
                            content_disposition_type='attachment' if download else 'inline')
    return app
