"""PDF values, missing-data handling, and inclusion in the final upload bundle."""
import csv
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
from pypdf import PdfReader
from rom.measurement import summarize
from rom.pdf_report import write_pdf
from rom.web import process_video


class PDFTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.video=self.root/'source.mp4'
        writer=cv2.VideoWriter(str(self.video),cv2.VideoWriter_fourcc(*'avc1'),10,(320,240))
        self.assertTrue(writer.isOpened())
        for _ in range(4):writer.write(np.full((240,320,3),120,dtype=np.uint8))
        writer.release()
        self.rows=[{'frame':i,'time_s':i/10,'left_raw_flexion_deg':v,'left_flexion_deg':v,
                    'right_raw_flexion_deg':None,'right_flexion_deg':None} for i,v in enumerate([20.,40.,60.,80.])]
        self.summary={'input_name':'a-long-file-'+'W'*180+'.mp4','frames':4,'fps':10.,'duration_s':.4,
                      'width':320,'height':240,'smoothing_window':1,'warnings':[],
                      'arms':{s:summarize(self.rows,s) for s in ('left','right')}}

    def test_two_pages_with_measured_and_unavailable_values(self):
        path=write_pdf(self.root/'report.pdf',self.summary,self.rows,self.video)
        reader=PdfReader(path);self.assertEqual(len(reader.pages),2)
        text='\n'.join(p.extract_text() for p in reader.pages)
        self.assertIn('60.0°',text)
        self.assertIn('100.0° to 160.0°',text)
        self.assertIn('Unavailable',text)
        self.assertIn('Frame 3 at 0.30s',text)
        self.assertIn('Inside angle + flexion = 180°',text)
        self.assertGreater(len(reader.pages[1].images),0)

    def test_no_measurements_do_not_become_a_zero_range(self):
        for row in self.rows:row['left_raw_flexion_deg']=row['left_flexion_deg']=None
        self.summary['arms']={s:summarize(self.rows,s) for s in ('left','right')}
        path=write_pdf(self.root/'empty.pdf',self.summary,self.rows,self.video)
        reader=PdfReader(path)
        self.assertIn('No reliable range could be measured',reader.pages[1].extract_text())
        self.assertIn('Insufficient data',reader.pages[0].extract_text())

    def test_upload_finishes_with_pdf_inside_zip(self):
        output=self.root/'result.mp4'
        def analyzed(source,target,progress):
            target.write_bytes(self.video.read_bytes())
            paths={'video':target,'csv':target.with_suffix('.csv'),'summary':target.with_suffix('.json'),'report':target.with_suffix('.html')}
            with paths['csv'].open('w',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=list(self.rows[0]));writer.writeheader();writer.writerows(self.rows)
            paths['summary'].write_text(json.dumps(self.summary))
            paths['report'].write_text('placeholder')
            return self.summary,paths
        with patch('rom.web.run_analysis',side_effect=analyzed):
            result=process_video(self.video,output,lambda value:None,'uploaded.mp4')
        self.assertEqual(result['input_name'],'uploaded.mp4')
        with zipfile.ZipFile(self.root/'results.zip') as archive:
            self.assertIn('result.pdf',archive.namelist())
            self.assertTrue(archive.read('result.pdf').startswith(b'%PDF'))
        self.assertEqual(len(PdfReader(self.root/'result.pdf').pages),2)
