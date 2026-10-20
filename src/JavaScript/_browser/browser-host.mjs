import {Peer,DEFAULT_LIMITS,MAX_ID,application,grants,limits,record,exact,text,id,tagText,untagText,handle,none,failure,errorInfo,validError,equal} from './browser-protocol.mjs';

// The caller supplies verified application identity and trusted DOM bindings.
export function mountCompiledApplication(options) {
  const app=application(options.application), capabilities=grants(options.capabilities), budget=limits(options.limits);
  const bindings=options.controls||{}, eventInputs=options.eventInputs||{};
  const granted=new Map(capabilities.map(value=>[value.id,value]));
  for(const grant of capabilities)for(const control of grant.controls||[]){
    if(!Object.hasOwn(bindings,control)||!(bindings[control] instanceof Element))throw new TypeError('Bind every granted control to an Element.');
  }
  for(const [button,input] of Object.entries(eventInputs))if(!granted.get('dom-events/1')?.controls.includes(button)||!granted.get('dom-text/1')?.controls.includes(input))throw new TypeError('Event snapshots require granted button/input controls.');
  if(granted.has('output/1')&&!(options.output instanceof Element))throw new TypeError('Output requires a trusted text container.');
  const session=Array.from(crypto.getRandomValues(new Uint8Array(16)),value=>value.toString(16).padStart(2,'0')).join('');
  const worker=new Worker(new URL('./browser-worker.mjs',import.meta.url),{type:'module'});
  const peer=new Peer(session,value=>worker.postMessage(value),budget.message_bytes);
  const pending=new Map(), subscriptions=new Map();
  let state='initializing',lastRequest=0,nextHandle=0,outputCount=0,resolveReady,rejectReady;
  const ready=new Promise((resolve,reject)=>{resolveReady=resolve;rejectReady=reject;});
  // A caller may install UI handlers before awaiting ready; retain the rejection.
  ready.catch(()=>{});
  const initTimer=setTimeout(()=>fatal(failure('TIMEOUT','Worker initialization timed out.')),budget.deadline_ms);
  const writeError=error=>{
    const info=errorInfo(error);
    if(typeof options.onError==='function')options.onError(info);
    else if(options.output instanceof Element)options.output.append(document.createTextNode(info.type+': '+info.message+'\n'));
  };
  function dispose(reason='stop') {
    if(state==='closed')return;
    const before=state;state='closed';clearTimeout(initTimer);
    for(const item of pending.values()){clearTimeout(item.timer);item.controller.abort();}
    pending.clear();
    for(const item of subscriptions.values())item.element.removeEventListener('click',item.listener);
    subscriptions.clear();
    try{peer.send('close',{reason});}catch{}
    worker.onmessage=null;worker.onerror=null;worker.terminate();
    if(before==='initializing')rejectReady(failure('CANCELLED','Worker initialization stopped.','AbortError'));
  }
  function fatal(error) {
    if(state==='closed')return;
    rejectReady(error);dispose('error');writeError(error);
  }
  const control=(name,capability)=>{
    if(!text(name,64)||!granted.get(capability)?.controls.includes(name))throw failure('DENIED','Control is outside its granted capability.');
    return bindings[name];
  };
  const read=element=>'value' in element?String(element.value):element.textContent;
  const write=(element,value)=>{if('value' in element)element.value=value;else element.textContent=value;};
  const requireCapability=name=>{if(!granted.has(name))throw failure('UNAVAILABLE','Capability is not granted: '+name);};
  const unsubscribe=wire=>{
    handle(wire,'main','event.subscription');
    const entry=subscriptions.get(wire.id);
    if(!entry)throw failure('STALE_HANDLE','Subscription has been released.');
    entry.element.removeEventListener('click',entry.listener);subscriptions.delete(wire.id);
  };
  async function dispatch(operation,args,signal) {
    if(signal.aborted||state==='closed')throw failure('CANCELLED','Host operation cancelled.','AbortError');
    if(!record(args))throw failure('BAD_VALUE','Host arguments must be a plain record.');
    if(operation==='output.write') {
      requireCapability('output/1');
      if(!exact(args,['stream','text'])||!['stdout','stderr'].includes(args.stream))throw failure('BAD_VALUE','Invalid output arguments.');
      const value=untagText(args.text,budget.output_codepoints),count=args.text.codepoints.length;
      if(outputCount+count>budget.output_codepoints)throw failure('QUOTA','Output limit exceeded.');
      outputCount+=count;options.output.append(document.createTextNode(value));return none();
    }
    if(operation==='dom.read') {
      requireCapability('dom-text/1');if(!exact(args,['control']))throw failure('BAD_VALUE','Invalid read arguments.');
      const value=tagText(read(control(args.control,'dom-text/1')));
      if(value.codepoints.length>budget.output_codepoints)throw failure('QUOTA','Control text exceeds its limit.');
      return value;
    }
    if(operation==='dom.write') {
      requireCapability('dom-text/1');if(!exact(args,['control','text']))throw failure('BAD_VALUE','Invalid write arguments.');
      const element=control(args.control,'dom-text/1'),value=untagText(args.text,budget.output_codepoints);write(element,value);return none();
    }
    if(operation==='events.subscribe') {
      requireCapability('dom-events/1');requireCapability('handles/1');
      if(!exact(args,['control','event','callback'])||args.event!=='click')throw failure('BAD_VALUE','Only a named click subscription is supported.');
      handle(args.callback,'worker','callback');
      const element=control(args.control,'dom-events/1');
      if(subscriptions.size>=budget.subscriptions||nextHandle>=MAX_ID)throw failure('QUOTA','Subscription limit exceeded.');
      const wire={type:'handle',owner:'main',kind:'event.subscription',id:'m'+(++nextHandle)};
      const listener=()=>{
        if(state!=='ready'||!subscriptions.has(wire.id))return;
        try{
          const input=Object.hasOwn(eventInputs,args.control)?eventInputs[args.control]:null;
          const value=tagText(input?read(control(input,'dom-text/1')):'');
          if(value.codepoints.length>budget.output_codepoints)throw failure('QUOTA','Event text exceeds its limit.');
          peer.send('event',{subscription:wire,callback:args.callback,value});
        }catch(error){fatal(error);}
      };
      element.addEventListener('click',listener);subscriptions.set(wire.id,{element,listener,callback:args.callback});return wire;
    }
    if(operation==='events.unsubscribe') {
      requireCapability('dom-events/1');requireCapability('handles/1');
      if(!exact(args,['subscription']))throw failure('BAD_VALUE','Invalid unsubscribe arguments.');
      unsubscribe(args.subscription);return none();
    }
    if(operation==='handles.release') {
      requireCapability('handles/1');
      if(!exact(args,['handles'])||!Array.isArray(args.handles)||args.handles.length>budget.subscriptions)throw failure('BAD_VALUE','Invalid handle release.');
      for(const wire of args.handles){handle(wire,'main','event.subscription');if(subscriptions.has(wire.id))unsubscribe(wire);}
      return none();
    }
    if(operation==='fetch.text') {
      requireCapability('fetch/1');
      if(!exact(args,['url','method'])||!text(args.url,2048)||args.method!=='GET')throw failure('BAD_VALUE','The first Fetch adapter accepts GET text only.');
      let url;
      try{url=new URL(args.url,location.href);}catch{throw failure('BAD_VALUE','Invalid Fetch URL.');}
      if(url.username||url.password||url.hash||!granted.get('fetch/1').urls.includes(url.href))throw failure('DENIED','URL is outside the exact Fetch grant.');
      try {
        const response=await fetch(url.href,{method:'GET',credentials:'omit',redirect:'error',signal});
        const reader=response.body?.getReader(),parts=[];let bytes=0;
        if(reader)try{
          while(true){const {done,value}=await reader.read();if(done)break;bytes+=value.byteLength;
            if(bytes>budget.response_bytes){await reader.cancel();throw failure('QUOTA','Fetch response exceeds its byte limit.');}parts.push(value);}
        }finally{reader.releaseLock();}
        const body=new Uint8Array(bytes);let offset=0;for(const part of parts){body.set(part,offset);offset+=part.length;}
        const value=new TextDecoder('utf-8',{fatal:true}).decode(body);
        return {type:'dict',entries:[['status',{type:'int',value:String(response.status)}],['url',tagText(response.url)],['text',tagText(value)]].map(([key,item])=>[tagText(key),item])};
      }catch(error){if(error.code==='QUOTA')throw error;if(signal.aborted)throw failure('CANCELLED','Fetch cancelled.','AbortError');throw failure('IO','Fetch failed.','FetchError');}
    }
    throw failure('UNAVAILABLE','Host operation is not implemented.');
  }
  function settle(request,value,error) {
    const entry=pending.get(request);if(!entry||state==='closed')return;
    clearTimeout(entry.timer);pending.delete(request);
    try{peer.send('result',{reply_to:request,...(error?{error:errorInfo(error,'host')}:{value})});}catch(caught){
      if(!error)try{peer.send('result',{reply_to:request,error:errorInfo(failure('QUOTA','Result exceeds its message limit.'),'host')});return;}catch{}
      fatal(caught);
    }
  }
  function request(message) {
    if(!id(message.id,'w')||Number(message.id.slice(1))<=lastRequest||!text(message.operation,64)||!Number.isSafeInteger(message.timeout_ms)||message.timeout_ms<1)throw failure('PROTOCOL','Invalid or repeated request.','ProtocolError','protocol');
    lastRequest=Number(message.id.slice(1));
    if(pending.size>=budget.pending_requests){peer.send('result',{reply_to:message.id,error:errorInfo(failure('QUOTA','Pending request limit exceeded.'),'host')});return;}
    const controller=new AbortController();
    const timer=setTimeout(()=>{controller.abort();settle(message.id,null,failure('TIMEOUT','Host operation timed out.'));},Math.min(message.timeout_ms,budget.deadline_ms));
    pending.set(message.id,{controller,timer});
    Promise.resolve().then(()=>dispatch(message.operation,message.arguments,controller.signal)).then(value=>settle(message.id,value),error=>settle(message.id,null,error));
  }
  worker.onmessage=event=>{
    if(state==='closed')return;
    try{
      const message=peer.receive(event.data);if(!message)return;
      if(message.kind==='ready'&&state==='initializing') {
        application(message.application);
        if(!exact(message.limits,Object.keys(DEFAULT_LIMITS)))throw failure('PROTOCOL','Ready must report every effective limit.','ProtocolError','protocol');
        if(!Array.isArray(message.capabilities)||message.capabilities.some(value=>typeof value!=='string')||!equal(message.application,app)||!equal(message.capabilities,capabilities.map(value=>value.id))||!equal(limits(message.limits),budget))throw failure('PROTOCOL','Worker ready identity mismatch.','ProtocolError','protocol');
        state='ready';clearTimeout(initTimer);resolveReady();return;
      }
      if(message.kind==='fatal'){validError(message.error);fatal(message.error);return;}
      if(state!=='ready')throw failure('PROTOCOL','Worker request before ready.','ProtocolError','protocol');
      if(message.kind==='request'){request(message);return;}
      if(message.kind==='cancel') {
        if(!id(message.reply_to,'w')||Number(message.reply_to.slice(1))>lastRequest)throw failure('PROTOCOL','Unknown cancellation ID.','ProtocolError','protocol');
        const entry=pending.get(message.reply_to);if(entry){entry.controller.abort();settle(message.reply_to,null,failure('CANCELLED','Host operation cancelled.','AbortError'));}return;
      }
      throw failure('PROTOCOL','Unexpected worker message.','ProtocolError','protocol');
    }catch(error){fatal(error);}
  };
  worker.onerror=()=>fatal(failure('IO','Compiled worker failed to load or execute.','RuntimeError','runtime'));
  try{peer.send('init',{application:app,capabilities,limits:budget});}catch(error){fatal(error);}
  return Object.freeze({ready,stop:()=>dispose('stop'),restart:()=>{dispose('restart');return mountCompiledApplication(options);},
    stats:()=>({state,session,pending:pending.size,subscriptions:subscriptions.size,handles:subscriptions.size})});
}
