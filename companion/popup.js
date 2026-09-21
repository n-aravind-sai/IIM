import {exportInventory} from './inventory.js';
let inventory=[];
document.querySelector('#review').addEventListener('click',async()=>{
  const list=document.querySelector('#list');list.replaceChildren();
  try{
    inventory=(await chrome.management.getAll()).filter(e=>e.type==='extension'&&e.id!==chrome.runtime.id)
      .map(e=>({name:e.name,enabled:e.enabled}));
    for(const row of inventory){const li=document.createElement('li');li.textContent=`${row.name} (${row.enabled?'enabled':'disabled'})`;list.append(li);}
    document.querySelector('#export').disabled=false;
  }catch{const li=document.createElement('li');li.textContent='Inventory permission unavailable.';list.append(li);}
});
document.querySelector('#export').addEventListener('click',async()=>{
  const data=await exportInventory(inventory);
  const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download='candidate-extension-inventory.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1500);
});

