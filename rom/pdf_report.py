"""Printable analysis report generated from the same measurements as the video."""
import math
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

INK=colors.HexColor('#202625')
MUTED=colors.HexColor('#5c6864')
LINE=colors.HexColor('#dce2df')
GREEN=colors.HexColor('#237561')
ORANGE=colors.HexColor('#a76531')
PAPER=colors.HexColor('#f1f5f2')
W,H=A4
M=44


def degree(value):
    return 'Unavailable' if value is None else f'{value:.1f}°'


def text(c, x, y, value, size=10, color=INK, bold=False):
    c.setFont('Helvetica-Bold' if bold else 'Helvetica',size)
    c.setFillColor(color)
    c.drawString(x,y,str(value))


def paragraph(c, value, x, y, width, size=9, leading=13, color=MUTED, max_lines=None):
    c.setFont('Helvetica',size)
    words=[]
    for word in str(value).split():
        while c.stringWidth(word,'Helvetica',size)>width:
            cut=1
            while cut<len(word) and c.stringWidth(word[:cut+1],'Helvetica',size)<=width:cut+=1
            words.append(word[:cut]);word=word[cut:]
        if word:words.append(word)
    lines=[]
    line=''
    for word in words:
        candidate=(line+' '+word).strip()
        if c.stringWidth(candidate,'Helvetica',size)>width and line:
            lines.append(line);line=word
        else:line=candidate
    if line:lines.append(line)
    if max_lines is not None and len(lines)>max_lines:
        lines=lines[:max_lines]
        while c.stringWidth(lines[-1]+'...','Helvetica',size)>width:lines[-1]=lines[-1][:-1]
        lines[-1]+='...'
    for line in lines:text(c,x,y,line,size,color);y-=leading
    return y


def heading(c, page):
    text(c,M,H-43,'ELBOW ROM',11,GREEN,True)
    text(c,W-M-114,H-43,'VIDEO ANALYSIS REPORT',8,MUTED)
    c.setStrokeColor(LINE);c.line(M,H-57,W-M,H-57)
    text(c,M,28,'2D video estimates - not clinically validated',8,MUTED)
    c.setFont('Helvetica',8);c.setFillColor(MUTED);c.drawRightString(W-M,28,f'{page} / 2')


def draw_chart(c, rows, fps):
    x,y,width,height=M+31,249,W-2*M-39,150
    c.setLineWidth(.5)
    for value in (0,45,90,135,180):
        yy=y+height*value/180
        c.setStrokeColor(LINE);c.line(x,yy,x+width,yy)
        text(c,M,yy-3,f'{value}°',8,MUTED)
    duration=max(rows[-1]['time_s'],1/fps) if rows else 1
    for index in range(5):
        xx=x+width*index/4
        text(c,xx-6,y-17,f'{duration*index/4:.1f}s',8,MUTED)
    for side,color in [('left',GREEN),('right',ORANGE)]:
        path=c.beginPath();connected=False
        for row in rows:
            value=row.get(f'{side}_flexion_deg')
            if value is None or not math.isfinite(value):connected=False;continue
            xx=x+row['time_s']/duration*width;yy=y+height*value/180
            if connected:path.lineTo(xx,yy)
            else:path.moveTo(xx,yy)
            connected=True
        c.setStrokeColor(color);c.setLineWidth(1.15);c.drawPath(path)
    text(c,W-M-120,426,'Left',9,GREEN,True)
    text(c,W-M-60,426,'Right',9,ORANGE,True)


def frame_image(video, index):
    import cv2
    cap=cv2.VideoCapture(str(video))
    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES,index)
        ok,frame=cap.read()
        if not ok:return None
        ok,encoded=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,88])
        return BytesIO(encoded.tobytes()) if ok else None
    finally:cap.release()


def write_pdf(path, summary, rows, video):
    """Write a two-page PDF; unavailable measurements are never turned into zeros."""
    path=Path(path)
    temporary=path.with_suffix('.pdf.part')
    c=canvas.Canvas(str(temporary),pagesize=A4,pageCompression=1)
    c.setTitle('Elbow movement report - '+summary['input_name'])
    c.setAuthor('Elbow ROM')
    heading(c,1)
    text(c,M,H-95,'Elbow movement report',24,INK,True)
    paragraph(c,summary['input_name'],M,H-118,W-2*M,10,13,INK,max_lines=2)
    text(c,M,H-151,'GENERATED',8,MUTED,True)
    text(c,M,H-168,datetime.now(timezone.utc).strftime('%d %b %Y, %H:%M UTC'),10)
    for xx,label,value in [(250,'DURATION',f'{summary["duration_s"]:.2f}s'),(350,'FRAMES',str(summary['frames'])),(440,'VIDEO',f'{summary["width"]} x {summary["height"]}')]:
        text(c,xx,H-151,label,8,MUTED,True);text(c,xx,H-168,value,10)
    text(c,M,622,'Observed movement',13,INK,True)
    col=[M,282,418]
    c.setFillColor(PAPER);c.roundRect(M,582,W-2*M,25,4,fill=1,stroke=0)
    for xx,value in zip(col,['MEASUREMENT','LEFT ELBOW','RIGHT ELBOW']):text(c,xx+8,591,value,8,MUTED,True)
    arms=summary['arms']
    entries=[('Observed movement range',*[degree(arms[s]['observed_rom_deg']) for s in ('left','right')]),
             ('Inside angle range',*[('Unavailable' if arms[s]['min_flexion_deg'] is None else f'{180-arms[s]["max_flexion_deg"]:.1f}° to {180-arms[s]["min_flexion_deg"]:.1f}°') for s in ('left','right')]),
             ('Flexion range',*[('Unavailable' if arms[s]['min_flexion_deg'] is None else f'{arms[s]["min_flexion_deg"]:.1f}° to {arms[s]["max_flexion_deg"]:.1f}°') for s in ('left','right')]),
             ('Frames measured',*[f'{arms[s]["valid_frames"]}/{arms[s]["total_frames"]} ({arms[s]["coverage_percent"]:.1f}%)' for s in ('left','right')]),
             ('Data status',*[arms[s]['status'].replace('_',' ').capitalize() for s in ('left','right')])]
    yy=565
    for index,entry in enumerate(entries):
        for xx,value in zip(col,entry):text(c,xx+8,yy,value,9,INK,index==0)
        c.setStrokeColor(LINE);c.line(M,yy-10,W-M,yy-10);yy-=25
    text(c,M,426,'Flexion over time',12,INK,True)
    draw_chart(c,rows,summary['fps'])
    text(c,M,199,'Inside angle + flexion = 180°',12,INK,True)
    paragraph(c,'Inside angle is the visible shoulder-elbow-wrist angle. A straight arm is 180°. Flexion is the bend away from straight, where a straight arm is 0°. For example: 108° inside angle means 72° flexion.',M,180,W-2*M,9,13)
    text(c,M,116,'How to interpret the range',10,INK,True)
    paragraph(c,f'Range is the largest minus smallest valid smoothed flexion in this clip, using a {summary["smoothing_window"]}-frame median. It describes recorded movement, not the full range the person can achieve. Gaps in the graph indicate unavailable measurements.',M,99,W-2*M,9,13)
    c.showPage();heading(c,2)
    text(c,M,H-95,'Frames behind the measurements',21,INK,True)
    paragraph(c,'Extremes below use the smoothed series. The captions identify each source frame and its current-frame angle estimates.',M,H-118,W-2*M,9,13)
    selections=[]
    for side in ('left','right'):
        valid=[r for r in rows if r.get(f'{side}_flexion_deg') is not None]
        if len(valid)>=2:
            for label,select in [('minimum',min),('maximum',max)]:
                row=select(valid,key=lambda r:r[f'{side}_flexion_deg'])
                selections.append((side,label,row))
    boxw=(W-2*M-18)/2
    for index,(side,label,row) in enumerate(selections):
        xx=M+(index%2)*(boxw+18);top=672-(index//2)*215
        text(c,xx,top,f'{side.capitalize()} elbow - {label}',10,INK,True)
        image=frame_image(video,row['frame'])
        if image:
            c.setFillColor(PAPER);c.rect(xx,top-151,boxw,138,fill=1,stroke=0)
            c.drawImage(ImageReader(image),xx,top-151,boxw,138,preserveAspectRatio=True,anchor='c',mask='auto')
        else:paragraph(c,'The video frame could not be decoded.',xx,top-50,boxw)
        raw=row.get(f'{side}_raw_flexion_deg')
        text(c,xx,top-166,f'Frame {int(row["frame"])} at {row["time_s"]:.2f}s',8,MUTED)
        text(c,xx,top-180,f'Inside {degree(None if raw is None else 180-raw)} / flexion {degree(raw)}',8,MUTED)
        text(c,xx,top-194,f'Smoothed flexion: {degree(row[f"{side}_flexion_deg"])}',8,MUTED)
    if not selections:
        text(c,M,653,'No reliable range could be measured.',14,INK,True)
        paragraph(c,'The video was processed, but too few usable joint detections were available. Keep the shoulder, elbow and wrist visible, use a side view, and record one person with a steady camera.',M,627,W-2*M,11,16)
    text(c,M,210,'Quality and limitations',11,INK,True)
    yy=192
    notes=['Perspective, occlusion, blur and landmark errors can affect estimates. Model confidence is not an accuracy guarantee. This report does not diagnose or grade movement limitations.']
    notes += [w for w in summary.get('warnings',[]) if 'not calibrated' not in w and 'One person' not in w]
    for note in notes:
        if yy<67:break
        yy=paragraph(c,note,M,yy,W-2*M,8.5,12)-6
    c.save()
    temporary.replace(path)
    return path
