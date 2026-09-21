// v2: truncate to 100 Unicode code points, ASCII-escape JSON rows, sort ASCII rows.
// A checksum confirms consistency of editable content; it is not browser attestation.
export async function exportInventory(inventory){
  if(!Array.isArray(inventory)||inventory.length>250)throw Error('Expected up to 250 extensions');
  const clean=inventory.map(row=>{
    if(typeof row.name!=='string'||typeof row.enabled!=='boolean')throw Error('Invalid extension entry');
    return {name:Array.from(row.name).slice(0,100).join(''),enabled:row.enabled};
  });
  const rows=clean.map(row=>JSON.stringify([row.name,row.enabled])
    .replace(/[\u007f-\uffff]/g,c=>'\\u'+c.charCodeAt(0).toString(16).padStart(4,'0'))).sort();
  const bytes=new TextEncoder().encode('['+rows.join(',')+']');
  const hash=await crypto.subtle.digest('SHA-256',bytes);
  const digest=Array.from(new Uint8Array(hash),b=>b.toString(16).padStart(2,'0')).join('');
  return {format:'iim.extensions.v2',exported_at:new Date().toISOString(),self_reported:true,digest,extensions:clean};
}
