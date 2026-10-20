import {createModule} from './app.mjs';
import {Peer,DEFAULT_LIMITS,MAX_ID,application,grants,limits,exact,id,tagText,tagged,handle,failure,errorInfo,validError} from './browser-protocol.mjs';

const REQUIRED_CAPABILITIES=/*CAPABILITIES*/[];
let peer=null,state='created',budget=null,controller=null,requestCounter=0,callbackCounter=0,lastHandle=0,outputCount=0,eventCount=0;
const pending=new Map(),callbacks=new Map(),subscriptions=new Map();
let output=Promise.resolve(),events=Promise.resolve();
function close(reason='stop') {
  if(state==='closed')return;
  state='closed';controller?.abort();
  for(const entry of pending.values()){clearTimeout(entry.timer);entry.reject(failure('CANCELLED','Worker closed.','AbortError'));}
  pending.clear();callbacks.clear();subscriptions.clear();
  try{peer?.send('closed');}catch{}
  self.close();
}
function fatal(error) {
  if(state==='closed')return;
  try{peer?.send('fatal',{error:errorInfo(error)});}catch{}
  close('error');
}
function request(operation,args) {
  if(state!=='ready')return Promise.reject(failure('PROTOCOL','No host requests before ready.','ProtocolError','protocol'));
  if(pending.size>=budget.pending_requests||requestCounter>=MAX_ID)return Promise.reject(failure('QUOTA','Pending host request limit exceeded.'));
  const requestId='w'+(++requestCounter);
  return new Promise((resolve,reject)=>{
    const entry={resolve,reject,operation,args,done:false,timer:null};
    entry.timer=setTimeout(()=>{
      if(!pending.has(requestId)||entry.done)return;
      entry.done=true;reject(failure('TIMEOUT','Host request timed out.'));
      try{peer.send('cancel',{reply_to:requestId});}catch(error){fatal(error);}
      // Retain the slot until the peer's terminal reply or teardown.
    },budget.deadline_ms);
    pending.set(requestId,entry);
    try{peer.send('request',{id:requestId,operation,arguments:args,timeout_ms:budget.deadline_ms});}
    catch(error){clearTimeout(entry.timer);pending.delete(requestId);reject(error);}
  });
}
const host={request,
  registerCallback(fn) {
    if(typeof fn!=='function'||callbacks.size>=budget.subscriptions||callbackCounter>=MAX_ID)throw failure('QUOTA','Callback limit exceeded.');
    const wire={type:'handle',owner:'worker',kind:'callback',id:'w'+(++callbackCounter)};
    callbacks.set(wire.id,fn);return wire;
  },
  releaseCallback(wire){handle(wire,'worker','callback');callbacks.delete(wire.id);}
};
function write(value) {
  if(typeof value!=='string')throw failure('BAD_VALUE','Output requires text.');
  const taggedText=tagText(value);
  if(outputCount+taggedText.codepoints.length>budget.output_codepoints)throw failure('QUOTA','Output limit exceeded.');
  outputCount+=taggedText.codepoints.length;
  output=output.then(()=>request('output.write',{stream:'stdout',text:taggedText}));
  output.catch(fatal);
}
function result(message) {
  if(!id(message.reply_to,'w')||!pending.has(message.reply_to))throw failure('PROTOCOL','Duplicate or unknown host reply.','ProtocolError','protocol');
  const entry=pending.get(message.reply_to);
  if(Object.hasOwn(message,'error'))validError(message.error);else tagged(message.value,0,budget.value_depth);
  clearTimeout(entry.timer);pending.delete(message.reply_to);
  if(Object.hasOwn(message,'error')){if(!entry.done)entry.reject(message.error);return;}
  if(entry.operation==='events.subscribe') {
    handle(message.value,'main','event.subscription');
    const number=Number(message.value.id.slice(1));
    if(number<=lastHandle)throw failure('PROTOCOL','Reused main resource ID.','ProtocolError','protocol');
    lastHandle=number;
    if(entry.done){request('handles.release',{handles:[message.value]}).catch(fatal);return;}
    subscriptions.set(message.value.id,entry.args.callback.id);
  }
  if(entry.operation==='events.unsubscribe')subscriptions.delete(entry.args.subscription.id);
  if(entry.operation==='handles.release')for(const wire of entry.args.handles)subscriptions.delete(wire.id);
  if(!entry.done)entry.resolve(message.value);
}
function event(message) {
  handle(message.subscription,'main','event.subscription');handle(message.callback,'worker','callback');
  tagged(message.value,0,budget.value_depth);
  const expected=subscriptions.get(message.subscription.id);
  if(!expected){
    if(Number(message.subscription.id.slice(1))<=lastHandle)return;
    throw failure('PROTOCOL','Event references an unknown subscription.','ProtocolError','protocol');
  }
  if(expected!==message.callback.id)throw failure('PROTOCOL','Event callback does not own its subscription.','ProtocolError','protocol');
  if(!callbacks.has(expected))return;
  if(eventCount>=budget.pending_requests)throw failure('QUOTA','Event queue overflow.');
  eventCount++;
  events=events.then(async()=>{
    if(state!=='ready'||subscriptions.get(message.subscription.id)!==expected||!callbacks.has(expected))return;
    await callbacks.get(expected)(message.value);await output;
  }).finally(()=>{eventCount--;});
  events.catch(fatal);
}
async function initialize(message) {
  if(state!=='created')throw failure('PROTOCOL','Duplicate initialization.','ProtocolError','protocol');
  peer=new Peer(message.session,value=>self.postMessage(value));
  const init=peer.receive(message);if(!init||init.kind!=='init')throw failure('PROTOCOL','Worker requires init first.','ProtocolError','protocol');
  if(!exact(init.limits,Object.keys(DEFAULT_LIMITS)))throw failure('PROTOCOL','Init must declare every limit.','ProtocolError','protocol');
  state='initializing';const app=application(init.application),capabilities=grants(init.capabilities);budget=limits(init.limits);peer.budget=budget.message_bytes;
  if(REQUIRED_CAPABILITIES.some(name=>!capabilities.some(value=>value.id===name)))throw failure('UNAVAILABLE','A compiled application capability is missing.');
  controller=new AbortController();
  const module=createModule({write,signal:controller.signal,host});
  if(typeof module.main!=='function')throw failure('BAD_VALUE','Browser entry requires main().');
  state='ready';peer.send('ready',{application:app,capabilities:capabilities.map(value=>value.id),limits:budget});
  await module.main();await output;
}
self.onmessage=eventMessage=>{
  if(state==='closed')return;
  if(state==='created'){initialize(eventMessage.data).catch(fatal);return;}
  try{
    const message=peer.receive(eventMessage.data);if(!message)return;
    if(message.kind==='close'){
      if(!['stop','restart','completed','error'].includes(message.reason))throw failure('PROTOCOL','Invalid close reason.','ProtocolError','protocol');
      close(message.reason);return;
    }
    if(state!=='ready')throw failure('PROTOCOL','Host message before ready.','ProtocolError','protocol');
    if(message.kind==='result'){result(message);return;}
    if(message.kind==='event'){event(message);return;}
    throw failure('PROTOCOL','Unexpected host message.','ProtocolError','protocol');
  }catch(error){fatal(error);}
};
