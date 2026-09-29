// v2: truncate to 100 Unicode code points, ASCII-escape JSON rows, sort ASCII rows.
// A checksum confirms consistency of editable content; it is not browser attestation.
const asciiJson=value=>JSON.stringify(value).replace(/[\u007f-\uffff]/g,c=>'\\u'+c.charCodeAt(0).toString(16).padStart(4,'0'));
async function sha256(value){
  const hash=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value));
  return Array.from(new Uint8Array(hash),b=>b.toString(16).padStart(2,'0')).join('');
}
export async function exportInventory(inventory,scope=null){
  if(!Array.isArray(inventory)||inventory.length>250)throw Error('Expected up to 250 extensions');
  const clean=inventory.map(row=>{
    if(typeof row.name!=='string'||typeof row.enabled!=='boolean')throw Error('Invalid extension entry');
    return {name:Array.from(row.name).slice(0,100).join(''),enabled:row.enabled};
  });
  const rows=clean.map(row=>asciiJson([row.name,row.enabled])).sort();
  let digest=await sha256('['+rows.join(',')+']');
  if(scope){
    for(const key of ['session_id','browser','profile']){
      if(typeof scope[key]!=='string'||!scope[key].trim()||Array.from(scope[key]).length>100||/[\u0000-\u001f]/.test(scope[key]))throw Error('Enter the current session ID, browser and profile label.');
    }
    const exported_at=scope.exported_at||new Date().toISOString();
    if(!Number.isFinite(Date.parse(exported_at)))throw Error('Invalid inventory timestamp. Review again.');
    const format='iim.extensions.v3';
    digest=await sha256(asciiJson([format,scope.session_id,exported_at,scope.browser,scope.profile,digest]));
    return {format,session_id:scope.session_id,exported_at,browser:scope.browser,profile:scope.profile,self_reported:true,digest,extensions:clean};
  }
  return {format:'iim.extensions.v2',exported_at:new Date().toISOString(),self_reported:true,digest,extensions:clean};
}
