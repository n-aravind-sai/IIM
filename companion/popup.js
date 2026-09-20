let inventory=[];
document.querySelector('#review').addEventListener('click',async()=>{
  const list=document.querySelector('#list');list.replaceChildren();
  try{
    inventory=(await chrome.management.getAll()).filter(e=>e.type==='extension'&&e.id!==chrome.runtime.id)
      .map(e=>({name:e.name,enabled:e.enabled,version:e.version}));
    for(const row of inventory){const li=document.createElement('li');li.textContent=`${row.name} (${row.enabled?'enabled':'disabled'})`;list.append(li);}
    document.querySelector('#export').disabled=false;
  }catch{const li=document.createElement('li');li.textContent='Inventory permission unavailable.';list.append(li);}
});
document.querySelector('#export').addEventListener('click',async()=>{
  const clean=inventory.map(e=>({name:(e.name||'').slice(0,100),enabled:Boolean(e.enabled)}));
  const sorted=clean.slice().sort((a,b)=>a.name.localeCompare(b.name));
  const canonicalRepr=JSON.stringify(sorted.map(e=>[e.name,e.enabled]));
  const msgBuffer=new TextEncoder().encode(canonicalRepr);
  const hashBuffer=await crypto.subtle.digest('SHA-256',msgBuffer);
  const digest=Array.from(new Uint8Array(hashBuffer)).map(b=>b.toString(16).padStart(2,'0')).join('');
  const data={format:'iim.extensions.v1',exported_at:new Date().toISOString(),self_reported:true,digest,extensions:inventory};
  const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download='candidate-extension-inventory.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1500);
});

