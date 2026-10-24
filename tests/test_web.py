"""HTTP upload/job/download contracts; the injected runner does not test pose accuracy."""
import json
import shutil
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
import cv2
import numpy as np
from fastapi.testclient import TestClient
from rom.web import create_app


def fake_runner(source, output, progress, filename):
    shutil.copy2(source, output)
    progress('Processed 3 frames (0.3s)')
    arm={'min_flexion_deg':0.,'max_flexion_deg':0.,'observed_rom_deg':0.,'coverage_percent':100.,'valid_frames':3,'total_frames':3,'status':'measured'}
    summary={'frames':3,'input_name':filename,'arms':{'left':arm,'right':arm},'fps':10.}
    output.with_suffix('.json').write_text(json.dumps(summary))
    output.with_suffix('.html').write_text('<html><video src="result.mp4" controls></video></html>')
    output.with_suffix('.csv').write_text('frame,time_s\n0,0\n')
    (output.parent/'playback.json').write_text('{"fps":10,"left":[0,0,0],"right":[0,0,0]}')
    output.with_suffix('.pdf').write_bytes(b'%PDF-1.4\n% mock HTTP-contract artifact\n')
    with zipfile.ZipFile(output.parent/'results.zip','w') as archive:archive.write(output,output.name)
    return summary


class UploadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'input.mp4'
            writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'avc1'),10,(160,240))
            if not writer.isOpened():raise unittest.SkipTest('H.264 encoder not installed')
            for _ in range(3):writer.write(np.zeros((240,160,3),dtype=np.uint8))
            writer.release();cls.video=path.read_bytes()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.app=create_app(self.root,runner=fake_runner,max_upload_bytes=1024*1024)
        self.client=TestClient(self.app);self.client.__enter__()
        self.addCleanup(self.client.__exit__,None,None,None)

    def upload(self,name='video.mp4',data=None):
        return self.client.post('/api/jobs',files={'video':(name,self.video if data is None else data,'video/mp4')})

    def finished(self,identifier):
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            response=self.client.get('/api/jobs/'+identifier);job=response.json()
            if job['status'] in ('complete','failed'):return job
            time.sleep(.005)
        self.fail('Background job did not finish')

    def test_upload_processing_results_downloads_and_range(self):
        response=self.upload();self.assertEqual(response.status_code,202)
        job=self.finished(response.json()['id']);self.assertEqual(job['status'],'complete')
        self.assertEqual(job['metadata']['width'],160)
        self.assertEqual(job['metadata']['height'],240)
        self.assertEqual(job['summary']['input_name'],'video.mp4')
        for url in job['files'].values():self.assertEqual(self.client.get(url).status_code,200)
        response=self.client.get(job['files']['video'],headers={'Range':'bytes=0-15'})
        self.assertEqual(response.status_code,206);self.assertEqual(len(response.content),16)
        response=self.client.get(job['files']['bundle']+'?download=true')
        self.assertIn('attachment',response.headers['content-disposition'])

    def test_rejects_empty_and_unreadable_files_without_queueing(self):
        for data in (b'',b'not a video'):
            self.assertEqual(self.upload(data=data).status_code,422)
        self.assertEqual(self.app.state.manager.jobs,{})
        self.assertEqual(list(self.root.iterdir()),[])

    def test_file_size_limit(self):
        self.assertEqual(self.upload(data=b'x'*(1024*1024+1)).status_code,413)
        self.assertEqual(self.app.state.manager.jobs,{})

    def test_chunked_request_is_limited_before_video_decoding(self):
        boundary='rom-test-boundary'
        prefix=(f'--{boundary}\r\nContent-Disposition: form-data; name="video"; filename="large.mp4"\r\nContent-Type: video/mp4\r\n\r\n').encode()
        def chunks():
            yield prefix
            for _ in range(24):yield b'x'*(64*1024)
            yield f'\r\n--{boundary}--\r\n'.encode()
        response=self.client.post('/api/jobs',headers={'Content-Type':f'multipart/form-data; boundary={boundary}'},content=chunks())
        self.assertEqual(response.status_code,413)
        self.assertEqual(self.app.state.manager.jobs,{})

    def test_filename_cannot_escape_job_directory(self):
        response=self.upload('../../private.mp4')
        job=self.finished(response.json()['id'])
        self.assertEqual(job['filename'],'private.mp4')
        self.assertTrue((self.root/job['id']/'source.mp4').is_file())
        self.assertFalse((self.root/'private.mp4').exists())
        self.assertEqual(self.client.get('/api/jobs/'+job['id']+'/files/job.json').status_code,404)
        self.assertEqual(self.client.get('/api/jobs/'+'0'*32).status_code,404)
        self.assertEqual(self.client.get('/api/jobs/not-an-id').status_code,404)

    def test_separate_uploads_get_separate_results(self):
        first=self.finished(self.upload('first.mp4').json()['id'])
        second=self.finished(self.upload('second.MP4').json()['id'])
        self.assertNotEqual(first['id'],second['id'])
        self.assertEqual(first['summary']['input_name'],'first.mp4')
        self.assertEqual(second['summary']['input_name'],'second.MP4')

    def test_failed_processing_is_reported(self):
        def fail(*args):raise ValueError('No frames could be measured')
        self.app.state.manager.runner=fail
        job=self.finished(self.upload().json()['id'])
        self.assertEqual(job['status'],'failed')
        self.assertIn('No frames',job['message'])
        self.assertEqual(self.client.get('/api/jobs/'+job['id']+'/files/result.mp4').status_code,404)

    def test_server_restart_preserves_finished_jobs(self):
        job=self.finished(self.upload().json()['id'])
        second=create_app(self.root,runner=fake_runner)
        with TestClient(second) as client:
            self.assertEqual(client.get('/api/jobs/'+job['id']).json()['status'],'complete')

    def test_unfinished_job_marked_interrupted_on_restart(self):
        identifier=self.app.state.manager.reserve('unfinished.mp4','source.mp4')
        second=create_app(self.root,runner=fake_runner)
        with TestClient(second) as client:
            self.assertEqual(client.get('/api/jobs/'+identifier).json()['status'],'interrupted')

    def test_upload_interface_and_configuration(self):
        self.assertIn('Choose your video',self.client.get('/').text)
        self.assertEqual(self.client.get('/assets/app.js').status_code,200)
        self.assertEqual(self.client.get('/api/config').json()['max_upload_bytes'],1024*1024)

    def test_queue_does_not_block_status_requests(self):
        entered,release=threading.Event(),threading.Event()
        def slow(*args):
            entered.set();release.wait(3)
            return fake_runner(*args)
        self.app.state.manager.runner=slow
        self.app.state.manager.max_pending=1
        identifier=self.upload().json()['id']
        self.assertTrue(entered.wait(1))
        try:
            self.assertEqual(self.client.get('/api/jobs/'+identifier).json()['status'],'processing')
            self.assertEqual(self.client.get('/api/config').status_code,200)
            self.assertEqual(self.upload().status_code,429)
        finally:release.set()
        self.assertEqual(self.finished(identifier)['status'],'complete')
