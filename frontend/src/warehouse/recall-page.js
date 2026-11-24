import {get, post, put} from '../api.js';
import {escape, field, form, listen, option, picker, table} from './view.js';

function exposureTable(notice, role) {
  const rows = notice.exposures.map(action => {
    const actionable = action.status_at_notice === 'dispatched' || action.pick_status === 'cancelled';
    const actionForm = role === 'shift_coordinator' && !notice.closed_at && !action.handled_at && actionable
      ? form('收回回执', [field('outlet_ref','隔离或撤销凭证'), field('isolated_units','门店隔离件数', {type:'number', min:0, step:1})],
        '确认回执', `data-kind="confirm" data-id="${notice.id}" data-pick="${action.picklist_id}"`) : '—';
    const state = action.handled_at ? `已回执 · ${action.outlet_ref}` : actionable ? '待回执' : '待撤销拣货';
    return [escape(action.store_code), escape(`#${action.picklist_id}`), escape(action.exposed_units), escape(state), actionForm];
  });
  return table(['门店','拣货单','关联件数','状态','处理'], rows, '涉及门店和拣货单');
}

export async function recallsPage({root, role, reload, toast}) {
  const [notices, {lots}] = await Promise.all([get('/warehouse/recalls'), get('/warehouse/lots')]);
  const available = lots.filter(lot => lot.state === 'available');
  const canOpen = role === 'regional_manager' && available.length;
  const input = canOpen ? form('登记召回通知', [
    picker('lot_id','仓库批号', available.map(lot => option(lot.id, `${lot.sku} · ${lot.lot_code}`))),
    field('notice_ref','召回编号'), field('reason','召回原因'),
  ], '锁定批号并追溯', 'data-kind="open"') : '';
  root.innerHTML = input + notices.map(notice => `<article class="wh-notice"><h3>${escape(notice.notice_ref)} · ${escape(notice.lot_code)}</h3>
    <p>${escape(notice.reason)} · 仓内剩余 ${escape(notice.on_hand)} 件 · ${notice.closed_at ? '已结案' : '追溯中'}</p>
    ${exposureTable(notice, role)}${role === 'regional_manager' && !notice.closed_at
      ? form('核对并结案', [], '关闭召回', `data-kind="close" data-id="${notice.id}"`) : ''}</article>`).join('');
  listen(root, 'form', (data, tags) => {
    if (tags.kind === 'open') return post('/warehouse/recalls', {...data, lot_id: Number(data.lot_id)});
    if (tags.kind === 'confirm') return put(`/warehouse/recalls/${tags.id}/actions/${tags.pick}`, {...data, isolated_units: Number(data.isolated_units)});
    return put(`/warehouse/recalls/${tags.id}/close`);
  }, reload, toast);
}
