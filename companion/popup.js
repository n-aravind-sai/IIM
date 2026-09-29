import {exportInventory} from './inventory.js';
let inventory=[],reviewedAt=null;
document.querySelector('#review').addEventListener('click',async()=>{
  const list=document.querySelector('#list');list.replaceChildren();
  inventory=[];reviewedAt=null;document.querySelector('#export').disabled=true;
  try{
    inventory=(await chrome.management.getAll()).filter(e=>e.type==='extension'&&e.id!==chrome.runtime.id)
      .map(e=>({name:e.name,enabled:e.enabled}));
    for(const row of inventory){const li=document.createElement('li');li.textContent=`${row.name} (${row.enabled?'enabled':'disabled'})`;list.append(li);}
    reviewedAt=new Date().toISOString();document.querySelector('#export').disabled=false;
  }catch{const li=document.createElement('li');li.textContent='Inventory permission unavailable.';list.append(li);}
});
document.querySelector('#export').addEventListener('click',async()=>{
  const error=document.querySelector('#error');error.textContent='';
  let data;
  try{
    if(!reviewedAt||Date.now()-Date.parse(reviewedAt)>=300000)throw Error('Inventory expired. Review extensions again.');
    data=await exportInventory(inventory,{session_id:document.querySelector('#session').value.trim(),
      browser:document.querySelector('#browser').value.trim(),profile:document.querySelector('#profile').value.trim(),exported_at:reviewedAt});
  }catch(e){error.textContent=e.message;return;}
  const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download='candidate-extension-inventory.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1500);
});
