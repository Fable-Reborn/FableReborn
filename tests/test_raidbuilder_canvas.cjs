/* Browser contract test. NODE_PATH must expose playwright; arguments: editor HTML, output directory. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');

(async () => {
  const [fixture, output] = process.argv.slice(2);
  assert(fixture && output, 'Pass an exported editor HTML and output directory.');
  const browser = await chromium.launch({ channel: process.env.RAID_TEST_BROWSER || 'msedge', headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(pathToFileURL(fixture).href);
    assert.equal(await page.locator('.node').count(), 4);
    await page.getByRole('button', { name: 'Validate', exact: true }).click();
    assert.match(await page.locator('#report-title').innerText(), /passed/);
    await page.getByRole('button', { name: 'Close', exact: true }).click();

    // Drag an existing encounter, then connect a port using actual pointer events.
    const guardian = page.locator('[data-node="guardian"]');
    const head = await guardian.locator('.head').boundingBox();
    await page.mouse.move(head.x + 80, head.y + 35);
    await page.mouse.down();
    await page.mouse.move(head.x + 110, head.y + 245, { steps: 12 });
    await page.mouse.up();
    assert.equal(await guardian.evaluate(node => node.style.top), '260px');
    const port = await page.locator('[data-node="arrival"] .port').boundingBox();
    const target = await guardian.boundingBox();
    await page.mouse.move(port.x + port.width - 7, port.y + port.height / 2);
    await page.mouse.down();
    await page.mouse.move(target.x + 30, target.y + 30, { steps: 10 });
    await page.mouse.up();
    assert.match(await page.locator('[data-node="arrival"] .port').innerText(), /Gate Guardian/);

    // Add a team and a role, then edit more than one field without losing an open card.
    await page.getByRole('button', { name: 'Teams', exact: true }).click();
    await page.getByRole('button', { name: '+ Team', exact: true }).click();
    await page.locator('#inspector summary').last().click();
    await page.getByLabel('Team name', { exact: true }).last().fill('Wardens');
    await page.getByLabel('Team name', { exact: true }).last().press('Tab');
    await page.getByRole('button', { name: 'Roles', exact: true }).click();
    await page.getByRole('button', { name: '+ Role', exact: true }).click();
    await page.locator('#inspector summary').last().click();
    await page.getByLabel('Role name', { exact: true }).last().fill('Warden');
    await page.getByLabel('Role name', { exact: true }).last().press('Tab');
    await page.getByLabel('Team', { exact: true }).last().selectOption({ label: 'Wardens' });
    await page.getByLabel('Role health (0 = raid default)', { exact: true }).last().fill('200');
    await page.getByLabel('Role health (0 = raid default)', { exact: true }).last().press('Tab');

    // Author a status and add a second enemy while preserving the original boss.
    await page.getByRole('button', { name: 'Statuses', exact: true }).click();
    await page.getByRole('button', { name: '+ Status', exact: true }).click();
    await page.locator('#inspector summary').last().click();
    await page.getByLabel('Status name', { exact: true }).fill('Moonfire');
    await page.getByLabel('Status name', { exact: true }).press('Tab');
    await guardian.locator('.head').click();
    await page.getByRole('button', { name: '+ Enemy', exact: true }).click();
    await page.getByRole('button', { name: '+ Rule', exact: true }).click();
    await page.locator('#inspector summary').last().click();
    await page.getByRole('button', { name: 'Build AND / OR group', exact: true }).click();
    const conditionModes = page.locator('.condition > select');
    await conditionModes.first().selectOption('any');
    // Nested group on the second branch.
    await page.locator('.condition > select').nth(2).selectOption('all');
    await page.getByLabel('Effect', { exact: true }).selectOption('apply_status');
    await page.getByLabel('Target', { exact: true }).selectOption('enemies');
    await page.getByLabel('Stacks', { exact: true }).fill('1');
    await page.getByLabel('Stacks', { exact: true }).press('Tab');
    await page.getByLabel('Status', { exact: true }).selectOption({ label: 'Moonfire' });

    await page.getByRole('button', { name: 'Validate', exact: true }).click();
    assert.match(await page.locator('#report-title').innerText(), /passed/);
    await page.getByRole('button', { name: 'Close', exact: true }).click();
    const downloading = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Download Save File', exact: true }).click();
    const download = await downloading;
    const packagePath = path.join(output, 'raid-canvas-browser-save.json');
    await download.saveAs(packagePath);
    const saved = JSON.parse(fs.readFileSync(packagePath, 'utf8'));
    const spec = saved.definition.config.encounter;
    assert.equal(spec.roles.length, 2);
    assert.equal(spec.roles[1].hp, 200);
    assert.equal(spec.statuses[0].label, 'Moonfire');
    assert.equal(spec.nodes[1].enemies.length, 2);
    assert.equal(spec.nodes[1].rules[0].condition.any[1].all.length, 2);
    assert.equal(spec.layout.guardian.y, 260);

    // Reload resumes the browser draft, and another downloaded copy can be opened.
    await page.reload();
    await page.getByRole('button', { name: 'Roles', exact: true }).click();
    assert.equal(await page.locator('#inspector summary').count(), 2);
    await page.locator('#file-input').setInputFiles(packagePath);
    assert.equal(await page.locator('#report[open]').count(), 0);
    await page.screenshot({ path: path.join(output, 'raid-canvas-desktop.png') });

    // Basic narrow-screen usability: inspector and save controls remain accessible.
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.locator('body').evaluate(el => el.scrollWidth <= window.innerWidth), true);
    await page.getByRole('button', { name: 'Raid', exact: true }).click();
    await page.getByLabel('Raid name', { exact: true }).fill('Mobile raid');
    await page.getByLabel('Raid name', { exact: true }).press('Tab');
    assert.equal(await page.locator('#raid-name').innerText(), 'Mobile raid');
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ result: 'passed', checks: 'dragging, connections, roles, teams, statuses, enemies, nested AND/OR, download, reopen, mobile', packagePath }));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
