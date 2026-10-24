'use strict';
const $ = id => document.getElementById(id);
const state = {file:null, preview:null, job:null, data:null, side:'left', view:'original', busy:false, maxBytes:1024**3, ready:true, timer:null, animation:null};
const sourceVideo=$('source-preview'), resultVideo=$('result-video');
const videos=[sourceVideo,resultVideo];
const activeVideo=()=>state.view==='analyzed'?resultVideo:sourceVideo;
const bytes=value=>value>=1024**3?`${(value/1024**3).toFixed(1)} GB`:`${(value/1024**2).toFixed(1)} MB`;
const clock=value=>{value=Number.isFinite(value)?Math.max(0,value):0;return `${String(Math.floor(value/60)).padStart(2,'0')}:${(value%60).toFixed(2).padStart(5,'0')}`;};
const angle=value=>value===null||value===undefined?'Unavailable':`${value.toFixed(1)}°`;
let recent=[];
try{recent=JSON.parse(localStorage.getItem('rom.recent')||'[]').filter(item=>/^[a-f0-9]{32}$/.test(item.id)).slice(0,12);}catch{}
function showMessage(value){$('message').textContent=value;$('message').hidden=!value;}
function controls(){
 const video=activeVideo(), available=video.readyState>=1&&$('empty-view').hidden;
 for(const id of ['play-toggle','scrubber','playback-speed','fullscreen'])$(id).disabled=!available;
 for(const id of ['step-back','step-forward'])$(id).disabled=!available||!state.job?.metadata?.fps;
 $('analyze').disabled=state.busy||!state.file||!state.ready;
 $('choose-file').disabled=state.busy;$('change-file').disabled=state.busy;
 $('new-analysis').disabled=state.busy||(!state.file&&!state.job);
 $('view-original').disabled=!sourceVideo.getAttribute('src');
 $('view-analyzed').disabled=state.job?.status!=='complete';
 $('change-file').hidden=!state.file&&!state.job;
 $('play-toggle').setAttribute('aria-label',video.paused?'Play video':'Pause video');
 $('play-toggle').firstElementChild.className=`icon i-player-${video.paused?'play':'pause'}`;
}
function mode(value){document.body.dataset.state=value;controls();}
function setView(view){
 if(view==='analyzed'&&state.job?.status!=='complete')return;
 const before=activeVideo(), time=before.currentTime||0;before.pause();state.view=view;
 sourceVideo.hidden=view!=='original'||!sourceVideo.getAttribute('src');
 resultVideo.hidden=view!=='analyzed'||!resultVideo.getAttribute('src');
 $('view-original').setAttribute('aria-pressed',String(view==='original'));
 $('view-analyzed').setAttribute('aria-pressed',String(view==='analyzed'));
 const video=activeVideo();if(video.readyState>=1)video.currentTime=Math.min(time,Math.max(0,video.duration-.001));
 $('video-unavailable').hidden=!video.error;
 updateTime();controls();
}
function remember(job){
 recent=[{id:job.id,name:job.filename,created:job.created_at,status:job.status},...recent.filter(r=>r.id!==job.id)].slice(0,12);
 try{localStorage.setItem('rom.recent',JSON.stringify(recent));}catch{}
 renderLibrary();
}
function renderLibrary(){
 const list=$('recent-list');list.replaceChildren();
 if(!recent.length){const p=document.createElement('p');p.className='library-empty';p.textContent='Your videos will appear here.';list.append(p);return;}
 for(const item of recent){
  const link=document.createElement('a');link.href=`?job=${item.id}`;link.className='recent-item'+(state.job?.id===item.id?' active':'');
  const icon=document.createElement('span');icon.className='icon i-video';const detail=document.createElement('div');
  const name=document.createElement('strong');name.textContent=item.name;name.title=item.name;
  const meta=document.createElement('small');const date=new Date(item.created);
  meta.textContent=`${Number.isNaN(date.getTime())?'Saved analysis':date.toLocaleDateString(undefined,{month:'short',day:'numeric'})} · ${item.status==='complete'?'Complete':item.status==='processing'?'Analyzing':item.status==='queued'?'Queued':'Interrupted'}`;
  detail.append(name,meta);link.append(icon,detail);
  link.addEventListener('click',event=>{event.preventDefault();if(state.busy)return;reset(false);history.replaceState(null,'',link.href);closeLibrary();poll(item.id);});list.append(link);
 }
}
function choose(file){
 if(state.busy||!file)return;
 if(!file.size){showMessage('This file is empty. Choose a video with recorded footage.');return;}
 if(file.size>state.maxBytes){showMessage(`Choose a video smaller than ${bytes(state.maxBytes)}.`);return;}
 reset(false);state.file=file;state.preview=URL.createObjectURL(file);sourceVideo.src=state.preview;
 $('empty-view').hidden=true;sourceVideo.hidden=false;
 $('document-name').textContent=file.name;$('document-status').textContent='Ready to analyze';
 $('video-meta').textContent=bytes(file.size);$('result-badge').textContent='Ready';mode('selected');
}
function reset(clearURL=true){
 clearTimeout(state.timer);cancelAnimationFrame(state.animation);videos.forEach(video=>{video.pause();video.removeAttribute('src');video.hidden=true;});
 if(state.preview)URL.revokeObjectURL(state.preview);
 Object.assign(state,{file:null,preview:null,job:null,data:null,busy:false,view:'original'});
 $('video-file').value='';$('empty-view').hidden=false;$('video-unavailable').hidden=true;
 $('document-name').textContent='Untitled analysis';$('document-status').textContent='Video analysis';$('video-meta').textContent='No video selected';
 $('result-badge').textContent='No analysis';$('job-progress').hidden=true;$('other-exports').hidden=true;
 $('pdf-link').removeAttribute('href');$('pdf-link').setAttribute('aria-disabled','true');$('report-status').textContent='Generated when analysis finishes.';
 $('view-original').setAttribute('aria-pressed','true');$('view-analyzed').setAttribute('aria-pressed','false');
 $('analyze').innerHTML='Analyze video<span class="icon i-chart-line"></span>';
 if(clearURL)history.replaceState(null,'','/');showMessage('');renderSummary();renderFrame();drawBase();updateTime();renderLibrary();mode('empty');
}
async function getJson(url){
 const response=await fetch(url);let data;
 try{data=await response.json();}catch{throw new Error('The server returned an unreadable response.');}
 if(!response.ok){const error=new Error(typeof data.detail==='string'?data.detail:'The request could not be completed.');error.status=response.status;throw error;}return data;
}
function showProgress(title,fraction,detail=''){
 $('job-progress').hidden=false;$('progress-title').textContent=title;$('progress-detail').textContent=detail;
 if(fraction===null){$('progress').removeAttribute('value');$('progress-label').textContent='';}
 else{$('progress').value=fraction*100;$('progress-label').textContent=`${Math.round(fraction*100)}%`;}
}
function upload(){
 if(!state.file||state.busy)return;state.busy=true;showMessage('');mode('processing');showProgress('Uploading video',0);
 $('analyze').textContent='Analyzing video';$('document-status').textContent='Uploading';
 const form=new FormData();form.append('video',state.file);const request=new XMLHttpRequest();request.open('POST','/api/jobs');request.responseType='json';
 request.upload.addEventListener('progress',event=>{if(event.lengthComputable)showProgress('Uploading video',event.loaded/event.total);});
 request.addEventListener('error',()=>{state.busy=false;mode('selected');$('analyze').textContent='Try analysis again';showMessage('The upload lost its connection. Please try again.');});
 request.addEventListener('load',()=>{
  if(request.status!==202){state.busy=false;mode('selected');$('job-progress').hidden=true;$('analyze').textContent='Analyze video';showMessage(typeof request.response?.detail==='string'?request.response.detail:'The upload could not be accepted. Try another video.');return;}
  const id=request.response.id;history.replaceState(null,'',`?job=${id}`);poll(id);
 });request.send(form);
}
async function poll(id){
 clearTimeout(state.timer);
 try{
  const job=await getJson(`/api/jobs/${id}`);state.job=job;remember(job);
  $('document-name').textContent=job.filename;$('empty-view').hidden=true;
  if(!state.preview&&!['failed','interrupted'].includes(job.status)&&sourceVideo.getAttribute('src')!==job.source_url){sourceVideo.src=job.source_url;sourceVideo.hidden=state.view!=='original';}
  if(job.metadata)$('video-meta').textContent=`${job.metadata.width} × ${job.metadata.height}${job.metadata.duration_s?` · ${job.metadata.duration_s.toFixed(1)}s`:''}`;
  if(job.status==='complete'){
   state.busy=false;mode('complete');$('job-progress').hidden=true;$('document-status').textContent='Analysis complete';$('result-badge').textContent='Complete';
   resultVideo.src=job.files.video;setView('analyzed');renderSummary();
   $('pdf-link').href=job.files.pdf+'?download=true';$('pdf-link').setAttribute('aria-disabled','false');$('report-status').textContent='PDF report ready to download.';
   $('bundle-link').href=job.files.bundle+'?download=true';$('report-link').href=job.files.report;
   for(const [id,key]of [['video-link','video'],['csv-link','csv'],['json-link','summary']])$(id).href=job.files[key]+'?download=true';
   $('other-exports').hidden=false;
   try{const data=await getJson(job.files.playback);if(state.job?.id===job.id){state.data=data;renderFrame();drawBase();}}
   catch{showMessage('The video is ready. Open the report for frame measurements.');}controls();return;
  }
  if(['failed','interrupted'].includes(job.status)){
   state.busy=false;mode('selected');$('document-status').textContent='Analysis interrupted';$('result-badge').textContent='Interrupted';$('job-progress').hidden=true;$('analyze').textContent='Try analysis again';showMessage(job.message);return;
  }
  state.busy=true;mode('processing');$('analyze').textContent='Analyzing video';$('result-badge').textContent=job.status==='queued'?'Queued':'Analyzing';$('document-status').textContent=job.status==='queued'?'Waiting for analysis':'Analyzing';
  showProgress(job.message,job.progress,job.frames_processed?`${job.frames_processed} frames processed`:'You can return to this analysis while it finishes.');
  state.timer=setTimeout(()=>poll(id),1500);
 }catch(error){
  if(error.status===404){state.busy=false;controls();showMessage('This analysis is no longer available. Choose a new video.');return;}
  showProgress('Reconnecting to server',null,'Analysis may still be running. Retrying automatically.');state.timer=setTimeout(()=>poll(id),4000);
 }
}
function summaryField(label,value,first=false){const row=document.createElement('div'),dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=value;row.append(dt,dd);$('arm-results').append(row);}
function renderSummary(){
 const arm=state.job?.summary?.arms?.[state.side];$('arm-results').replaceChildren();$('coverage-note').hidden=true;
 if(!arm){for(const label of ['Movement range','Inside angle','Flexion','Frames measured'])summaryField(label,'Not measured');return;}
 summaryField('Movement range',angle(arm.observed_rom_deg));
 summaryField('Inside angle',arm.min_flexion_deg===null?'Unavailable':`${angle(180-arm.max_flexion_deg)} to ${angle(180-arm.min_flexion_deg)}`);
 summaryField('Flexion',arm.min_flexion_deg===null?'Unavailable':`${angle(arm.min_flexion_deg)} to ${angle(arm.max_flexion_deg)}`);
 summaryField('Frames measured',`${arm.coverage_percent.toFixed(1)}% (${arm.valid_frames}/${arm.total_frames})`);
 $('range-note').textContent='Ranges use smoothed measurements across the clip.';
 if(arm.status==='insufficient_data'||arm.status==='low_coverage'){$('coverage-note').hidden=false;$('coverage-note').textContent=arm.status==='insufficient_data'?'Not enough usable frames to measure a movement range.':'Tracking was available in fewer than half the frames. Treat this range cautiously.';}
}
function frameIndex(){return state.data?Math.min(state.data.left.length-1,Math.max(0,Math.floor(activeVideo().currentTime*state.data.fps+.001))):0;}
function renderFrame(){
 const value=state.data?.[state.side]?.[frameIndex()];const valid=value!==null&&value!==undefined;
 $('inside-value').textContent=valid?angle(180-value):state.data?'Unavailable':'Not measured';
 $('flexion-value').textContent=valid?angle(value):state.data?'Unavailable':'Not measured';
 $('inside-value').classList.toggle('empty',!valid);$('flexion-value').classList.toggle('empty',!valid);
 $('frame-number').textContent=state.data?`Frame ${frameIndex()+1} of ${state.data.left.length}`:'No frame';
 $('current-angles').textContent=valid?'Inside angle + flexion = 180°':state.data?'Tracking unavailable in this frame.':'Inside angle + flexion = 180°';
}
function updateTime(){
 const video=activeVideo(),duration=Number.isFinite(video.duration)?video.duration:0;
 $('time-current').textContent=clock(video.currentTime);$('time-duration').textContent=clock(duration);
 $('scrubber').max=duration||1;$('scrubber').step=state.data?1/state.data.fps:.001;$('scrubber').value=video.currentTime||0;
 renderFrame();drawCursor();
}
function seek(time){const video=activeVideo();if(video.readyState<1)return;const fps=state.job?.metadata?.fps||30;video.currentTime=Math.max(0,Math.min(time,Math.max(0,video.duration-1/fps)));updateTime();}
function tick(){updateTime();if(!activeVideo().paused)state.animation=requestAnimationFrame(tick);}
for(const video of videos){
 video.controls=false;
 video.addEventListener('loadedmetadata',()=>{if(video===activeVideo()){updateTime();controls();}});
 video.addEventListener('play',()=>{if(video===activeVideo()){cancelAnimationFrame(state.animation);controls();tick();}});
 for(const event of ['pause','ended','seeked','timeupdate'])video.addEventListener(event,()=>{if(video===activeVideo()){controls();updateTime();}});
 video.addEventListener('error',()=>{if(video===activeVideo()&&video.getAttribute('src')){$('video-unavailable').hidden=false;controls();}});
}
$('choose-file').addEventListener('click',()=>$('video-file').click());$('change-file').addEventListener('click',()=>$('video-file').click());
$('video-file').addEventListener('change',event=>choose(event.target.files[0]));$('analyze').addEventListener('click',upload);
$('new-analysis').addEventListener('click',()=>{if(!state.busy){reset();closeLibrary();$('choose-file').focus();}});
$('view-original').addEventListener('click',()=>setView('original'));$('view-analyzed').addEventListener('click',()=>setView('analyzed'));
for(const side of ['left','right'])$(`arm-${side}`).addEventListener('click',()=>{state.side=side;$('arm-left').setAttribute('aria-pressed',String(side==='left'));$('arm-right').setAttribute('aria-pressed',String(side==='right'));renderSummary();renderFrame();});
$('play-toggle').addEventListener('click',()=>{const video=activeVideo();if(video.paused)video.play().catch(()=>showMessage('This video could not start playing. Try the downloaded MP4.'));else video.pause();});
$('scrubber').addEventListener('input',event=>seek(Number(event.target.value)));
$('step-back').addEventListener('click',()=>{activeVideo().pause();seek(activeVideo().currentTime-1/(state.job?.metadata?.fps||30));});
$('step-forward').addEventListener('click',()=>{activeVideo().pause();seek(activeVideo().currentTime+1/(state.job?.metadata?.fps||30));});
$('playback-speed').addEventListener('change',event=>videos.forEach(video=>video.playbackRate=Number(event.target.value)));
$('fullscreen').addEventListener('click',()=>{const video=activeVideo();if(video.requestFullscreen)video.requestFullscreen().catch(()=>{});else if(video.webkitEnterFullscreen)video.webkitEnterFullscreen();});
for(const event of ['dragenter','dragover'])$('drop-zone').addEventListener(event,e=>{e.preventDefault();if(!state.busy)$('drop-zone').classList.add('dragging');});
for(const event of ['dragleave','drop'])$('drop-zone').addEventListener(event,e=>{e.preventDefault();$('drop-zone').classList.remove('dragging');});
$('drop-zone').addEventListener('drop',event=>choose(event.dataTransfer.files[0]));
let chart={base:null,context:null,w:0,h:0,dpr:1,x:30,y:8,plotW:1,plotH:1,duration:1,ink:'#777'};
function drawBase(){
 const canvas=$('angle-chart'),rect=canvas.getBoundingClientRect();if(!rect.width||!rect.height)return;
 const dpr=Math.min(window.devicePixelRatio||1,2),w=rect.width,h=rect.height;
 canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);
 const base=document.createElement('canvas');base.width=canvas.width;base.height=canvas.height;const ctx=base.getContext('2d');ctx.scale(dpr,dpr);
 const style=getComputedStyle(document.documentElement),muted=style.getPropertyValue('--muted').trim(),line=style.getPropertyValue('--line').trim();
 chart={base,context:canvas.getContext('2d'),w,h,dpr,x:30,y:9,plotW:w-42,plotH:h-31,duration:state.data?Math.max((state.data.left.length-1)/state.data.fps,1/state.data.fps):1,ink:muted};
 ctx.font='9px -apple-system, sans-serif';ctx.fillStyle=muted;ctx.lineWidth=.5;
 for(const value of [0,90,180]){const yy=chart.y+chart.plotH*(1-value/180);ctx.strokeStyle=line;ctx.beginPath();ctx.moveTo(chart.x,yy);ctx.lineTo(chart.x+chart.plotW,yy);ctx.stroke();ctx.fillText(`${value}°`,0,yy+3);}
 if(state.data){
  for(const [side,token]of [['left','--left'],['right','--right']]){ctx.beginPath();let connected=false;state.data[side].forEach((v,i)=>{if(v===null){connected=false;return;}const x=chart.x+(i/state.data.fps)/chart.duration*chart.plotW,y=chart.y+chart.plotH*(1-v/180);if(connected)ctx.lineTo(x,y);else ctx.moveTo(x,y);connected=true;});ctx.strokeStyle=style.getPropertyValue(token).trim();ctx.lineWidth=1.3;ctx.stroke();}
  for(let i=0;i<=4;i++)ctx.fillText(`${(chart.duration*i/4).toFixed(1)}s`,chart.x+chart.plotW*i/4-8,h-2);
 }
 $('chart-empty').hidden=Boolean(state.data);drawCursor();
}
function drawCursor(){if(!chart.base)return;const ctx=chart.context;ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,chart.base.width,chart.base.height);ctx.drawImage(chart.base,0,0);if(!state.data)return;ctx.setTransform(chart.dpr,0,0,chart.dpr,0,0);const x=chart.x+Math.min(activeVideo().currentTime,chart.duration)/chart.duration*chart.plotW;ctx.strokeStyle=chart.ink;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x,chart.y-3);ctx.lineTo(x,chart.y+chart.plotH+3);ctx.stroke();}
new ResizeObserver(drawBase).observe($('angle-chart').parentElement);
let chartDragging=false;
function chartSeek(event){if(!state.data)return;const rect=$('angle-chart').getBoundingClientRect();seek((event.clientX-rect.left-chart.x)/chart.plotW*chart.duration);}
$('angle-chart').addEventListener('pointerdown',event=>{if(!state.data)return;chartDragging=true;event.currentTarget.setPointerCapture(event.pointerId);activeVideo().pause();chartSeek(event);});
$('angle-chart').addEventListener('pointermove',event=>{if(chartDragging)chartSeek(event);});
for(const event of ['pointerup','pointercancel'])$('angle-chart').addEventListener(event,()=>chartDragging=false);
function closeLibrary(){document.body.dataset.sidebarOpen='false';$('sidebar-toggle').setAttribute('aria-expanded','false');$('sidebar-scrim').hidden=true;$('workspace').inert=false;$('inspector').inert=false;const hidden=window.innerWidth<=900;document.querySelector('.library').inert=hidden;document.querySelector('.library').setAttribute('aria-hidden',String(hidden));}
function openLibrary(){document.querySelector('.library').inert=false;document.querySelector('.library').setAttribute('aria-hidden','false');document.body.dataset.sidebarOpen='true';$('sidebar-toggle').setAttribute('aria-expanded','true');$('sidebar-scrim').hidden=false;$('workspace').inert=true;$('inspector').inert=true;$('close-library').focus();}
$('sidebar-toggle').addEventListener('click',()=>document.body.dataset.sidebarOpen==='true'?closeLibrary():openLibrary());
$('sidebar-scrim').addEventListener('click',closeLibrary);$('close-library').addEventListener('click',()=>{closeLibrary();$('sidebar-toggle').focus();});
document.addEventListener('keydown',event=>{if(event.key==='Escape')closeLibrary();if(event.key==='Tab'&&document.body.dataset.sidebarOpen==='true'){const items=[...document.querySelector('.library').querySelectorAll('button:not(:disabled),a,select,summary')].filter(el=>el.getClientRects().length);const first=items[0],last=items.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}}});
window.matchMedia('(min-width:901px)').addEventListener('change',closeLibrary);
$('guide-link').addEventListener('click',()=>{$('recording-guide').open=true;if(window.innerWidth<=900)openLibrary();});
function applyTheme(value){if(value==='system')delete document.documentElement.dataset.theme;else document.documentElement.dataset.theme=value;$('theme-picker').value=value;try{localStorage.setItem('rom.theme',value);}catch{}drawBase();}
let preference='system';try{preference=localStorage.getItem('rom.theme')||'system';}catch{}applyTheme(['light','dark','system'].includes(preference)?preference:'system');
$('theme-picker').addEventListener('change',event=>applyTheme(event.target.value));window.matchMedia('(prefers-color-scheme:dark)').addEventListener('change',drawBase);
closeLibrary();renderLibrary();renderFrame();controls();
(async()=>{
 try{const config=await getJson('/api/config');state.maxBytes=config.max_upload_bytes;state.ready=config.model_ready;$('upload-limit').textContent=`Common video formats · Up to ${bytes(state.maxBytes)}`;if(!state.ready)showMessage('The analysis engine is not ready. Ask the server operator to run setup.');}
 catch{state.ready=false;showMessage('Cannot connect to the analysis server. Check that it is running.');}
 const id=new URLSearchParams(location.search).get('job');if(id&&/^[a-f0-9]{32}$/.test(id))poll(id);else controls();
})();
