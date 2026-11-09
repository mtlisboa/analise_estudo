const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '../..');
const render = spawnSync('python', [path.join(__dirname, 'render_institution_fixtures.py')], {cwd:root,encoding:'utf8'});
assert.equal(render.status,0,render.stderr);
const pages = JSON.parse(render.stdout);
const output = '/tmp/institution-analysis-preview'; fs.mkdirSync(output,{recursive:true});
(async () => {
 const browser = await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE_PATH, args:['--no-sandbox']});
 try {
 const page = await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[]; page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*', route=>{
   const url=new URL(route.request().url());
   if (url.pathname==='/conta/tema/') return route.fulfill({json:{ok:true}});
   if (url.pathname.startsWith('/static/')) return route.fulfill({path:path.join(root,'src',url.pathname)});
   const section=url.searchParams.get('section')||'overview';
   return route.fulfill({body:pages[section]||pages.overview,contentType:'text/html'});
 });
 await page.goto('https://testserver/instituicao/gestor/analise/');
 await page.waitForSelector('[data-analysis-chart="timeline"] svg');
 assert.equal(await page.locator('[data-analysis-chart="timeline"] circle').count(),6);
 await page.screenshot({path:output+'/manager-desktop.png',fullPage:true});
 await page.locator('.analysis-filter-panel summary').click();
 assert.equal(await page.locator('.analysis-filters input[name="start"]').isVisible(),true);
 await page.locator('.analysis-filter-panel summary').click();
 await page.locator('.theme-toggle').click();
 assert.equal(await page.locator('html').getAttribute('data-theme'),'dark');
 assert.equal(await page.locator('h1').evaluate(el=>getComputedStyle(el).color),'rgb(243, 242, 236)');
 await page.screenshot({path:output+'/manager-dark.png',fullPage:true});
 for (const section of ['learning','classes','students','items','attendance','interventions','trajectory','official','record','teacher']) {
   await page.goto('https://testserver/instituicao/gestor/analise/?section='+section);
   assert.equal(await page.locator('.institution-analysis-page').count(),1);
   await page.setViewportSize({width:390,height:844});
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'overflow: '+section);
 }
 await page.goto('https://testserver/instituicao/gestor/analise/');
 await page.waitForSelector('[data-analysis-chart="timeline"] svg');
 await page.screenshot({path:output+'/manager-mobile.png',fullPage:true});
 await page.goto('https://testserver/instituicao/gestor/analise/?section=empty');
 await page.waitForSelector('[data-state="empty"]');
 assert.equal(await page.locator('[data-analysis-chart] svg').count(),0);
 assert.deepEqual(errors,[]);
 console.log('Institutional routes passed: manager/teacher, nine sections, records, charts, dark theme, mobile and empty state. '+output);
 } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exit(1);});
