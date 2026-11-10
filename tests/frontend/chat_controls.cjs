const assert = require('node:assert/strict');
const {JSDOM} = require('jsdom');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const dom = new JSDOM(`<section data-chat-root data-websocket-path="/ws/ia-integrations/chat-bot/"><form data-chat-form><textarea data-chat-input></textarea><button data-chat-send></button></form><div data-chat-messages></div><div data-chat-thinking hidden></div><div data-chat-status><strong></strong></div><button data-chat-clear></button></section>`, {runScripts:'outside-only',url:'http://localhost/'});
let socket;
class Socket {
  static OPEN=1;
  constructor(url) { this.readyState=1; this.listeners={}; this.sent=[]; socket=this; }
  addEventListener(name, fn) { this.listeners[name]=fn; }
  send(data) { this.sent.push(JSON.parse(data)); }
  receive(data) { this.listeners.message({data:JSON.stringify(data)}); }
}
const w=dom.window, d=w.document;
w.WebSocket=Socket;
w.eval(readFileSync(path.resolve(__dirname,'../../src/static/js/chat_bot.js'),'utf8'));
socket.receive({type:'chat.ready'});
const input=d.querySelector('textarea');
input.value='Crie uma questão';
d.querySelector('form').dispatchEvent(new w.Event('submit',{cancelable:true}));
const id=socket.sent[0].conversation_id;
socket.receive({type:'chat.response',conversation_id:id,message:'<img src=x onerror=alert(1)>',metadata:{sources:['Manual Lumini'],data:{limits:'30 registros',results:[{publication__title:'Atividade',score:0,maximum_score:2}]},proposal:{action:'create_question',subject:'Matemática',topic:'Soma',question:{statement:'2 + 2?',options:['4','5'],correct_answer:'4',explanation:'Soma',points:1}},confirmation_token:'token'}});
assert.equal(d.querySelector('img'),null);
assert.ok(d.querySelector('table').textContent.includes('0'));
assert.ok(d.body.textContent.includes('Resposta: 4'));
const save=d.querySelector('[data-chat-confirm]'); save.click();
assert.equal(socket.sent[1].type,'chat.confirm');
assert.equal(socket.sent[1].token,'token');
save.click(); assert.equal(socket.sent.length,2);
socket.receive({type:'chat.response',conversation_id:id,message:'Salva',metadata:{url:'/avaliacoes/questoes/1/editar/'}});
assert.equal(d.querySelector('a').getAttribute('href'),'/avaliacoes/questoes/1/editar/');
input.value='Nova proposta'; d.querySelector('form').dispatchEvent(new w.Event('submit',{cancelable:true}));
socket.receive({type:'chat.error',conversation_id:id,message:'Modelo indisponível'});
assert.equal(d.querySelector('[data-chat-thinking]').hidden,true);
d.querySelector('[data-chat-clear]').click();
assert.equal(d.querySelector('table'),null);
dom.window.close();console.log('Chat DOM: safe text, data tables, preview, confirmation once, result link, failure and clearing passed.');
