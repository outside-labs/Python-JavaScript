export const PROTOCOL = 'pocket-python-host';
export const DEFAULT_LIMITS = Object.freeze({message_bytes:1048576,value_depth:64,pending_requests:32,subscriptions:32,output_codepoints:65536,response_bytes:1048576,deadline_ms:10000});
export const MAX_ID = 2147483647;
export const record = value => value!==null && typeof value==='object' && !Array.isArray(value);
export function failure(code,message,type='HostError',domain='host') {
  return Object.assign(new Error(message),{name:type,type,code,domain});
}
export function exact(value,keys) {
  return record(value) && Object.keys(value).length===keys.length && keys.every(key=>Object.hasOwn(value,key));
}
export function text(value,maximum=4096) { return typeof value==='string' && value.length<=maximum; }
export function id(value,prefix) { return typeof value==='string' && new RegExp('^'+prefix+'[1-9][0-9]*$').test(value) && Number(value.slice(1))<=MAX_ID; }
export function limits(input={}) {
  if(!record(input)||Object.keys(input).some(key=>!Object.hasOwn(DEFAULT_LIMITS,key)))throw failure('PROTOCOL','Unknown limits.','ProtocolError','protocol');
  const result={...DEFAULT_LIMITS,...input};
  if(Object.entries(result).some(([key,value])=>!Number.isSafeInteger(value)||value<1||value>DEFAULT_LIMITS[key]))throw failure('PROTOCOL','Limits must be positive and no larger than this adapter supports.','ProtocolError','protocol');
  return Object.freeze(result);
}
export function application(value) {
  if(!exact(value,['manifest_sha256','profile','profile_version','entrypoint','engine'])||
     !/^[0-9a-f]{64}$/.test(value.manifest_sha256)||value.profile!=='compiled-javascript'||value.profile_version!==1||value.entrypoint!=='app.mjs'||value.engine!==null) {
    throw failure('PROTOCOL','Unsupported compiled application identity.','ProtocolError','protocol');
  }
  return {...value};
}
export function grants(input) {
  if(!Array.isArray(input)||input.length>5)throw failure('PROTOCOL','Invalid capability grants.','ProtocolError','protocol');
  const seen=new Set();
  return input.map(value=>{
    if(!record(value)||!text(value.id,64)||seen.has(value.id))throw failure('PROTOCOL','Duplicate/invalid capability.','ProtocolError','protocol');
    seen.add(value.id);
    const fields={'output/1':['id'],'dom-text/1':['id','controls'],'dom-events/1':['id','controls','events'],'handles/1':['id'],'fetch/1':['id','urls']};
    if(!Object.hasOwn(fields,value.id)||!exact(value,fields[value.id]))throw failure('PROTOCOL','Unsupported capability shape.','ProtocolError','protocol');
    if(value.controls&&(!Array.isArray(value.controls)||value.controls.length>32||new Set(value.controls).size!==value.controls.length||value.controls.some(name=>!text(name,64)||!/^[A-Za-z][A-Za-z0-9_-]*$/.test(name))))throw failure('PROTOCOL','Invalid named controls.','ProtocolError','protocol');
    if(value.events&&(!Array.isArray(value.events)||value.events.length!==1||value.events[0]!=='click'))throw failure('PROTOCOL','Only click events are adopted.','ProtocolError','protocol');
    if(value.urls&&(!Array.isArray(value.urls)||value.urls.length>32||new Set(value.urls).size!==value.urls.length||value.urls.some(url=>{
      if(!text(url,2048))return true;
      try{const parsed=new URL(url);return !['http:','https:'].includes(parsed.protocol)||parsed.username||parsed.password||parsed.hash||parsed.href!==url;}catch{return true;}
    })))throw failure('PROTOCOL','Fetch requires exact normalized HTTP(S) URL grants.','ProtocolError','protocol');
    return structuredClone(value);
  });
}
export const tagText = value => ({type:'str',codepoints:Array.from(value,point=>point.codePointAt(0))});
export function untagText(value,maximum=1048576) {
  if(!exact(value,['type','codepoints'])||value.type!=='str'||!Array.isArray(value.codepoints)||value.codepoints.length>maximum||!Array.from(value.codepoints).every(point=>Number.isInteger(point)&&point>=0&&point<=0x10ffff))throw failure('BAD_VALUE','Expected a bounded code-point string.');
  const chunks=[];
  for(let index=0;index<value.codepoints.length;index+=1024)chunks.push(String.fromCodePoint(...value.codepoints.slice(index,index+1024)));
  return chunks.join('');
}
export const none = () => ({type:'none'});
export function handle(value,owner,kind) {
  if(!exact(value,['type','owner','kind','id'])||value.type!=='handle'||value.owner!==owner||value.kind!==kind||!id(value.id,owner==='main'?'m':'w'))throw failure('BAD_VALUE','Invalid resource handle.');
  return value;
}
export function tagged(value,depth=0,maxDepth=64) {
  if(depth>maxDepth||!record(value)||!text(value.type,16))throw failure('BAD_VALUE','Invalid tagged value.');
  if(value.type==='none'&&exact(value,['type']))return;
  if(value.type==='bool'&&exact(value,['type','value'])&&typeof value.value==='boolean')return;
  if(value.type==='int'&&exact(value,['type','value'])&&text(value.value,4097)&&/^(0|[1-9][0-9]*|-[1-9][0-9]*)$/.test(value.value))return;
  if(value.type==='float'&&exact(value,['type','bits'])&&typeof value.bits==='string'&&/^[0-9a-f]{16}$/.test(value.bits))return;
  if(value.type==='str'){untagText(value);return;}
  if(['tuple','list'].includes(value.type)&&exact(value,['type','items'])&&Array.isArray(value.items)&&value.items.length<=1024){for(const item of value.items)tagged(item,depth+1,maxDepth);return;}
  if(value.type==='dict'&&exact(value,['type','entries'])&&Array.isArray(value.entries)&&value.entries.length<=1024){
    for(const pair of value.entries){if(!Array.isArray(pair)||pair.length!==2)throw failure('BAD_VALUE','Invalid dict pair.');for(const item of pair)tagged(item,depth+1,maxDepth);}return;
  }
  if(value.type==='handle'&&['main','worker'].includes(value.owner)&&text(value.kind,64)){
    handle(value,value.owner,value.kind);return;
  }
  throw failure('BAD_VALUE','Unknown or malformed tagged value.');
}
export function errorInfo(error,domain='runtime') {
  const result={domain:error.domain||domain,code:typeof error.code==='string'?error.code:'RUNTIME',type:typeof error.type==='string'?error.type:typeof error.name==='string'?error.name:'RuntimeError',message:typeof error.message==='string'?error.message.slice(0,4096):'Operation failed.',frames:[]};
  const at=error.location;
  if(at&&text(at.filename,256)&&['line','column','end_line','end_column'].every(key=>Number.isSafeInteger(at[key])&&at[key]>0&&at[key]<=1000000))result.location={...at};
  return result;
}
export function validError(value) {
  if(!record(value)||!['protocol','host','runtime'].includes(value.domain)||!text(value.code,64)||!text(value.type,128)||!text(value.message,4096)||!Array.isArray(value.frames)||value.frames.length>128)throw failure('PROTOCOL','Malformed error packet.','ProtocolError','protocol');
  if(value.location!==undefined&&(!exact(value.location,['filename','line','column','end_line','end_column'])||!text(value.location.filename,256)||!['line','column','end_line','end_column'].every(key=>Number.isSafeInteger(value.location[key])&&value.location[key]>0&&value.location[key]<=1000000)||value.location.end_line<value.location.line||(value.location.end_line===value.location.line&&value.location.end_column<value.location.column)))throw failure('PROTOCOL','Invalid error location.','ProtocolError','protocol');
  if(Object.keys(value).some(key=>!['domain','code','type','message','location','frames'].includes(key)))throw failure('PROTOCOL','Unknown error fields.','ProtocolError','protocol');
}
export function equal(left,right) {
  const sorted=value=>Array.isArray(value)?value.map(sorted):record(value)?Object.fromEntries(Object.keys(value).sort().map(key=>[key,sorted(value[key])])):value;
  return JSON.stringify(sorted(left))===JSON.stringify(sorted(right));
}
export class Peer {
  constructor(session,post,budget=DEFAULT_LIMITS.message_bytes) {
    if(typeof session!=='string'||!/^[0-9a-f]{32}$/.test(session))throw failure('PROTOCOL','Invalid session.','ProtocolError','protocol');
    this.session=session;this.post=post;this.budget=budget;this.sent=0;this.received=0;
  }
  size(value) {
    let bytes;
    try{bytes=new TextEncoder().encode(JSON.stringify(value)).length;}catch{throw failure('PROTOCOL','Message is not a bounded plain value.','ProtocolError','protocol');}
    if(bytes>this.budget)throw failure('PROTOCOL','Message size exceeded.','ProtocolError','protocol');
  }
  send(kind,fields={}) {
    if(this.sent>=MAX_ID)throw failure('PROTOCOL','Sequence exhausted.','ProtocolError','protocol');
    const value={protocol:PROTOCOL,version:1,session:this.session,seq:this.sent+1,kind,...fields};
    this.size(value);this.sent++;this.post(value);
  }
  receive(value) {
    if(record(value)&&value.session!==this.session)return null;
    this.size(value);
    if(!record(value)||value.protocol!==PROTOCOL||value.version!==1||value.session!==this.session||value.seq!==this.received+1||value.seq>MAX_ID)throw failure('PROTOCOL','Invalid envelope or sequence.','ProtocolError','protocol');
    const base=['protocol','version','session','seq','kind'];
    const fields={init:['application','capabilities','limits'],ready:['application','capabilities','limits'],request:['id','operation','arguments','timeout_ms'],event:['subscription','callback','value'],cancel:['reply_to'],close:['reason'],closed:[],fatal:['error']};
    const extra=value.kind==='result'?(Object.hasOwn(value,'value')?['reply_to','value']:['reply_to','error']):Object.hasOwn(fields,value.kind)?fields[value.kind]:null;
    if(!extra||!exact(value,[...base,...extra]))throw failure('PROTOCOL','Unexpected message fields/kind.','ProtocolError','protocol');
    this.received++;return value;
  }
}
