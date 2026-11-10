const assert = require('node:assert/strict');
const {JSDOM} = require('jsdom');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const dom = new JSDOM(`<section data-chat-root data-websocket-path="/ws/ia-integrations/chat-bot/"><button data-chat-mode="assembly" aria-pressed="false">Montagem</button><button data-chat-mode="doubts" aria-pressed="true">Dúvidas</button><button data-chat-mode="analysis" aria-pressed="false">Análise</button><p data-chat-mode-hint></p><form data-chat-form><textarea data-chat-input></textarea><button data-chat-send></button></form><div data-chat-messages></div><div data-chat-thinking hidden></div><div data-chat-status><strong></strong></div><button data-chat-clear></button></section>`, {runScripts:'outside-only',url:'http://localhost/'});
let socket;
class Socket {
  static OPEN=1;
  constructor(url) { this.readyState=1; this.listeners={}; this.sent=[]; socket=this; }
  addEventListener(name, fn) { this.listeners[name]=fn; }
  close() { this.readyState=3; if (this.listeners.close) this.listeners.close(); }
  send(data) { this.sent.push(JSON.parse(data)); }
  receive(data) { this.listeners.message({data:JSON.stringify(data)}); }
}
const w=dom.window, d=w.document;
w.WebSocket=Socket;
w.eval(readFileSync(path.resolve(__dirname,'../../src/static/js/chat_bot.js'),'utf8'));
w.confirm=()=>true;
socket.receive({type:'chat.ready', conversation_id:'saved-id', messages:[], timeout_seconds:120});
const input=d.querySelector('textarea');
d.querySelector('[data-chat-mode=assembly]').click();
assert.equal(d.querySelector('[data-chat-mode=assembly]').getAttribute('aria-pressed'),'true');
input.value='Crie uma questão';
d.querySelector('form').dispatchEvent(new w.Event('submit',{cancelable:true}));
const id=socket.sent[0].conversation_id;
assert.equal(socket.sent[0].mode,'assembly');
assert.equal(d.querySelector('[data-chat-mode=doubts]').disabled,true);
socket.receive({type:'chat.delta',conversation_id:id,message:'Resposta parcial <script>'});
assert.ok(d.body.textContent.includes('Resposta parcial'));
assert.equal(d.querySelector('script'),null);
assert.equal(d.querySelector('[data-chat-thinking]').hidden,false);
socket.receive({type:'chat.response',conversation_id:id,message:'<img src=x onerror=alert(1)>',metadata:{sources:['Manual Lumini'],data:{limits:'30 registros',results:[{publication__title:'Atividade',score:0,maximum_score:2}]},proposal:{action:'create_question',subject:'Matemática',topic:'Soma',question:{statement:'2 + 2?',options:['4','5'],correct_answer:'4',explanation:'Soma',points:1}},confirmation_token:'token'}});
assert.equal(d.querySelector('img'),null);
assert.ok(!d.body.textContent.includes('Resposta parcial'));
assert.ok(d.querySelector('table').textContent.includes('0'));
assert.ok(d.body.textContent.includes('Resposta: 4'));
const save=d.querySelector('[data-chat-confirm]'); save.click();
assert.equal(socket.sent[1].type,'chat.confirm');
assert.equal(socket.sent[1].token,'token');
save.click(); assert.equal(socket.sent.length,2);
socket.receive({type:'chat.response',conversation_id:id,message:'Salva',metadata:{url:'/avaliacoes/questoes/1/editar/'}});
assert.equal(d.querySelector('a').getAttribute('href'),'/avaliacoes/questoes/1/editar/');
d.querySelector('[data-chat-mode=doubts]').click();
assert.equal(d.querySelector('[data-chat-mode=doubts]').getAttribute('aria-pressed'),'true');
input.value='Nova proposta'; d.querySelector('form').dispatchEvent(new w.Event('submit',{cancelable:true}));
assert.equal(socket.sent.at(-1).mode,'doubts');
socket.receive({type:'chat.delta',conversation_id:id,message:'Rascunho interrompido'});
socket.receive({type:'chat.error',conversation_id:id,message:'Modelo indisponível'});
assert.ok(!d.body.textContent.includes('Rascunho interrompido'));
assert.equal(d.querySelector('[data-chat-thinking]').hidden,true);
d.querySelector('[data-chat-clear]').click();
assert.equal(socket.sent.at(-1).type, 'chat.clear');
socket.receive({type:'chat.cleared',conversation_id:'new-id'});
assert.equal(d.querySelector('table'),null);
// Reloaded messages are restored without a replayable action token.
socket.receive({type:'chat.ready',conversation_id:'new-id',messages:[{id:1,role:'user',content:'Persistida',metadata:{}},{id:2,role:'assistant',content:'Resposta salva',metadata:{mode:'assembly'}}]});
assert.ok(d.body.textContent.includes('Persistida'));
assert.ok(d.body.textContent.includes('Resposta salva'));
assert.equal(d.querySelector('[data-chat-mode=assembly]').getAttribute('aria-pressed'),'true');
socket.receive({type:'chat.response',conversation_id:'new-id',message:'Abra Questionários.',metadata:{sources:[],data:{user_id:1}}});
const last=d.querySelector('[data-chat-messages]').lastElementChild;
assert.equal(last.querySelector('details'),null);
assert.ok(!last.textContent.includes('Fontes consultadas:'));
d.querySelector('[data-chat-mode=analysis]').click();
assert.equal(d.querySelector('[data-chat-mode=analysis]').getAttribute('aria-pressed'),'true');
input.value='Falha visual';d.querySelector('form').dispatchEvent(new w.Event('submit',{cancelable:true}));
assert.equal(socket.sent.at(-1).mode,'analysis');
socket.receive({type:'chat.response',conversation_id:'new-id',message:'Texto válido',metadata:{sources:42}});
assert.equal(d.querySelector('[data-chat-thinking]').hidden,true);
let watchdog;
w.setTimeout=(fn)=>{watchdog=fn;return 99;};
input.value='Sem resposta';d.querySelector('form').dispatchEvent(new w.Event('submit',{cancelable:true}));
watchdog();
assert.equal(d.querySelector('[data-chat-thinking]').hidden,true);
assert.ok(d.body.textContent.includes('no prazo'));
assert.equal(socket.readyState,3);
dom.window.close();console.log('Chat DOM: safe text, data tables, preview, confirmation once, result link, failure and clearing passed.');
