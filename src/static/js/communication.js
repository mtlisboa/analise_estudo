(function () {
 function init() {
 document.querySelectorAll('.chat-window[data-chat-updates]').forEach(function (windowEl) {
  if (windowEl.dataset.connected) return;
  windowEl.dataset.connected = 'true';
  var log = windowEl.querySelector('.chat-messages');
  var form = windowEl.querySelector('.chat-send');
  var status = form.querySelector('.chat-status');
  var body = form.querySelector('[name=body]');
  var nonce = form.querySelector('[name=nonce]');
  var csrf = form.querySelector('[name=csrfmiddlewaretoken]').value;
  var last = Math.max(0, ...Array.from(log.querySelectorAll('[data-message-id]')).map(function (el) { return Number(el.dataset.messageId); }));
  var first = Math.min(...Array.from(log.querySelectorAll('[data-message-id]')).map(function (el) { return Number(el.dataset.messageId); }));
  log.querySelectorAll('time[datetime]').forEach(function (time) { time.textContent=new Date(time.dateTime).toLocaleString('pt-BR'); });
  var busy = false, stopped = false;
  function markRead() {
   if (!last || document.hidden || windowEl.closest('[hidden]')) return;
   fetch(windowEl.dataset.chatRead, {method:'POST',headers:{'X-CSRFToken':csrf},body:new URLSearchParams({last_id:String(last)})}).then(function (response) { if (response.ok) { var badge=windowEl.closest('.communication').querySelector('nav a[aria-current] strong'); if (badge) badge.remove(); } }).catch(function () {});
  }
  function bubble(message) {
   var article = document.createElement('article');
   article.className = 'chat-bubble' + (message.mine ? ' mine' : ''); article.dataset.messageId = message.id;
   var author = document.createElement('strong'); author.textContent = message.author;
   var text = document.createElement('p'); text.textContent = message.body;
   var time = document.createElement('time'); time.dateTime = message.time; time.textContent = new Date(message.time).toLocaleString('pt-BR');
   article.append(author,text,time); return article;
  }
  function append(message) {
   if (log.querySelector('[data-message-id="'+message.id+'"]')) return;
   var empty = log.querySelector('.chat-empty'); if (empty) empty.remove();
   log.appendChild(bubble(message)); last = Math.max(last,message.id); first = Math.min(first,message.id);
  }
  async function poll() {
   if (busy || stopped || document.hidden || windowEl.closest('[hidden]')) return;
   busy = true;
   try {
    var response = await fetch(windowEl.dataset.chatUpdates+'?after='+last);
    if (response.status === 403 || response.status === 404 || response.redirected) { stopped=true; body.disabled=true; status.textContent='Esta conversa não está mais disponível para seu acesso.'; return; }
    if (!response.ok) throw Error();
    var data = await response.json(); var bottom = log.scrollHeight-log.scrollTop-log.clientHeight < 100;
    data.messages.forEach(append); if (bottom) log.scrollTop=log.scrollHeight;
    status.textContent=''; markRead();
   } catch (error) { status.textContent='Conexão interrompida. Tentando novamente...'; }
   finally { busy=false; }
  }
  body.addEventListener('keydown',function (event) { if (event.key==='Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); form.requestSubmit(); } });
  form.addEventListener('submit',async function (event) {
   event.preventDefault(); if (!body.value.trim() || stopped) return;
   var button = form.querySelector('button'); if (button.disabled) return; button.disabled=true; body.readOnly=true; status.textContent='Enviando...';
   try {
    var response = await fetch(form.action,{method:'POST',headers:{'X-Requested-With':'XMLHttpRequest'},body:new FormData(form)});
    if (response.status === 409) { nonce.value=globalThis.crypto && typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,function(c){var r=Math.random()*16|0;return (c==='x'?r:(r&3|8)).toString(16);}); }
    if (!response.ok || response.redirected) throw Error();
    // Poll in sequence instead of appending a later ID and skipping messages sent concurrently.
    body.value=''; nonce.value=globalThis.crypto && typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,function(c){var r=Math.random()*16|0;return (c==='x'?r:(r&3|8)).toString(16);}); status.textContent=''; await poll(); log.scrollTop=log.scrollHeight;
   } catch (error) { status.textContent='Não foi possível enviar. Sua mensagem foi preservada; tente novamente.'; }
   finally { button.disabled=false; body.readOnly=false; }
  });
  var older = windowEl.querySelector('.chat-load-older');
  if (older) older.addEventListener('click',async function () {
   if (!Number.isFinite(first)) return; older.disabled=true;
   try {
    var response = await fetch(windowEl.dataset.chatUpdates+'?before='+first);
    if (!response.ok || response.redirected) throw Error(); var data = await response.json();
    var height = log.scrollHeight; data.messages.slice().reverse().forEach(function (message) {
     if (!log.querySelector('[data-message-id="'+message.id+'"]')) log.prepend(bubble(message)); first=Math.min(first,message.id);
    }); log.scrollTop += log.scrollHeight-height; older.hidden=!data.has_older;
   } catch (error) { status.textContent='Não foi possível carregar mensagens anteriores.'; }
   finally { older.disabled=false; }
  });
  log.scrollTop=log.scrollHeight; markRead(); poll();
  var interval = setInterval(function () { if (!windowEl.isConnected || stopped) clearInterval(interval); else poll(); },3000);
 });
 }
 if (document.readyState === 'complete') init();
 else document.addEventListener('DOMContentLoaded',init,{once:true});
}());
