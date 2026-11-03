// Offline browser regression: real Django templates, Alpine and HTMX. No live services.
const fs = require('node:fs');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const assert = require('node:assert/strict');
const {chromium} = require('playwright');

(async () => {
    const root = path.resolve(__dirname, '../..');
    const fixture = JSON.parse(execFileSync(path.join(root, '.venv/Scripts/python.exe'), [path.join(__dirname, 'notifications_fixture.py')], {cwd: root, encoding: 'utf8'}));
    const browser = await chromium.launch({channel: 'msedge', headless: true});
    try {
        const page = await browser.newPage();
        const errors = [], mutations = [];
        let unread = 1;
        page.on('pageerror', error => errors.push(error.message));
        await page.route('**/*', route => {
            const req = route.request(), url = new URL(req.url());
            if (url.origin !== 'https://notifications.local') return route.abort();
            if (url.pathname.startsWith('/static/')) {
                for (const dir of ['static', 'theme/static']) {
                    const base = path.resolve(root, dir), file = path.resolve(base, url.pathname.slice(8));
                    if (file.startsWith(base + path.sep) && fs.existsSync(file) && fs.statSync(file).isFile()) {
                        return route.fulfill({contentType: file.endsWith('.css') ? 'text/css' : 'application/javascript', body: fs.readFileSync(file)});
                    }
                }
                return route.fulfill({status: 404, body: ''});
            }
            if (url.pathname === '/notifications/unread-count/') return route.fulfill({json: {count: unread}});
            if (req.method() === 'POST') {
                mutations.push(url.pathname);
                assert.equal(req.headers()['x-csrftoken'], 'a'.repeat(64));
                unread = 0;
                return route.fulfill({contentType: 'text/html', body: req.headers()['hx-target'] === 'notification-history-list' ? fixture.read_history : (req.headers()['hx-target'] ? fixture.read_drawer : '{"ok":true}')});
            }
            if (url.pathname === '/details/') return route.fulfill({contentType: 'text/html', body: '<p>Detalhes da publicação</p>'});
            return route.fulfill({contentType: 'text/html', body: fixture.history});
        });
        await page.goto('https://notifications.local/notifications/');
        const badge = page.locator('[x-data="notificationBell()"] .sidebar-badge');
        await badge.waitFor({state: 'visible'});
        assert.equal(await badge.innerText(), '1');
        await page.getByRole('button', {name: 'Mark read', exact: true}).click();
        await page.waitForFunction(() => Alpine.$data(document.querySelector('[x-data="notificationBell()"]')).unreadCount === 0);
        assert.match(await page.locator('#notification-history-list').innerText(), /Falha sintética/);
        assert.equal(await page.getByRole('button', {name: 'Mark read', exact: true}).count(), 0);
        // The drawer has its own Alpine scope in the original design.
        await page.evaluate(drawer => {
            const panel = document.createElement('div');
            panel.id = 'notification-drawer-content';
            panel.setAttribute('x-data', '{}');
            panel.innerHTML = drawer;
            document.body.append(panel);
        }, fixture.drawer);
        await page.locator('#notification-drawer-content a').first().click();
        await page.waitForURL('https://notifications.local/details/');
        assert.equal(mutations.length, 2, 'Each click marks a notification exactly once');
        assert.equal(errors.length, 0, errors.join('\n'));
        process.stdout.write('PASS: live badge, read state/history, CSRF and drawer navigation; no external requests.\n');
    } finally {
        await browser.close();
    }
})().catch(error => {console.error(error); process.exitCode = 1;});
