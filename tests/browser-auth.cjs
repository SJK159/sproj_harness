// Optional Playwright smoke test against the built frontend, with explicit fake
// auth/API responses. No Microsoft credentials or university services are used.
const assert = require('node:assert/strict');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');

(async () => {
  const root = path.resolve(__dirname, '..');
  const server = spawn(process.execPath, [path.join(root, 'frontend/node_modules/vite/bin/vite.js'),
    'preview', '--host', '127.0.0.1', '--port', '4173', '--strictPort'],
    { cwd: path.join(root, 'frontend'), windowsHide: true, stdio: 'ignore' });
  let browser;
  try {
    for (let n = 0; n < 100; n++) {
      try { if ((await fetch('http://127.0.0.1:4173')).ok) break; } catch {}
      if (n === 99) throw new Error('Preview did not start');
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHANNEL ? {channel:process.env.PLAYWRIGHT_CHANNEL} : {}) });
    const page = await browser.newPage();
    let signedIn = false, unauthorized = false;
    const writes = [];
    await page.route('http://localhost:8000/**', async (route) => {
      const request = route.request(), url = new URL(request.url());
      const headers = { 'Access-Control-Allow-Origin':'http://127.0.0.1:4173',
        'Access-Control-Allow-Credentials':'true', 'Access-Control-Allow-Headers':'Content-Type, X-CSRF-Token',
        'Access-Control-Allow-Methods':'GET, POST, OPTIONS' };
      if (request.method() === 'OPTIONS') return route.fulfill({ status:204, headers });
      if (url.pathname === '/auth/status') return route.fulfill({ json:signedIn ?
        {mode:'bff',authenticated:true,actor_id:'S1',role:'Student',csrf_token:'synthetic-csrf'} :
        {mode:'bff',authenticated:false}, headers });
      if (url.pathname === '/auth/logout') {
        writes.push(request.headers()['x-csrf-token']); signedIn = false;
        return route.fulfill({json:{signed_out:true},headers});
      }
      return route.fulfill({status:unauthorized ? 401 : 200, json:unauthorized ? {error:'sign in'} : [], headers});
    });
    await page.goto('http://127.0.0.1:4173');
    await page.getByRole('link',{name:'Sign in with Microsoft'}).waitFor();
    assert.equal(await page.getByText('Demo: switch user').count(),0);
    signedIn = true;
    await page.reload();
    await page.getByText('Signed in as S1 · Student').waitFor();
    assert.equal(await page.getByText('Demo: switch user').count(),0);
    await page.waitForTimeout(400); // Let the existing entrance animation finish for inspection.
    await page.screenshot({path:path.join(root,'data/browser-auth-smoke.png'),fullPage:true});
    await page.getByRole('button',{name:'Sign out',exact:true}).click();
    await page.getByRole('link',{name:'Sign in with Microsoft'}).waitFor();
    assert.deepEqual(writes,['synthetic-csrf']);
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),true);
    signedIn = true; unauthorized = true;
    await page.reload();
    await page.getByRole('link',{name:'Sign in with Microsoft'}).waitFor();
    assert.equal(await page.getByText('Signed in as S1 · Student').count(),0);
    process.stdout.write('Browser auth smoke: sign-in gate, mapped identity, CSRF logout, and 401 reset passed\n');
  } finally {
    if (browser) await browser.close();
    server.kill();
  }
})().catch((error) => { console.error(error.message); process.exitCode = 1; });
