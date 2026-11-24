import {get, post, put} from './api.js';

export const operationTabs = [
  ['expiry', '临期处置', '◷'], ['shortage', '缺货升级', '↑'],
  ['reports', '定时报表', '▤'], ['receipt', '回执对账', '≋'],
];
const escape = value => String(value ?? '—').replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
})[char]);
const header = (title, text) => `<div class="card-head"><div><h2>${title}</h2><p class="muted">${text}</p></div></div>`;
const table = (head, body) => `<div class="table-wrap"><table><thead><tr>${head.map(label => `<th>${label}</th>`).join('')}
  </tr></thead><tbody>${body || `<tr><td colspan="${head.length}">暂无记录</td></tr>`}</tbody></table></div>`;
const field = (label, html) => `<div class="field"><label>${label}${html}</label></div>`;
const note = label => field(label, '<input required minlength="3" maxlength="255" name="note">');
const button = label => `<button class="btn secondary">${label}</button>`;
const form = (endpoint, method, contents) => `<form data-action="${endpoint}" data-method="${method}" class="operations-form">${contents}</form>`;
const cells = values => values.map(value => `<td>${escape(value)}</td>`).join('');
const canInventory = user => ['regional_manager', 'inventory_clerk'].includes(user.role);
const actionLabels = {quarantined: '隔离待退', returned: '退回区域仓'};

async function expiry(root, user) {
  const rows = await get('/expiry-board');
  root.innerHTML = `<div class="card">${header('在库临期批次', '按门店与 SKU 取最新库存。距离到期 30 天以内和已过期在库均纳入。')}
    ${table(['门店 / 商品', '有效期', '当前库存', '替代品', '处置'], rows.map(row => {
      const action = row.action ? `<strong>${actionLabels[row.action]}</strong><br>${escape(row.note)}` : canInventory(user) ?
        form(`/expiry-board/${Number(row.id)}`, 'POST', field('处置动作', '<select name="action"><option value="quarantined">隔离待退</option><option value="returned">退回区域仓</option></select>') + note('处置依据') + button('登记处置')) : '待盘点员处置';
      return `<tr>${cells([`${row.store_code} · ${row.product_name}`, row.expiry_date, row.on_hand, row.substitute_name])}<td>${action}</td></tr>`;
    }).join(''))}</div>`;
}

async function shortage(root, user) {
  const rows = await get('/shortage-board');
  root.innerHTML = `<div class="card">${header('门店缺货升级', '最新库存低于再订货点可登记升级，区域经理记录调货结果。')}
    ${table(['门店 / 商品', '现有库存', '再订货点', '跟进记录', '操作'], rows.map(row => {
      let action = '—';
      if (!row.status && canInventory(user)) action = form(`/shortage-board/${Number(row.id)}`, 'POST', note('升级原因') + button('提交升级'));
      if (row.status === 'open' && user.role === 'regional_manager') action = form(`/shortage-board/${Number(row.id)}`, 'PUT', note('处理结果') + button('关闭升级'));
      const status = row.status === 'resolved' ? `已解决 · ${row.resolution}` : row.status === 'open' ? `跟进中 · ${row.note}` : '待登记';
      return `<tr>${cells([`${row.store_code} · ${row.product_name}`, row.on_hand, row.reorder_point, status])}<td>${action}</td></tr>`;
    }).join(''))}</div>`;
}

async function reports(root, user) {
  const data = await get('/report-subscriptions');
  const manager = user.role === 'regional_manager';
  const options = (rows, val, text) => rows.map(row => `<option value="${escape(row[val])}">${escape(row[text])}</option>`).join('');
  const schedule = manager && data.stores.length && data.recipients.length ? form('/report-subscriptions', 'POST',
    field('门店', `<select name="store_code">${options(data.stores, 'store_code', 'store_name')}</select>`) +
    field('收件人', `<select name="recipient_id" data-number>${options(data.recipients, 'id', 'name')}</select>`) +
    field('每日小时', '<input type="number" name="delivery_hour" min="0" max="23" value="6" data-number required>') + button('保存订阅')) : '';
  const subscriptions = data.subscriptions.map(row => `<tr>${cells([row.store_code, row.recipient, `${String(row.delivery_hour).padStart(2, '0')}:00`, row.enabled ? '发送中' : '已暂停'])}
    <td>${manager ? form(`/report-subscriptions/${Number(row.id)}`, 'PUT', `<input name="enabled" type="hidden" value="${!row.enabled}" data-boolean>${button(row.enabled ? '暂停订阅' : '恢复订阅')}`) : '—'}</td></tr>`).join('');
  const deliveries = data.deliveries.map(row => `<details class="report-delivery"><summary>${escape(row.report_date)} · ${escape(row.store_code)} · ${escape(row.recipient)} · ${row.payload.length} 个 SKU</summary>
    ${table(['SKU', '品名', '盘点日', '库存', '再订货点', '建议补货'], row.payload.map(item => `<tr>${cells([item.sku, item.product_name, item.snapshot_date, item.on_hand, item.reorder_point, item.recommended_qty])}</tr>`).join(''))}</details>`).join('');
  root.innerHTML = `<div class="card">${header('门店报表订阅', '每天按上海时间生成一份库存与补货报表，发到应用内收件箱。')}${schedule}${table(['门店', '收件人', '时间', '状态', '操作'], subscriptions)}</div>
    <div class="card">${header('报表收件箱', '展开报表查看发送时冻结的盘点明细。')}${deliveries || '<p class="muted">暂无已发送报表</p>'}</div>`;
}

async function receipt(root, user) {
  const rows = await get('/receipt-audit');
  root.innerHTML = `<div class="card">${header('分发回执对账', '发送超过 2 小时仍未签收或缺少发送时间的分发进入待核对范围。')}
    ${table(['分发 / 门店', '件数', '收件人', '核对状态', '回执处理'], rows.map(row => {
      let action = '—';
      if (['regional_manager', 'shift_coordinator'].includes(user.role)) {
        if (row.overdue && !row.reason) action = form(`/receipt-audit/${Number(row.id)}`, 'POST', note('异常原因') + button('登记异常'));
        if (row.status === 'received' && row.reason && !row.closed_at) action = form(`/receipt-audit/${Number(row.id)}`, 'PUT', button('结清异常'));
      }
      const status = row.closed_at ? '已对账' : row.reason ? '异常跟进中' : row.overdue ? '待核对' : row.status === 'received' ? '已签收' : '待签收';
      return `<tr>${cells([`#${row.id} · ${row.store_code}`, row.approved_qty, row.recipient_name, status])}<td>${row.reason ? `<p>${escape(row.reason)}</p>` : ''}${action}</td></tr>`;
    }).join(''))}</div>`;
}

const pages = {expiry, shortage, reports, receipt};

export async function renderOperation(page, root, user, toast) {
  await pages[page](root, user);
  root.querySelectorAll('form[data-action]').forEach(widget => {
    widget.onsubmit = async event => {
      event.preventDefault();
      const submit = widget.querySelector('button');
      submit.disabled = true;
      const value = Object.fromEntries(new FormData(widget));
      widget.querySelectorAll('[data-number]').forEach(input => { value[input.name] = Number(input.value); });
      widget.querySelectorAll('[data-boolean]').forEach(input => { value[input.name] = input.value === 'true'; });
      try {
        const save = widget.dataset.method === 'POST' ? post : put;
        await save(widget.dataset.action, value);
        toast('操作已保存');
        await renderOperation(page, root, user, toast);
      } catch (error) {
        toast(error.message);
      } finally {
        submit.disabled = false;
      }
    };
  });
}
