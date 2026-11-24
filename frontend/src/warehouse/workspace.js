import {lotPage} from './lot-page.js';
import {pickPage} from './pick-page.js';
import {temperaturesPage} from './temperature-page.js';
import {recallsPage} from './recall-page.js';
import {countPage} from './count-page.js';

const pages = {
  'warehouse-lots': ['入库批号', lotPage],
  'warehouse-picks': ['仓库拣配', pickPage],
  'warehouse-temperature': ['冷藏交接', temperaturesPage],
  'warehouse-recalls': ['批号召回', recallsPage],
  'warehouse-counts': ['盘差复核', countPage],
};

export const isWarehouse = path => Object.hasOwn(pages, path);

export async function renderWarehouse(path, root, user, toast) {
  root.innerHTML = `<section class="warehouse"><div class="wh-nav" aria-label="仓配功能">${Object.entries(pages)
    .map(([key, [name]]) => `<a href="#/${key}" ${key === path ? 'aria-current="page"' : ''}>${name}</a>`).join('')}</div>
    <div class="wh-content"></div></section>`;
  const context = {root: root.querySelector('.wh-content'), role: user.role, toast};
  const page = pages[path][1];
  context.reload = () => page(context);
  await context.reload();
}
