const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { spawnSync } = require('node:child_process');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const root = path.resolve(__dirname, '../..');
const fixtures = spawnSync(process.env.PYTHON || 'python', [path.join(__dirname, 'render_fixtures.py')], { encoding: 'utf8', cwd: root });
assert.equal(fixtures.status, 0, fixtures.stderr);
const html = JSON.parse(fixtures.stdout);
function dom(markup) { return new JSDOM(markup, { url: 'https://testserver/', runScripts: 'outside-only' }); }
function script(window, name) { window.eval(readFileSync(path.join(root, 'src/static/js', name), 'utf8')); }

const assessment = dom(html.assessment);
const w = assessment.window, d = w.document;
w.document.documentElement.dataset.openAssessmentModal = 'true';
script(w, 'assessments.js');
assert.equal(d.querySelector('#assessment-modal').hidden, false, 'invalid edit must remain open');
assert.equal(d.querySelector('#id_subject').value, 'Old failed edit');
d.querySelector('#observation-entry').value = 'Unsaved text from previous modal';
d.querySelector('#new-assessment').click();
assert.equal(d.querySelector('#id_subject').value, '', 'new assessment must clear failed edit defaults');
assert.equal(d.querySelector('#id_topic').value, '');
assert.equal(d.querySelector('#id_technique').value, '');
assert.equal(d.querySelectorAll('[name="assessment_types"]:checked').length, 0);
assert.equal(d.querySelector('#observation-entry').value, '');
assert.equal(d.querySelectorAll('#assessment-form .errorlist').length, 0);
assert.ok(d.querySelector('#assessment-form').action.endsWith('/avaliacoes/nova/'));

const dangerous = '" onmouseover="window.injected=true" <img src=x onerror=alert(1)>';
d.querySelector('#observation-entry').value = dangerous;
d.querySelector('#add-observation').click();
assert.equal(d.querySelector('#observation-list img'), null);
assert.equal(d.querySelector('#observation-list button').getAttribute('onmouseover'), null);
assert.equal(d.querySelector('#observation-list button').getAttribute('aria-label'), 'Remover ' + dangerous);
d.querySelector('#observation-entry').value = 'Pending observation';
d.querySelector('#assessment-form').dispatchEvent(new w.Event('submit', { cancelable: true }));
assert.equal(d.querySelector('#id_observations').value, dangerous + '\nPending observation', 'save must include pending observation');
assert.equal(d.querySelector('.assessment-search').getAttribute('action'), '/avaliacoes/');
d.querySelector('[data-remove-observation]').click();
assert.equal(d.querySelector('#id_observations').value, 'Pending observation');
assessment.window.close();

const chat = dom(html.chat);
const cw = chat.window, cd = cw.document;
const sockets = [];
class FakeSocket extends cw.EventTarget {
    static OPEN = 1;
    constructor() { super(); this.readyState = 1; this.sent = []; sockets.push(this); }
    send(message) { this.sent.push(JSON.parse(message)); }
    receive(payload) { this.dispatchEvent(new cw.MessageEvent('message', { data: JSON.stringify(payload) })); }
}
cw.WebSocket = FakeSocket;
script(cw, 'chat_bot.js');
const socket = sockets[0];
socket.receive({ type: 'chat.ready' });
const input = cd.querySelector('[data-chat-input]');
input.value = 'Old question';
cd.querySelector('[data-chat-form]').dispatchEvent(new cw.Event('submit', { cancelable: true }));
const oldId = socket.sent[0].conversation_id;
cd.querySelector('[data-chat-clear]').click();
input.value = 'New question';
cd.querySelector('[data-chat-form]').dispatchEvent(new cw.Event('submit', { cancelable: true }));
assert.equal(socket.sent.length, 2, 'clearing chat must release waiting state');
const newId = socket.sent[1].conversation_id;
assert.notEqual(oldId, newId);
socket.receive({ type: 'chat.response', conversation_id: oldId, message: 'STALE ANSWER' });
assert.equal(cd.querySelector('[data-chat-messages]').textContent.includes('STALE ANSWER'), false);
assert.equal(cd.querySelector('[data-chat-thinking]').hidden, false, 'stale response must not finish new request');
socket.receive({ type: 'chat.response', conversation_id: newId, message: 'CURRENT ANSWER' });
assert.ok(cd.querySelector('[data-chat-messages]').textContent.includes('CURRENT ANSWER'));
assert.equal(cd.querySelector('[data-chat-thinking]').hidden, true);
chat.window.close();
console.log('Frontend regressions passed: modal reset, observations, safe DOM, search route, stale chat responses.');

const analytics = dom(html.analytics);
const aw = analytics.window, ad = aw.document;
// Exercise the CDN failure branch without spending ten seconds on timer retries.
aw.setTimeout = callback => { callback(); return 1; };
script(aw, 'analytics_dashboard.js');
ad.dispatchEvent(new aw.Event('DOMContentLoaded'));
const filters = ad.querySelector('.analytics-filters');
assert.ok(filters.elements.teacher.value);
assert.ok(filters.elements.student.value);
filters.elements.teacher.dispatchEvent(new aw.Event('change', { bubbles: true }));
assert.equal(filters.elements.classroom.value, '');
assert.equal(filters.elements.student.value, '');
filters.elements.organization.dispatchEvent(new aw.Event('change', { bubbles: true }));
assert.equal(filters.elements.teacher.value, '');
assert.ok(ad.querySelector('#timeline-chart').textContent.includes('Não foi possível carregar'));
assert.ok(ad.querySelector('.analytics-table').textContent.includes('teacher-fixture'));
analytics.window.close();
console.log('Analytics frontend regressions passed: manager controls, dependent filters and chart failure fallback.');
