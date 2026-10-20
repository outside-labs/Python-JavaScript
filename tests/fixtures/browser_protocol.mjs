import {test} from 'node:test';
import assert from 'node:assert/strict';
const {Peer,limits,grants,tagText,untagText,tagged,application}=await import(process.argv[2]);
const session='000102030405060708090a0b0c0d0e0f';
test('sessions and independent sequence counters reject replay and malformed envelopes',()=>{
  const sent=[],peer=new Peer(session,message=>sent.push(message));
  peer.send('closed');peer.send('closed');assert.equal(sent[1].seq,2);
  assert.equal(peer.receive({...sent[0],session:'f'.repeat(32)}),null);
  assert.equal(peer.received,0);assert.equal(peer.receive(sent[0]).kind,'closed');
  assert.throws(()=>peer.receive(sent[0]),{code:'PROTOCOL'});
  assert.throws(()=>peer.receive({...sent[1],extra:true}),{code:'PROTOCOL'});
  assert.equal(peer.received,1);
  assert.throws(()=>peer.receive({...sent[1],kind:'result',reply_to:'w1',value:{type:'none'},error:{}}),{code:'PROTOCOL'});
});
test('message, value and capability bounds are explicit',()=>{
  const peer=new Peer(session,()=>{},256);
  assert.throws(()=>peer.send('fatal',{error:{message:'x'.repeat(500)}}),{code:'PROTOCOL'});
  const cyclic={};cyclic.value=cyclic;assert.throws(()=>peer.size(cyclic),{code:'PROTOCOL'});
  assert.throws(()=>tagged({type:'int',value:'-0'}),{code:'BAD_VALUE'});
  assert.throws(()=>tagged({type:'constructor'}),{code:'BAD_VALUE'});
  assert.throws(()=>tagged({type:'str',codepoints:[0x110000]}),{code:'BAD_VALUE'});
  assert.throws(()=>limits({deadline_ms:10001}),{code:'PROTOCOL'});
  assert.throws(()=>limits({constructor:1}),{code:'PROTOCOL'});
  assert.throws(()=>grants([{id:'files/1'}]),{code:'PROTOCOL'});
  assert.throws(()=>grants([{id:'fetch/1',urls:['javascript:alert(1)']}]),{code:'PROTOCOL'});
  assert.throws(()=>grants([{id:'fetch/1',urls:['https://name:secret@example.test/']}]),{code:'PROTOCOL'});
});
test('Unicode transport preserves stored points and declares DOM projection',()=>{
  const value={type:'str',codepoints:[65,0x1f600,0xd83d,0xde00,0x301]};tagged(value);
  assert.deepEqual(value.codepoints,[65,0x1f600,0xd83d,0xde00,0x301]);
  assert.deepEqual(tagText(untagText(value)).codepoints,[65,0x1f600,0x1f600,0x301]);
});
test('compiled profile identity rejects interpreted engines and unknown formats',()=>{
  const app={manifest_sha256:'0'.repeat(64),profile:'compiled-javascript',profile_version:1,entrypoint:'app.mjs',engine:null};
  assert.deepEqual(application(app),app);
  assert.throws(()=>application({...app,engine:{implementation:'other'}}),{code:'PROTOCOL'});
  assert.throws(()=>application({...app,entrypoint:'https://example.test/main.mjs'}),{code:'PROTOCOL'});
});
