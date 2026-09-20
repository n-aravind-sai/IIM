const names = ['OverlayDetector','ProcessDetector','AudioCaptureDetector','GazeDetector','VirtualDisplayDetector','BrowserExtensionDetector'];
const scopes = ['windows','processes','audio_devices','gaze','displays','extensions'];
const emptyScore = {value:null,coverage:0,label:'Insufficient coverage',badge:'INSUFFICIENT_COVERAGE'};
export function demoClient(onSnapshot) {
  let state = {session_id:null,active:false,consent:{},results:[],history:[],timeline:[],score:emptyScore,elapsed_seconds:0};
  let started = 0;
  function event(title, detail) { state.timeline.unshift({time:new Date().toISOString(),title,detail}); }
  function refresh() {
    if (state.active) {
      state.elapsed_seconds = Math.floor((Date.now()-started)/1000);
      state.history.push({time:new Date().toISOString(),score:state.score.value,gaze:state.consent.gaze ? [82,85,79,88,84,81,78,83][state.history.length%8] : null});
      state.history = state.history.slice(-120);
    }
    onSnapshot(structuredClone(state));
  }
  setInterval(refresh,2000);
  return { async call(op,args={}) {
    if(op==='start') {
      if(args.consent?.accepted!==true) throw Error('Consent is required.');
      state = {session_id:'demo-7a9c2f',active:true,consent:args.consent,history:[],timeline:[],results:[],score:emptyScore,elapsed_seconds:0};
      started=Date.now();
      state.results=names.map((detector,i)=>({detector,status:args.consent[scopes[i]]?'partial':'disabled',detail:args.consent[scopes[i]]?'Synthetic sample for preview only.':'Candidate did not enable this scope.',signals:[],metrics:{}}));
      if(args.consent.windows) state.results[0].signals.push({id:'demo-overlay',detector:names[0],title:'Overlay-style window observed',confidence:.8,weight:.5,evidence:{topmost:true,layered:true,clickthrough:false},explanation:'Synthetic example: a window combines elevated stacking with overlay-like attributes.',limitation:'Captions, meeting controls and accessibility tools can produce the same properties.'});
      if(args.consent.processes) state.results[1].signals.push({id:'demo-process',detector:names[1],title:'Application name matches a review rule',confidence:.65,weight:.7,evidence:{process:'example-interview-assistant',source:'synthetic fixture'},explanation:'Synthetic example of an executable-name match.',limitation:'A matching name does not establish interview use. Names can be spoofed or changed.'});
      if(args.consent.gaze) {state.results[3].metrics={consistency:82,calibrated:true,quality:'synthetic',lighting:'normal',secondary_person:false};state.history=Array.from({length:28},(_,i)=>({time:new Date(Date.now()-(28-i)*2000).toISOString(),score:85,gaze:[87,84,79,83,81,75,82,88][i%8]}));}
      state.score={value:Math.round(100-(args.consent.windows?8:0)-(args.consent.processes?6.825:0)),coverage:Math.round(state.results.filter((r,i)=>i!==3&&r.status==='partial').length/10*100),label:'Review observations',badge:'OBSERVATIONS_FOR_REVIEW'};
      if(state.score.coverage===0)state.score={value:null,coverage:0,label:'Insufficient coverage',badge:'INSUFFICIENT_COVERAGE'};
      else if(!args.consent.windows&&!args.consent.processes){state.score.label='No matching observations';state.score.badge='PARTIAL_COVERAGE';}
      event('Session started','Synthetic session. No device monitoring takes place.');
      for(const r of state.results)for(const s of r.signals)event(s.title,s.explanation);
    } else if(op==='stop') {state.active=false;event('Monitoring stopped','Synthetic session ended.');}
    else if(op==='note') {if(!state.active)throw Error('Start a session first.');event('Candidate context',args.text);}
    else if(op==='mark') {if(!state.active)throw Error('Start a session first.');event(args.kind==='question_end'?'Question finished':'Answer started','Synthetic manual marker; excluded from index.');}
    else if(op==='extensions') {if(!state.active||!state.consent.extensions)throw Error('Enable extension consent at session start.');event('Extension inventory imported','Synthetic import demonstration.');}
    else if(op==='delete') {if(state.active)throw Error('Stop first.');state={session_id:null,active:false,consent:{},results:[],history:[],timeline:[],score:emptyScore,elapsed_seconds:0};}
    else if(op==='attestation') {
      if(!state.session_id) throw Error('No active or recent session to attest.');
      const pk = 'DEMO_Ed25519_PUBLIC_KEY_BASE64_ATTESTATION==';
      const head = '0'.repeat(64);
      const payload = JSON.stringify({id: state.session_id, pk, head});
      const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 33 33" shape-rendering="crispEdges" width="100%" height="100%"><rect width="33" height="33" fill="#ffffff"/><path d="M4,4h7v7h-7zM5,5h5v5h-5zM7,7h1v1h-1zM22,4h7v7h-7zM23,5h5v5h-5zM25,7h1v1h-1zM4,22h7v7h-7zM5,23h5v5h-5zM7,25h1v1h-1zM14,4h5v2h-5zM14,8h2v3h-2zM18,8h3v2h-3zM14,14h2v5h-2zM17,14h3v2h-3zM22,14h2v2h-2zM26,14h3v3h-3zM14,22h3v2h-3zM19,22h2v5h-2zM23,22h6v2h-6zM23,26h2v3h-2zM27,26h2v3h-2z" fill="#0c171c"/></svg>';
      return {session_id: state.session_id, public_key: pk, head, payload, svg};
    }
    else if(op==='export_json')return {format:'iim.demo.unsigned',synthetic:true,snapshot:structuredClone(state)};
    else if(op==='export_pdf')throw Error('PDF generation requires the local worker. This browser demo has no worker.');
    refresh();return structuredClone(state);
  }};
}
