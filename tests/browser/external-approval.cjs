// Offline browser check of the real rendered public templates. No real emails or accounts.
// Run with NODE_PATH pointing to Playwright packages.
const assert = require('node:assert/strict');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { chromium } = require('playwright');

(async () => {
    const root = path.resolve(__dirname, '../..');
    const render = spawnSync(path.join(root, '.venv/Scripts/python.exe'), ['-c', `
import django, json
django.setup()
from django.template.loader import render_to_string
from types import SimpleNamespace as Obj
from django.utils import timezone
context = {
    'csrf_token': 'browser-test-token',
    'link': Obj(recipient_name='Cliente', expires_at=timezone.now(), post=Obj(workspace=Obj(name='Workspace teste'))),
    'channels': [{'account': Obj(account_name='Conta teste', get_platform_display='Instagram', is_instagram=True), 'format': 'reel', 'caption': 'Legenda para aprovar', 'media': []}]
}
print(json.dumps({name: render_to_string('approvals/public_' + name + '.html', context) for name in ['review', 'thanks', 'closed']}))
`], { cwd: root, encoding: 'utf8', env: { ...process.env, DJANGO_SETTINGS_MODULE: 'config.settings.development' } });
    assert.equal(render.status, 0, render.stderr);
    const templates = JSON.parse(render.stdout);
    const browser = await chromium.launch({ channel: 'msedge', headless: true });
    try {
        const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
        await page.clock.install();
        const submissions = [];
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.route('**/*', route => {
            const req = route.request();
            const url = new URL(req.url());
            if (url.origin !== 'http://approval.local') return route.abort();
            if (req.method() === 'POST') {
                submissions.push(new URLSearchParams(req.postData()));
                return route.fulfill({ status: 302, headers: { location: '/review/thanks/' }, body: '' });
            }
            const name = url.pathname.endsWith('/thanks/') ? 'thanks' : url.pathname.endsWith('/closed/') ? 'closed' : 'review';
            return route.fulfill({ contentType: 'text/html; charset=utf-8', body: templates[name] });
        });
        await page.goto('http://approval.local/review/test-token/');
        await page.getByRole('button', { name: 'Rejeitar', exact: true }).click();
        assert.equal(submissions.length, 0, 'Reject without comment must not submit');
        await page.locator('#comment').fill('Trocar a capa do vídeo');
        await page.getByRole('button', { name: 'Precisa de ajustes', exact: true }).click();
        await page.waitForURL('**/review/thanks/');
        assert.equal(submissions[0].get('decision'), 'changes_requested');
        assert.equal(submissions[0].get('comment'), 'Trocar a capa do vídeo');
        await page.getByRole('heading', { name: 'Obrigado!' }).waitFor();
        await page.clock.fastForward(10000);
        await page.waitForURL('**/review/closed/');
        await page.getByRole('heading', { name: 'Link encerrado' }).waitFor();
        assert.deepEqual(errors, []);
        console.log('PASS: mobile form, required adjustments, thank-you and 10-second closure.');
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
