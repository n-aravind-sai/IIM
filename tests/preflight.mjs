import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {test} from 'node:test';
// Production handlers, mocked DOM/devices/RPC. No copied lifecycle implementation.
const source=readFileSync(new URL('../web/app.js',import.meta.url),'utf8').replace(/^import .*\n/,'').split('render({session_id:null')[0];
function fixture(demo=false){
 const elements=new Map(),pending=[],frames=new Map();let requests=0,closedAudio=0;
 function element(id){if(!elements.has(id))elements.set(id,{open:false,style:{},setAttribute(){},parentElement:{setAttribute(){}},classList:{toggle(){}},listeners:{},addEventListener(t,f){this.listeners[t]=f;},showModal(){this.open=true;},close(){this.open=false;},srcObject:null});return elements.get(id);}
 const window={listeners:{},addEventListener(t,f){this.listeners[t]=f;},AudioContext:class{createMediaStreamSource(){return {connect(){}};}createAnalyser(){return {frequencyBinCount:8,getByteFrequencyData(){}};}close(){closedAudio++;return Promise.resolve();}}};
 const mediaDevices={getUserMedia(){requests++;return new Promise((resolve,reject)=>pending.push({resolve,reject}));},enumerateDevices:async()=>[]};
 const context=vm.createContext({window,document:{querySelector:element,querySelectorAll:()=>[]},location:{search:demo?'?demo=1':''},URLSearchParams,structuredClone,navigator:{mediaDevices},setTimeout:()=>1,clearTimeout(){},requestAnimationFrame(f){frames.set(frames.size+1,f);return frames.size;},cancelAnimationFrame(id){frames.delete(id);}});
 vm.runInContext(source,context);vm.runInContext('client={call:async()=>({})}',context);
 return {context,element,pending,frames,window,mediaDevices,get requests(){return requests;},get closedAudio(){return closedAudio;},start:()=>vm.runInContext('startPreflight()',context),stop:()=>vm.runInContext('stopPreflight()',context)};
}
function stream(){const tracks=[{stopped:0,stop(){this.stopped++;}},{stopped:0,stop(){this.stopped++;}}];return {tracks,getTracks:()=>tracks};}
function stopped(s){assert.ok(s.tracks.every(t=>t.stopped===1));}

function renderState(f, overrides={}){
 f.context.state={session_id:'fixture',active:false,consent:{},results:[],timeline:[],history:[],score:{value:null,coverage:0},...overrides};
 vm.runInContext('connected=true; render(state)',f.context);
}

test('policy submission binds the edit to the opened session and revision',async()=>{
 const f=fixture();
 renderState(f,{session_id:'session-a',active:true,policy:{version:1,revision:3,phase:'discussion',allowed_apps:[],phase_apps:{},max_displays:null,context:''}});
 f.context.calls=[];
 vm.runInContext('client={call:async(op,args)=>{calls.push({op,args});return {};}}',f.context);
 f.element('#policy-btn').listeners.click();
 f.element('#policy-apps').value='otter.exe';
 f.element('#policy-accepted').checked=true;
 f.element('#policy-form').listeners.submit({preventDefault(){}});
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(f.context.calls.length,1);
 const {op,args}=f.context.calls[0];
 assert.equal(op,'policy');
 assert.equal(args.expected_session_id,'session-a');
 assert.equal(args.expected_revision,3);
});
test('cleanup in progress blocks restart and deletion without claiming a ready summary',()=>{
 const f=fixture();renderState(f,{stopping:true,cleanup_state:'in_progress'});
 assert.equal(f.element('#start').disabled,true);assert.equal(f.element('#delete').disabled,true);
 assert.equal(f.element('#session-status').textContent,'Stopping monitoring');
 assert.notEqual(f.element('#report-title').textContent,'Session summary ready');
});
test('failed cleanup stays visible and blocks restart after reconnection',()=>{
 const f=fixture();renderState(f,{stopping:true,cleanup_state:'failed'});
 vm.runInContext("setConnection('Connected',true)",f.context);
 assert.equal(f.element('#start').disabled,true);
 assert.equal(f.element('#session-status').textContent,'Cleanup failed — close the app');
});
test('open coverage gaps are visible independently of the capped timeline',()=>{
 const f=fixture();renderState(f,{active:true,coverage_gaps:[{detector:'ProcessDetector',status:'error'}]});
 assert.equal(f.element('#coverage-gap-notice').hidden,false);
 assert.match(f.element('#coverage-gap-notice').textContent,/Application names/);
 renderState(f,{active:true,coverage_gaps:[]});assert.equal(f.element('#coverage-gap-notice').hidden,true);
});

test('shared-source groups are visible, escaped and cleared when unavailable',()=>{
 const f=fixture();renderState(f,{active:true,review_groups:[{source_ref:'a'.repeat(64),detectors:['ProcessDetector','<img src=x>'],signal_ids:['a','b']}]});
 assert.match(f.element('#source-groups').innerHTML,/Shared Windows process source/);
 assert.match(f.element('#source-groups').innerHTML,/Application names/);
 assert.match(f.element('#source-groups').innerHTML,/&lt;img src=x&gt;/);
 assert.doesNotMatch(f.element('#source-groups').innerHTML,/<img/);
 renderState(f,{active:true,review_groups:[]});assert.equal(f.element('#source-groups').innerHTML,'');
});
test('late permission after close releases all tracks',async()=>{const f=fixture(),p=f.start(),s=stream();f.stop();f.pending[0].resolve(s);await p;stopped(s);assert.equal(f.element('#preflight-video').srcObject,null);assert.equal(f.frames.size,0);});
test('stale request and queued close cannot disrupt reopened preview',async()=>{
 const f=fixture(),old=f.start();f.stop();const current=f.start(),a=stream(),b=stream();f.pending[1].resolve(b);await current;f.pending[0].resolve(a);await old;
 stopped(a);assert.equal(f.element('#preflight-video').srcObject,b);assert.equal(b.tracks[0].stopped,0);f.element('#preflight-dialog').listeners.close();assert.equal(f.element('#preflight-video').srcObject,b);f.stop();stopped(b);assert.equal(f.closedAudio,1);
});
test('repeated open starts only one request',async()=>{const f=fixture(),p=f.start();await f.start();assert.equal(f.requests,1);f.stop();f.pending[0].resolve(stream());await p;});
test('stale rejection leaves current preview intact',async()=>{const f=fixture(),p=f.start();f.stop();const q=f.start(),s=stream();f.pending[1].resolve(s);await q;f.pending[0].reject(Error('denied'));await p;assert.equal(f.element('#preflight-video').srcObject,s);f.stop();stopped(s);});
test('enumeration error releases resources',async()=>{const f=fixture();f.mediaDevices.enumerateDevices=async()=>{throw Error('device error');};const p=f.start(),s=stream();f.pending[0].resolve(s);await p;stopped(s);assert.equal(f.closedAudio,1);assert.equal(f.frames.size,0);});
for(const event of ['pagehide','beforeunload'])test(`${event} cancels pending and active previews`,async()=>{for(const acquired of [false,true]){const f=fixture(),p=f.start(),s=stream();if(acquired){f.pending[0].resolve(s);await p;}f.window.listeners[event]();if(!acquired){f.pending[0].resolve(s);await p;}stopped(s);assert.equal(f.element('#preflight-video').srcObject,null);}});
test('session stop releases devices even with failed worker RPC',async()=>{const f=fixture(),p=f.start(),s=stream();f.pending[0].resolve(s);await p;vm.runInContext('client={call:async()=>{throw Error("offline")}}',f.context);await f.element('#stop').listeners.click();stopped(s);assert.equal(f.element('#preflight-dialog').open,false);});
test('native dialog close releases active devices',async()=>{const f=fixture(),p=f.start(),s=stream();f.pending[0].resolve(s);await p;const d=f.element('#preflight-dialog');d.open=false;d.listeners.close();stopped(s);});
test('demo never requests hardware',async()=>{const f=fixture(true);await f.start();assert.equal(f.requests,0);});
