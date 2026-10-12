import {demoClient} from './demo.js';
const $ = selector => document.querySelector(selector);
const demo = new URLSearchParams(location.search).get('demo') === '1';
const labels = {OverlayDetector:'Window overlays',ProcessDetector:'Application names',AudioCaptureDetector:'Audio devices',GazeDetector:'Eye-position analysis',VirtualDisplayDetector:'Display adapters',BrowserExtensionDetector:'Browser extensions',RemoteSessionDetector:'Windows session protocol'};
const scopeLabels = {processes:'Application names',windows:'Window attributes',displays:'Display metadata',audio_devices:'Audio device names',extensions:'Browser inventory',gaze:'Optional camera',remote_sessions:'Windows session protocol'};
let client, snapshot, connected=false, toastTimer;
const defaultPolicy=()=>({version:1,phase:'discussion',allowed_apps:[],phase_apps:{},max_displays:null,context:''});
let policyDraft=defaultPolicy(),editingPolicy=null,editingRevision=null,editingSession=null;
function policyDescription(policy){
  if(!policy)return 'No session rules recorded.';
  const apps=[...policy.allowed_apps,...(policy.phase_apps[policy.phase]||[])];
  return `Phase: ${policy.phase.replace('_',' ')}. Permitted applications: ${apps.join(', ')||'none specified'}. Approval unverified: candidate-declared exceptions remain pending review and do not change the index. Display limit: ${policy.max_displays??'not specified'} (desktop monitor observations only; physical mirrors unknown).${policy.context?' Agreed context: '+policy.context:''}`;
}
function escape(value) {return String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function toast(message,error=false) {const el=$('#toast');el.textContent=message;el.classList.toggle('error',error);el.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.hidden=true,6500);}
function timeLabel(value){return new Date(value).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',second:'2-digit'});}
function setConnection(label,ok){connected=ok;$('#connection').textContent=label;$('#connection').className=`pill ${ok?'':'muted'}`;$('#start').disabled=!ok||Boolean(snapshot?.active||snapshot?.stopping);}

function render(data) {
  snapshot=data;
  const expanded=new Set([...document.querySelectorAll('.observation details[open]')].map(el=>el.parentElement.dataset.signal));
  const signals=data.results.flatMap(r=>r.signals);
  $('#session-status').textContent=data.cleanup_state==='failed'?'Cleanup failed — close the app':data.stopping?'Stopping monitoring':data.active?'Monitoring is visible':data.session_id?'Session ended':'Awaiting consent';
  $('#live-dot').classList.toggle('live',data.active);
  $('#session-id').textContent=data.session_id?`SESSION ${data.session_id.slice(0,8).toUpperCase()}`:'No active session';
  $('#inventory-session').value=data.active?data.session_id:'';
  const inventory=data.results.find(r=>r.detector==='BrowserExtensionDetector')?.metrics;
  $('#inventory-status').textContent=inventory?.format?`Latest import: ${inventory.browser||'unknown browser'} / ${inventory.profile||'unknown profile'}; ${inventory.freshness}. One declared profile; authenticity and completeness unverified.`:'No inventory imported for this session.';
  $('#elapsed').textContent=data.active?`${String(Math.floor(data.elapsed_seconds/60)).padStart(2,'0')}:${String(data.elapsed_seconds%60).padStart(2,'0')}`:data.session_id?'STOPPED':'00:00';
  $('#score').textContent=data.score.value??'—';
  $('#gauge-value').setAttribute('stroke-dashoffset',String(364.4*(1-(data.score.value??0)/100)));
  $('#score-label').textContent=data.session_id?data.score.label:'Ready when you are';
  const badgeMap={STANDARD_BASELINE:{label:'STANDARD BASELINE',class:'baseline'},OBSERVATIONS_FOR_REVIEW:{label:'REVIEW RECOMMENDED',class:'review'},PARTIAL_COVERAGE:{label:'PARTIAL COVERAGE',class:'partial'},INSUFFICIENT_COVERAGE:{label:'INCOMPLETE VISIBILITY',class:'partial'}};
  const b=data.session_id?(badgeMap[data.score?.badge]||{label:data.score?.label||'AWAITING CONSENT',class:'partial'}):{label:'AWAITING CONSENT',class:'partial'};
  const badgeEl=$('#status-badge');if(badgeEl){badgeEl.textContent=b.label;badgeEl.className=`status-pill ${b.class}`;}
  $('#signal-count').textContent=signals.length;
  $('#signal-caption').textContent=data.session_id?(signals.length?'Review evidence and candidate context':'No matching observations in available checks'):'Monitoring has not started';
  $('#coverage').textContent=data.score.coverage;
  $('#coverage-caption').textContent=`${data.results.filter(r=>['available','partial'].includes(r.status)).length} of ${Object.keys(labels).length} detectors returning data`;
  const gaps=data.coverage_gaps||[];
  $('#coverage-gap-notice').hidden=gaps.length===0;
  $('#coverage-gap-notice').textContent=gaps.length?`Measurements unavailable: ${gaps.map(g=>labels[g.detector]||g.detector).join(', ')}. These intervals are recorded as unknown coverage.`:'';
  $('#review-count').textContent=`${signals.length} ${data.active?'active':'in last sample'}`;
  $('#start').disabled=!connected||data.active||Boolean(data.stopping);$('#stop').disabled=!data.active;
  $('#delete').disabled=!data.session_id||data.active||Boolean(data.stopping);
  $('#attest-btn').disabled=!data.session_id;
  for(const id of ['export-json','export-pdf'])$(`#${id}`).disabled=!data.session_id;
  for(const id of ['save-note','question','answer'])$(`#${id}`).disabled=!data.active;
  $('#report-title').textContent=data.stopping?'Session cleanup needs to finish':data.session_id&&!data.active?'Session summary ready':'Your session, your record';
  $('#report-caption').textContent=data.cleanup_state==='failed'?'Cleanup or the final audit failed. Close the app; any verified export may be incomplete.':data.stopping?'Releasing devices and saving the final audit.':data.session_id&&!data.active?'Monitoring has stopped. Review context, export your record, or delete the session.':'Export observations, limitations and the signed audit history.';
  $('#source-groups').innerHTML=(data.review_groups||[]).map(group=>`<div class="card-note"><b>Shared Windows process source</b><p>${escape(group.detectors.map(name=>labels[name]||name).join(' + '))} · ${group.signal_ids.length} observations. The index avoids adding duplicate deductions when its strongest observations share this source. This does not authenticate software or establish intent.</p></div>`).join('');
  $('#signals').innerHTML=signals.length?signals.map(s=>`<div class="observation" data-signal="${escape(s.id)}"><h3>${escape(s.title)}</h3><p>${escape(s.explanation)}</p><div class="evidence">${escape(Object.entries(s.evidence).map(([k,v])=>`${k}: ${typeof v==='object'?JSON.stringify(v):v}`).join(' · '))}</div><details ${expanded.has(s.id)?'open':''}><summary>Why this may be legitimate</summary><p>${escape(s.limitation)}</p></details><div class="meta"><span>${escape(labels[s.detector]||s.detector)}</span><span>Observation confidence ${Math.round(s.confidence*100)}% · heuristic</span></div></div>`).join(''):`<div class="empty"><span>◇</span><h3>${data.session_id?'No matching observations':'No observations yet'}</h3><p>${data.session_id?'Check the coverage panel for unavailable or disabled detectors. Absence of signals does not establish absence of assistance.':'Monitoring starts only after the candidate selects scopes and gives consent.'}</p></div>`;
  const results=data.results.length?data.results:Object.keys(labels).map(detector=>({detector,status:'disabled',detail:'Awaiting candidate consent.'}));
  $('#detectors').innerHTML=results.map(r=>`<div class="detector-row" data-detector="${escape(r.detector)}" data-status="${escape(r.status)}"><div><b>${escape(labels[r.detector]||r.detector)}</b><small>${escape(r.detail)}</small></div><span class="pill ${r.status==='partial'?'warn':r.status==='available'?'':'muted'}">${escape(r.status)}</span></div>`).join('');
  $('#timeline').innerHTML=data.timeline.length?data.timeline.map(e=>`<div class="timeline-item"><time>${escape(timeLabel(e.time))}</time><div><b>${escape(e.title)}</b><p>${escape(e.detail)}</p></div></div>`).join(''):'<div class="empty"><h3>Your timeline starts here</h3><p>Consent, observations and candidate context will appear during a session.</p></div>';
  $('#consent-summary').innerHTML=Object.entries(scopeLabels).map(([scope,label])=>`<div class="consent-row"><b>${label}</b><span>${data.consent[scope]?'Selected':'Not selected'}</span></div>`).join('');
  $('#policy-summary').textContent=policyDescription(data.policy||policyDraft);
  $('#policy-btn').disabled=demo||Boolean(data.stopping);
  renderGaze(data);
}

function renderGaze(data){
  const r=data.results.find(r=>r.detector==='GazeDetector');
  const points=data.history.map((p,i)=>p.gaze===null?null:[12+i*576/Math.max(data.history.length-1,1),140-p.gaze*1.2]);
  let segments=[],segment=[];
  for(const p of points){if(p)segment.push(p);else if(segment.length){segments.push(segment);segment=[];}}if(segment.length)segments.push(segment);
  $('#gaze-chart').innerHTML=[20,80,140].map(y=>`<line x1="12" x2="588" y1="${y}" y2="${y}" stroke="#25333f" stroke-dasharray="4 5"/>`).join('')+segments.map(s=>`<polyline points="${s.map(p=>p.join(',')).join(' ')}" fill="none" stroke="#68dbc1" stroke-width="2"/>`).join('');
  $('#gaze-empty').hidden=segments.some(s=>s.length>1);
  $('#gaze-badge').textContent=!data.consent.gaze?'Off':r?.status==='error'?'Unavailable':r?.status==='waiting'?'Measurements unavailable':r?.metrics?.calibrated?'Experimental':'Calibrating';
  if(data.consent.gaze&&!$('#gaze-empty').hidden)$('#gaze-empty').innerHTML=r?.status==='error'?'Camera unavailable. You can continue without it.':'Waiting for reliable samples.<br><small>Look comfortably at your screen; calibration needs 50 stable samples.</small>';
  if(!data.consent.gaze)$('#gaze-empty').innerHTML='Enable optional camera analysis at session start.<br><small>No camera images are stored or shared.</small>';
}

async function rpc(op,args){
  if(!client)throw Error('The local worker is not connected. Start the desktop app or use the documented development launcher.');
  const result=await client.call(op,args);
  if(result?.results)render(result);
  return result;
}
async function action(task){try{return await task();}catch(error){toast(error.message||String(error),true);}}
for(const b of document.querySelectorAll('[data-view]'))b.addEventListener('click',()=>{
  for(const el of document.querySelectorAll('[data-view]'))el.classList.toggle('active',el===b);
  for(const view of document.querySelectorAll('.view'))view.hidden=view.id!==`view-${b.dataset.view}`;
});
$('#start').addEventListener('click',()=>{$('#accepted').checked=false;$('#consent-policy-summary').textContent=policyDescription(policyDraft);$('#consent-dialog').showModal();});
$('#cancel-consent').addEventListener('click',()=>$('#consent-dialog').close());
$('#consent-form').addEventListener('submit',event=>{event.preventDefault();action(async()=>{
  const form=new FormData(event.currentTarget);const consent={accepted:form.has('accepted'),version:'iim-consent-4'};
  for(const key of Object.keys(scopeLabels))consent[key]=form.has(key);
  if(!Object.keys(scopeLabels).some(key=>consent[key]))throw Error('Select at least one monitoring scope.');
  await rpc('start',{consent,policy:policyDraft});policyDraft=defaultPolicy();$('#consent-dialog').close();toast(demo?'Synthetic demo started. No monitoring is taking place.':'Selected monitoring checks started.');
});});
$('#policy-btn').addEventListener('click',()=>{
  editingPolicy=structuredClone(snapshot?.active?snapshot.policy:policyDraft);
  editingRevision=snapshot?.active?snapshot.policy.revision:null;
  editingSession=snapshot?.active?snapshot.session_id:null;
  $('#policy-phase').value=editingPolicy.phase;
  $('#policy-apps').value=editingPolicy.allowed_apps.join(', ');
  $('#policy-phase-apps').value=(editingPolicy.phase_apps[editingPolicy.phase]||[]).join(', ');
  $('#policy-displays').value=editingPolicy.max_displays??'';
  $('#policy-context').value=editingPolicy.context;
  $('#policy-accepted').checked=false;
  $('#policy-dialog').showModal();
});
$('#policy-phase').addEventListener('change',()=>{
  editingPolicy.phase_apps[editingPolicy.phase]=$('#policy-phase-apps').value.split(',').map(s=>s.trim()).filter(Boolean);
  editingPolicy.phase=$('#policy-phase').value;
  $('#policy-phase-apps').value=(editingPolicy.phase_apps[editingPolicy.phase]||[]).join(', ');
});
$('#cancel-policy').addEventListener('click',()=>$('#policy-dialog').close());
$('#policy-form').addEventListener('submit',event=>{event.preventDefault();action(async()=>{
  if(!$('#policy-accepted').checked)throw Error('Confirm that these rules were agreed before saving.');
  const phase=$('#policy-phase').value;
  const policy={version:1,phase,allowed_apps:$('#policy-apps').value.split(',').map(s=>s.trim()).filter(Boolean),
    phase_apps:{...editingPolicy.phase_apps,[phase]:$('#policy-phase-apps').value.split(',').map(s=>s.trim()).filter(Boolean)},
    max_displays:$('#policy-displays').value?Number($('#policy-displays').value):null,context:$('#policy-context').value};
  if(editingSession){
    if(!snapshot?.active||snapshot.session_id!==editingSession)throw Error('The session changed. Reopen the rules to review them.');
    await rpc('policy',{policy,expected_session_id:editingSession,expected_revision:editingRevision,accepted:true});
  }else{policyDraft=policy;$('#policy-summary').textContent=policyDescription(policyDraft);}
  $('#policy-dialog').close();toast(editingSession?'Agreed rules updated in the signed audit.':'Rules prepared for the next consented session.');
});});
$('#stop').addEventListener('click',()=>action(async()=>{stopPreflight();await rpc('stop');toast('Monitoring stopped. Your session summary is ready.');}));
$('#save-note').addEventListener('click',()=>action(async()=>{const text=$('#context-note').value.trim();if(!text)throw Error('Enter a note first.');await rpc('note',{text});$('#context-note').value='';toast('Candidate context added to the timeline.');}));
$('#question').addEventListener('click',()=>action(()=>rpc('mark',{kind:'question_end'})));
$('#answer').addEventListener('click',()=>action(()=>rpc('mark',{kind:'answer_start'})));
$('#delete').addEventListener('click',()=>action(async()=>{if(confirm('Delete this session’s locally stored observations, consent and notes? Exported files are not deleted.')){await rpc('delete');toast('Session deleted from the app.');}}));
$('#extension-file').addEventListener('change',event=>action(async()=>{const file=event.target.files[0];if(!file)return;if(file.size>60000)throw Error('Inventory file is too large (maximum 60 KB).');const data=JSON.parse(await file.text());await rpc('extensions',{entries:data});event.target.value='';toast('Candidate-supplied inventory imported.');}));
async function saveFile(bytes,name,type){
  if(window.__TAURI__&&!demo){const path=await window.__TAURI__.core.invoke('save_export',{name,bytes:Array.from(bytes)});toast(`Saved to ${path}`);return;}
  const url=URL.createObjectURL(new Blob([bytes],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
$('#export-json').addEventListener('click',()=>action(async()=>{const data=await rpc('export_json');await saveFile(new TextEncoder().encode(JSON.stringify(data,null,2)),`${demo?'demo-unsigned':'integrity'}-${snapshot.session_id}.json`,'application/json');}));
$('#export-pdf').addEventListener('click',()=>action(async()=>{const data=await rpc('export_pdf');const bytes=Uint8Array.from(atob(data.base64),c=>c.charCodeAt(0));await saveFile(bytes,data.filename,'application/pdf');}));

let currentAttestation=null;
$('#attest-btn').addEventListener('click',()=>action(async()=>{
  const res=await rpc('attestation');
  currentAttestation=res;
  $('#attest-session-id').textContent=res.session_id||'—';
  $('#attest-public-key').textContent=res.public_key||'—';
  $('#attest-head').textContent=res.head||'—';
  const qrWrap=$('#attest-qr-wrap');
  if(qrWrap)qrWrap.innerHTML=res.svg||'<div class="subtle">Attestation ready</div>';
  $('#attestation-dialog').showModal();
}));
$('#close-attestation')?.addEventListener('click',()=>$('#attestation-dialog').close());
$('#copy-attest')?.addEventListener('click',async()=>{
  if(!currentAttestation)return;
  const text=currentAttestation.payload||JSON.stringify({id:currentAttestation.session_id,pk:currentAttestation.public_key,head:currentAttestation.head},null,2);
  await navigator.clipboard.writeText(text);
  toast('Verification payload copied to clipboard.');
});


let preflightStream=null,audioCtx=null,animFrame=null,preflightGeneration=0;
async function startPreflight(){
  if(demo){toast('Device checks are disabled in the synthetic demo.');return;}
  const dialog=$('#preflight-dialog');if(!dialog||dialog.open)return;
  const generation=++preflightGeneration;
  dialog.showModal();
  $('#preflight-cam-status').textContent='Requesting camera & microphone...';
  $('#preflight-mic-status').textContent='Connecting audio meter...';
  try{
    const stream=await navigator.mediaDevices.getUserMedia({video:true,audio:true});
    if(generation!==preflightGeneration||!dialog.open){stream.getTracks().forEach(t=>t.stop());return;}
    preflightStream=stream;
    const video=$('#preflight-video');if(video)video.srcObject=preflightStream;
    $('#preflight-cam-status').textContent='Camera active (local preview only)';
    try{
      audioCtx=new (window.AudioContext||window.webkitAudioContext)();
      const source=audioCtx.createMediaStreamSource(preflightStream);
      const analyser=audioCtx.createAnalyser();
      analyser.fftSize=256;source.connect(analyser);
      const dataArray=new Uint8Array(analyser.frequencyBinCount);
      const updateMeter=()=>{
        if(generation!==preflightGeneration||!preflightStream)return;
        analyser.getByteFrequencyData(dataArray);
        let sum=0;for(let i=0;i<dataArray.length;i++)sum+=dataArray[i];
        const average=sum/dataArray.length;
        const level=Math.min(100,Math.round((average/128)*100));
        const bar=$('#preflight-meter-bar');
        if(bar){bar.style.width=`${level}%`;bar.parentElement?.setAttribute('aria-valuenow',String(level));}
        animFrame=requestAnimationFrame(updateMeter);
      };
      updateMeter();
      $('#preflight-mic-status').textContent='Microphone live. Level responds to your voice.';
    }catch(e){$('#preflight-mic-status').textContent='Microphone active (meter unavailable).';}
    if(navigator.mediaDevices.enumerateDevices){
      const devices=await navigator.mediaDevices.enumerateDevices();
      if(generation!==preflightGeneration||!dialog.open)return;
      const vCount=devices.filter(d=>d.kind==='videoinput').length;
      const aCount=devices.filter(d=>d.kind==='audioinput').length;
      $('#preflight-device-list').innerHTML=`<li>${vCount} camera${vCount===1?'':'s'} available</li><li>${aCount} microphone${aCount===1?'':'s'} available</li><li>Hardware check passed</li>`;
    }
  }catch(err){
    if(generation!==preflightGeneration||!dialog.open)return;
    releasePreflightResources();
    $('#preflight-cam-status').textContent='Camera/Microphone permission denied or unavailable.';
    $('#preflight-mic-status').textContent='Device access required for pre-flight test.';
    $('#preflight-device-list').innerHTML=`<li>Notice: ${escape(err.message||'Permission denied')}</li>`;
  }
}
function releasePreflightResources(){
  if(animFrame){cancelAnimationFrame(animFrame);animFrame=null;}
  if(audioCtx){audioCtx.close().catch(()=>{});audioCtx=null;}
  if(preflightStream){preflightStream.getTracks().forEach(t=>t.stop());preflightStream=null;}
  const video=$('#preflight-video');if(video)video.srcObject=null;
  const bar=$('#preflight-meter-bar');if(bar){bar.style.width='0%';bar.parentElement?.setAttribute('aria-valuenow','0');}
}
function stopPreflight(){
  preflightGeneration++;
  releasePreflightResources();
  const dialog=$('#preflight-dialog');if(dialog?.open)dialog.close();
}
$('#preflight-btn')?.addEventListener('click',startPreflight);
$('#close-preflight')?.addEventListener('click',stopPreflight);
$('#preflight-dialog')?.addEventListener('close',()=>{if(!$('#preflight-dialog').open)stopPreflight();});
window.addEventListener('pagehide',stopPreflight);
window.addEventListener('beforeunload',stopPreflight);

let reconnectTimer=null,reconnectAttempts=0;
let devBootstrapSecret=null;
async function fetchBootstrap(){
  if(window.__TAURI__)return await window.__TAURI__.core.invoke('bootstrap');
  if(devBootstrapSecret===null){
    devBootstrapSecret=new URLSearchParams(location.hash.slice(1)).get('bootstrap')||'';
    if(devBootstrapSecret)history.replaceState(null,'',location.pathname+location.search);
  }
  if(!devBootstrapSecret)throw Error('Open the private dashboard link printed by scripts/dev.py, or use the desktop app.');
  const r=await fetch('/bootstrap.json',{cache:'no-store',headers:{Authorization:`Bearer ${devBootstrapSecret}`}});
  if(!r.ok)throw Error('Development authorization failed. Reopen the private link from the current launcher.');
  return await r.json();
}
function scheduleReconnect(){
  if(reconnectTimer||demo)return;
  const delay=Math.min(1000*(2**reconnectAttempts),8000);
  reconnectAttempts++;
  setConnection(`Reconnecting in ${Math.round(delay/1000)}s...`,false);
  reconnectTimer=setTimeout(()=>{reconnectTimer=null;connect().catch(()=>{});},delay);
}

async function connect(){
  if(demo){$('#demo-banner').hidden=false;$('#export-json').textContent='↓ Demo JSON';client=demoClient(render);setConnection('Synthetic demo',true);render(await client.call('snapshot'));return;}
  clearTimeout(reconnectTimer);
  let info;
  try{info=await fetchBootstrap();}catch(err){scheduleReconnect();throw err;}
  if(!/^ws:\/\/127\.0\.0\.1:\d+$/.test(info.endpoint)){scheduleReconnect();throw Error('Invalid local worker endpoint.');}
  const ws=new WebSocket(info.endpoint);const pending=new Map();let serial=0,heartbeat;
  client={call(op,args={}){return new Promise((resolve,reject)=>{if(ws.readyState!==WebSocket.OPEN){reject(Error('Worker disconnected.'));return;}const id=String(++serial);const timeout=setTimeout(()=>{pending.delete(id);reject(Error('Worker response timed out.'));},15000);pending.set(id,{resolve,reject,timeout});ws.send(JSON.stringify({id,op,args}));});}};
  ws.addEventListener('open',()=>{reconnectAttempts=0;ws.send(JSON.stringify({token:info.token}));});
  ws.addEventListener('message',event=>{
    const msg=JSON.parse(event.data);
    if(msg.type==='ready'){setConnection('Local worker connected',true);render(msg.snapshot);heartbeat=setInterval(()=>rpc('heartbeat').catch(()=>{}),4000);}
    if(msg.type==='snapshot')render(msg.snapshot);
    if(msg.type==='response'){const p=pending.get(msg.id);if(p){clearTimeout(p.timeout);pending.delete(msg.id);msg.error?p.reject(Error(msg.error)):p.resolve(msg.result);}}
    if(msg.type==='fatal')toast(msg.error,true);
  });
  ws.addEventListener('close',()=>{
    clearInterval(heartbeat);
    setConnection('Disconnected · reconnecting...',false);
    for(const p of pending.values()){clearTimeout(p.timeout);p.reject(Error('Worker disconnected.'));}
    pending.clear();
    $('#stop').disabled=true;
    $('#session-status').textContent='Disconnected — last received data';
    $('#live-dot').classList.remove('live');
    scheduleReconnect();
  });
  window.addEventListener('beforeunload',()=>ws.close());
}
render({session_id:null,active:false,consent:{},results:[],timeline:[],history:[],score:{value:null,coverage:0,label:'Insufficient coverage',badge:'INSUFFICIENT_COVERAGE'},elapsed_seconds:0});
connect().catch(error=>{setConnection('Local worker not connected',false);toast(error.message||String(error),true);});
