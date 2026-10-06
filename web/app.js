'use strict';
const $ = id => document.getElementById(id);
const state = { config: {version: 1, frames: []}, token: '', profiles: {}, source: null, image: null,
  rotation: 0, zoom: 1, x: .5, y: .5, job: null, busy: false, drag: null };
const canvas = $('crop-canvas'), ctx = canvas.getContext('2d');
const rotated = document.createElement('canvas');
const frame = () => state.config.frames.find(item => item.id === $('frame-select').value);
const fit = () => document.querySelector('input[name=fit]:checked').value;
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
function notify(message, kind = '') { $('status').textContent = message; $('status').className = kind; }
async function api(path, body, extra = {}) {
  const options = body === undefined ? {} : {method: 'POST', headers: {'X-Studio-Token': state.token, ...extra}, body: body instanceof File ? body : JSON.stringify(body)};
  if (body !== undefined && !(body instanceof File)) options.headers['Content-Type'] = 'application/json';
  const response = await fetch(path, options);
  let data;
  try { data = await response.json(); } catch { throw new Error('The local application did not respond. Check that gui.py is still running.'); }
  if (!response.ok) throw new Error(data.error || 'Request failed.');
  return data;
}
function refreshControls() {
  document.querySelectorAll('button, select, input').forEach(el => { el.disabled = state.busy; });
  $('convert').disabled = state.busy || !state.source || !frame() || !$('frame-manager').hidden;
  $('send').disabled = state.busy || !state.job || !$('frame-manager').hidden;
  const crop = fit() === 'crop';
  const backgroundAvailable = Boolean(state.source) && (!crop || state.source.transparent);
  $('background').disabled = state.busy || !backgroundAvailable;
  $('background-color').disabled = state.busy || !backgroundAvailable || $('background').value !== 'solid';
  $('background-angle').disabled = state.busy || !backgroundAvailable || $('background').value !== 'gradient';
  $('background-solid').classList.toggle('inactive-control', $('background-color').disabled);
  $('background-gradient').classList.toggle('inactive-control', $('background-angle').disabled);
  $('background-help').textContent = !state.source ? 'Choose an image to adjust its background.' : !backgroundAvailable
    ? 'This opaque image fills the frame. Choose Letterbox to reveal a background.'
    : 'One background fills transparent areas and the space around the image. Gradient direction: 0° right, 90° down.';
  canvas.classList.toggle('can-crop', crop && !state.busy && Boolean(state.source));
  canvas.setAttribute('aria-label', crop ? 'Crop preview. Drag to reposition; use arrow keys to move the image.' : 'Letterbox preview. The whole image stays centred.');
  $('zoom').disabled = state.busy || !crop || !state.source;
  $('reset-crop').disabled = state.busy || !crop || !state.source;
  $('rotate-left').disabled = $('rotate-right').disabled = state.busy || !state.source;
  $('fit-help').textContent = crop ? 'Fill the frame. Trim the edges.' : 'Keep the whole image. Fill the remaining space with your background.';
  $('crop-hint').textContent = crop ? 'Drag the image to reframe it. Scroll to zoom. Arrow keys also work.' : 'The whole image stays centred. Zoom is available in Crop mode.';
  $('busy-progress').hidden = !state.busy;
}
function setBusy(value) { state.busy = value; refreshControls(); }
function invalidate(message = 'Settings changed. Convert to update the preview.') {
  state.job = null;
  $('result-link').hidden = true; $('result-placeholder').hidden = false;
  $('download-bin').hidden = true;
  $('result-description').textContent = 'Your converted image will appear here, in the orientation of your frame.';
  $('send').innerHTML = 'Send to frame <span>↗</span>';
  if (state.source) notify(message);
  refreshControls();
}
function dimensions() {
  const f = frame(), base = f?.screen === '315' ? [1440, 2560] : [1200, 1600];
  return f?.orientation === 'landscape' ? base.reverse() : base;
}
function geometry() {
  const [w, h] = dimensions();
  const swap = state.rotation % 180 !== 0;
  const iw = swap ? state.source.height : state.source.width;
  const ih = swap ? state.source.width : state.source.height;
  const cw = Math.min(iw, ih * w / h) / state.zoom, ch = cw * h / w;
  return {iw, ih, cw, ch, left: (iw-cw)*state.x, top: (ih-ch)*state.y};
}
function prepareRotated() {
  if (!state.image) return;
  const img = state.image, swap = state.rotation % 180 !== 0;
  rotated.width = swap ? img.naturalHeight : img.naturalWidth;
  rotated.height = swap ? img.naturalWidth : img.naturalHeight;
  const r = rotated.getContext('2d');
  r.translate(rotated.width/2, rotated.height/2); r.rotate(state.rotation*Math.PI/180);
  r.drawImage(img, -img.naturalWidth/2, -img.naturalHeight/2);
}
function paintBackground(x, y, width, height) {
  if (!state.source) return;
  ctx.fillStyle = $('background-color').value;
  if ($('background').value === 'gradient') {
    const angle = Number($('background-angle').value)*Math.PI/180;
    const dx = Math.cos(angle), dy = Math.sin(angle);
    const span = Math.abs(dx)*width + Math.abs(dy)*height;
    const cx=x+width/2, cy=y+height/2;
    const gradient=ctx.createLinearGradient(cx-dx*span/2, cy-dy*span/2, cx+dx*span/2, cy+dy*span/2);
    state.source.background_colors.forEach((color, i)=>gradient.addColorStop(i, color));
    ctx.fillStyle=gradient;
  }
  ctx.fillRect(x,y,width,height);
}
function draw() {
  if (!state.image) return;
  const [w,h] = dimensions();
  canvas.width = Math.round(760*w/Math.max(w,h)); canvas.height = Math.round(760*h/Math.max(w,h));
  paintBackground(0,0,canvas.width,canvas.height);
  const g = geometry();
  if (fit() === 'crop') {
    ctx.drawImage(rotated, g.left/g.iw*rotated.width, g.top/g.ih*rotated.height,
      g.cw/g.iw*rotated.width, g.ch/g.ih*rotated.height, 0,0,canvas.width,canvas.height);
  } else {
    const scale = Math.min(w/g.iw,h/g.ih), pw = Math.max(1,Math.round(g.iw*scale)), ph = Math.max(1,Math.round(g.ih*scale));
    ctx.drawImage(rotated, Math.floor((w-pw)/2)/w*canvas.width, Math.floor((h-ph)/2)/h*canvas.height, pw/w*canvas.width, ph/h*canvas.height);
  }
  if (state.drag) {
    ctx.strokeStyle = 'rgba(255,255,255,.5)'; ctx.lineWidth = 1;
    for (let i=1; i<3; i++) { ctx.beginPath();ctx.moveTo(canvas.width*i/3,0);ctx.lineTo(canvas.width*i/3,canvas.height);ctx.stroke();ctx.beginPath();ctx.moveTo(0,canvas.height*i/3);ctx.lineTo(canvas.width,canvas.height*i/3);ctx.stroke(); }
  }
  $('zoom').value = state.zoom; $('zoom-value').textContent = state.zoom.toFixed(2)+'×';
}
function resetCrop() { state.zoom = 1; state.x = state.y = .5; draw(); }
function selectedFrameChanged() {
  const f = frame();
  $('frame-name-width').textContent = f?.name || 'Add your first frame';
  if (f) { const [w,h] = dimensions(); $('frame-details').textContent = `${f.screen === '315' ? '31.5' : '13.3'}″ · ${f.orientation} · ${w} × ${h} · ${f.host}`; }
  else $('frame-details').textContent = 'Add a frame to set the size and orientation.';
  try { localStorage.setItem('fraimic-frame', f?.id || ''); } catch {}
  resetCrop(); invalidate(); refreshControls();
}
function renderFrames(selected) {
  const select = $('frame-select'); select.replaceChildren();
  if (!state.config.frames.length) select.add(new Option('Add your first frame', ''));
  for (const f of state.config.frames) select.add(new Option(f.name, f.id));
  if (state.config.frames.some(f => f.id === selected)) select.value = selected;
  selectedFrameChanged();
}
function addFrameRow(item = {}) {
  const row = document.createElement('div'); row.className = 'frame-row'; row.dataset.id = item.id || '';
  // This template is fixed; names and hosts are assigned as values, never HTML.
  row.innerHTML = `<label>Friendly name<input name="name" type="text" maxlength="100" placeholder="Living room" required></label><label>Hostname / IP<input name="host" type="text" placeholder="fraimic.local" required></label><label>Panel<select name="screen"><option value="133">13.3″ · 1200×1600</option><option value="315">31.5″ · 1440×2560</option></select></label><label>Orientation<select name="orientation"><option value="portrait">Portrait</option><option value="landscape">Landscape</option></select></label><button class="text-button remove-frame" aria-label="Remove frame">Remove</button>`;
  for (const key of ['name','host','screen','orientation']) if (item[key]) row.querySelector(`[name=${key}]`).value = item[key];
  row.querySelector('button').onclick = () => { row.remove(); invalidate(); };
  row.addEventListener('input', () => invalidate());
  $('frame-list').append(row);
}
function openManager() {
  $('frame-list').replaceChildren(); state.config.frames.forEach(addFrameRow);
  if (!state.config.frames.length) addFrameRow();
  $('frame-manager').hidden = false; invalidate();
  $('frame-list').querySelector('input')?.focus();
}
$('manage-frames').onclick = openManager;
$('close-manager').onclick = () => { $('frame-manager').hidden = true; refreshControls(); };
$('add-frame').onclick = () => addFrameRow();
$('save-frames').onclick = async () => {
  const frames = [...document.querySelectorAll('.frame-row')].map(row => {
    const item = {id: row.dataset.id}; for (const key of ['name','host','screen','orientation']) item[key] = row.querySelector(`[name=${key}]`).value.trim(); return item;
  });
  for (const input of $('frame-list').querySelectorAll('input')) if (!input.reportValidity()) return;
  const selected = $('frame-select').value;
  setBusy(true);
  try { state.config = await api('/api/config', {version:1,frames}); $('frame-manager').hidden = true; renderFrames(selected); notify('Frames saved. Choose a photo to begin.', 'success'); }
  catch (error) { notify(error.message, 'error'); }
  finally { setBusy(false); }
};
$('frame-select').onchange = selectedFrameChanged;
const chooseFile = () => { if (!state.busy) $('file-input').click(); };
$('drop-zone').onclick = chooseFile; $('replace-image').onclick = chooseFile;
$('drop-zone').onkeydown = event => { if (['Enter',' '].includes(event.key)) {event.preventDefault(); chooseFile();} };
$('file-input').onchange = event => { if (event.target.files[0]) loadFile(event.target.files[0]); event.target.value=''; };
async function loadFile(file) {
  if (state.busy) return;
  if (file.size > 60*1024*1024) { notify('Please choose an image smaller than 60 MB.', 'error'); return; }
  invalidate(); setBusy(true); notify('Opening your image…');
  try {
    const source = await api('/api/images', file, {'X-Filename':encodeURIComponent(file.name),'Content-Type':'application/octet-stream'});
    const image = new Image(); image.src = source.url; await image.decode();
    state.source = source; state.image = image; state.rotation = 0; prepareRotated(); resetCrop();
    $('drop-zone').hidden = true; $('editor').hidden = false;
    $('image-name').textContent = source.name; $('image-size').textContent = `${source.width} × ${source.height}`;
    draw(); notify(frame() ? 'Reframe your photo, then convert to see the six-colour result.' : 'Image ready. Add a frame to continue.');
  } catch (error) { notify(error.message, 'error'); }
  finally { setBusy(false); }
}
const editorPanel = document.querySelector('.editor-panel');
window.addEventListener('dragover', event => { event.preventDefault(); });
window.addEventListener('drop', event => { event.preventDefault(); });
editorPanel.addEventListener('dragover', event => { event.preventDefault(); if (!state.busy) editorPanel.classList.add('dragging'); });
editorPanel.addEventListener('dragleave', event => { if (!editorPanel.contains(event.relatedTarget)) editorPanel.classList.remove('dragging'); });
editorPanel.addEventListener('drop', event => { event.preventDefault(); editorPanel.classList.remove('dragging'); if (event.dataTransfer.files.length !== 1) notify('Drop one image at a time.', 'error'); else loadFile(event.dataTransfer.files[0]); });
function rotate(delta) { if (state.busy || !state.image) return; state.rotation=(state.rotation+delta+360)%360; prepareRotated(); resetCrop(); invalidate(); }
$('rotate-left').onclick=()=>rotate(-90); $('rotate-right').onclick=()=>rotate(90);
$('reset-crop').onclick=()=>{resetCrop();invalidate();};
$('zoom').oninput=()=>{state.zoom=Number($('zoom').value);draw();invalidate();};
for (const radio of document.querySelectorAll('input[name=fit]')) radio.onchange=()=>{draw();invalidate();};
$('dither').onchange=()=>invalidate();
function applyProfile() {
  const profile = state.profiles[$('profile').value];
  if (!profile) return;
  $('profile-help').textContent = profile.description;
  for (const key of ['brightness','contrast','saturation']) {
    $(key).value = profile[key]; $(`${key}-value`).textContent = profile[key].toFixed(2);
  }
  invalidate('Colour look changed. Convert to see the result.');
}
$('profile').onchange = applyProfile;
for (const key of ['brightness','contrast','saturation']) $(key).oninput=()=>{$(`${key}-value`).textContent=Number($(key).value).toFixed(2);invalidate();};
canvas.addEventListener('pointerdown', event=>{
  if(state.busy || fit()!=='crop' || !state.source) return;
  const rect=canvas.getBoundingClientRect();
  state.drag={px:event.clientX,py:event.clientY,x:state.x,y:state.y,rect,g:geometry()};
  canvas.setPointerCapture(event.pointerId);draw();
});
canvas.addEventListener('pointermove', event=>{
  const d=state.drag;if(!d)return;
  state.x=clamp(d.x-(event.clientX-d.px)/d.rect.width*d.g.cw/Math.max(.001,d.g.iw-d.g.cw),0,1);
  state.y=clamp(d.y-(event.clientY-d.py)/d.rect.height*d.g.ch/Math.max(.001,d.g.ih-d.g.ch),0,1);
  draw();invalidate();
});
for(const name of ['pointerup','pointercancel','lostpointercapture']) canvas.addEventListener(name,()=>{state.drag=null;draw();});
canvas.addEventListener('wheel',event=>{if(state.busy||fit()!=='crop'||!state.source)return;event.preventDefault();state.zoom=clamp(state.zoom-event.deltaY*.002,1,4);draw();invalidate();},{passive:false});
canvas.addEventListener('keydown',event=>{
  if(state.busy||fit()!=='crop'||!state.source)return;
  const step=event.shiftKey ? .1 : .025;
  if(event.key==='ArrowLeft')state.x=clamp(state.x+step,0,1);
  else if(event.key==='ArrowRight')state.x=clamp(state.x-step,0,1);
  else if(event.key==='ArrowUp')state.y=clamp(state.y+step,0,1);
  else if(event.key==='ArrowDown')state.y=clamp(state.y-step,0,1);
  else return;
  event.preventDefault();draw();invalidate();
});
function settings() {return {background:$('background').value,background_color:$('background-color').value,background_angle:Number($('background-angle').value),profile:$('profile').value,fit:fit(),dither:$('dither').value,rotation:state.rotation,zoom:state.zoom,x:state.x,y:state.y,brightness:Number($('brightness').value),contrast:Number($('contrast').value),saturation:Number($('saturation').value)};}
async function waitForJob(job) {
  while(['converting','sending'].includes(job.status)) {
    await new Promise(resolve=>setTimeout(resolve,600)); job=await api('/api/jobs/'+job.id);
  }
  return job;
}
$('convert').onclick=async()=>{
  if(!frame()||!state.source||state.busy)return;
  invalidate();setBusy(true);notify($('dither').value==='fs'?'Converting your photo into six display colours…':'Converting your photo… This method can take a few minutes.');
  try {
    let job=await api('/api/convert',{frame_id:frame().id,source_id:state.source.id,settings:settings()});
    job=await waitForJob(job);if(job.status!=='ready')throw new Error(job.message);
    $('result-image').src=job.preview; await $('result-image').decode();
    state.job=job; $('result-link').href=job.preview; $('result-link').hidden=false; $('result-placeholder').hidden=true;
    $('download-bin').href=job.bin; $('download-bin').hidden=false;
    $('result-description').textContent=`${job.frame.name} · ${job.frame.orientation} · ${state.profiles[job.settings.profile].label} · ${(job.bytes/1000000).toFixed(2)} MB. The actual BIN, shown upright.`;
    notify(job.message,'success'); $('result-link').closest('section').scrollIntoView({behavior:'smooth',block:'nearest'});
  } catch(error){notify(error.message,'error');}
  finally{setBusy(false);}
};
$('send').onclick=async()=>{
  if(!state.job||state.busy)return;setBusy(true);notify('Sending to '+frame().name+'…');
  try{
    let job=await api('/api/send',{job_id:state.job.id,frame_id:frame().id});job=await waitForJob(job);state.job=job;
    if(job.status!=='sent')throw new Error(job.message);
    notify(job.message,'success');$('send').innerHTML='Send again <span>↗</span>';
  }catch(error){notify(error.message,'error');}
  finally{setBusy(false);}
};
(async()=>{
  try{const data=await api('/api/state');state.config=data.config;state.token=data.token;state.profiles=data.profiles;
    $('dither').replaceChildren(...Object.entries(data.dithers).map(([key,d])=>{const option=new Option(d.label+(d.available?'':' · not installed'),key);option.disabled=!d.available;return option;}));
    $('dither').value=data.default_dither;
    const explainDither=()=>{$('dither-help').textContent=data.dithers[$('dither').value].description;};
    $('dither').addEventListener('change',explainDither);explainDither();
    $('profile').replaceChildren(...Object.entries(data.profiles).map(([key,p])=>new Option(p.label,key)));
    $('profile').value=data.default_profile;applyProfile();$('config-path').textContent=data.config_path;
    let selected;try{selected=localStorage.getItem('fraimic-frame');}catch{}
    renderFrames(selected);if(!state.config.frames.length)openManager();
    if(!data.heic)notify('JPG and PNG are ready. Install pillow-heif to enable HEIC.');
  }catch(error){notify(error.message,'error');}
})();

for (const id of ['background', 'background-color', 'background-angle']) $(id).oninput=()=>{ $('background-angle-value').textContent=$('background-angle').value+'°'; draw(); invalidate(); };
