// Browser checks for real Django templates and real Plotly, using disposable fixtures.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { spawnSync } = require('node:child_process');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '../..');
const result = spawnSync(process.env.PYTHON || 'python', [path.join(__dirname, 'render_fixtures.py')], {cwd: root, encoding: 'utf8'});
assert.equal(result.status, 0, result.stderr);
const fixtures = JSON.parse(result.stdout);
const output = process.env.SCREENSHOT_DIR || path.join(os.tmpdir(), 'lumini-analytics-visual');
fs.mkdirSync(output, {recursive: true});
(async () => {
    const browser = await chromium.launch({headless: true, executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || undefined,
        args: ['--no-sandbox', '--disable-dev-shm-usage', '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']});
    const page = await browser.newPage({viewport: {width: 1440, height: 1100}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/conta/tema/') return route.fulfill({json: {ok: true}});
        if (url.host === 'cdn.plot.ly') return route.fulfill({path: require.resolve('plotly.js-dist-min'), contentType: 'application/javascript'});
        if (url.pathname.startsWith('/static/')) {
            const file = path.join(root, 'src', url.pathname);
            return route.fulfill({path: file, contentType: file.endsWith('.css') ? 'text/css' : 'application/javascript'});
        }
        return route.fulfill({body: url.pathname === '/empty/' ? fixtures.analytics : fixtures.analytics_overview, contentType: 'text/html'});
    });
    await page.goto('https://testserver/');
    await page.waitForFunction(() => document.querySelector('#timeline-chart').data?.length === 1);
    await page.waitForFunction(() => document.querySelector('#classroom-scatter-chart').data?.length > 0);
    await page.selectOption('#classroom-scope-select', {index: 1});
    await page.locator('#clear-analysis-selection').click();
    await page.screenshot({path: path.join(output, 'desktop-light.png'), fullPage: true});
    assert.equal(await page.locator('#teachers').count(), 1);
    assert.equal(await page.locator('#students').count(), 1);
    assert.equal(await page.locator('.analytics-explore').getAttribute('open'), null);
    await page.selectOption('#timeline-mode', 'dimensions');
    await page.waitForFunction(() => document.querySelector('#timeline-chart').data?.length === 4);
    assert.deepEqual(await page.evaluate(() => document.querySelector('#timeline-chart').data.map(trace => trace.name)), ['Foco', 'Organização', 'Compreensão', 'Motivação']);
    const light = await page.evaluate(() => document.querySelector('#timeline-chart').layout.font.color);
    await page.locator('.theme-toggle').click();
    await page.waitForFunction(color => document.querySelector('#timeline-chart').layout.font.color !== color, light);
    await page.screenshot({path: path.join(output, 'desktop-dark.png'), fullPage: true});
    await page.locator('.analytics-explore summary').click();
    await page.waitForFunction(() => document.querySelector('#scatter-3d-chart').data?.[0]?.type === 'scatter3d');
    await page.locator('.analytics-explore').screenshot({path: path.join(output, '3d-dark.png')});
    await page.locator('.analytics-explore summary').click();
    await page.locator('.theme-toggle').click();
    for (const width of [390, 768]) {
        await page.setViewportSize({width, height: 844});
        await page.waitForTimeout(350);
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'page must not overflow horizontally at ' + width);
        await page.screenshot({path: path.join(output, 'responsive-' + width + '.png'), fullPage: true});
    }
    await page.goto('https://testserver/empty/');
    await page.waitForSelector('#timeline-chart[data-state="empty"]');
    await page.screenshot({path: path.join(output, 'empty-mobile.png'), fullPage: true});
    assert.deepEqual(errors, []);
    console.log('Browser checks passed: light/dark, dimensions, 3D, 390/768/1440px, empty state. Screenshots: ' + output);
    await browser.close();
})().catch(error => {console.error(error); process.exit(1);});
