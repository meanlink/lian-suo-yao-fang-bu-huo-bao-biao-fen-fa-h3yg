import {get, post, put} from '../api.js';
import {escape, field, form, listen, option, picker, table} from './view.js';

const stateLabel = {pending: '等候复核', posted:'已过账', rejected:'退回重盘'};

export async function countPage({root, role, reload, toast}) {
  const [counts, {lots}] = await Promise.all([get('/warehouse/counts'), get('/warehouse/lots')]);
  const available = lots.filter(lot => lot.state === 'available');
  const input = role === 'inventory_clerk' && available.length ? form('申报仓库盘差', [
    picker('lot_id','仓库批号', available.map(lot => option(lot.id, `${lot.lot_code} · 账存 ${lot.on_hand}`))),
    field('count_ref','盘点凭证'), field('counted_units','实盘件数', {type:'number', min:0, max:1000000, step:1}), field('reason','差额原因'),
  ], '提交盘差', 'data-kind="submit"') : '';
  const rows = counts.map(count => [count.count_ref, count.lot_code, count.system_units, count.counted_units,
    count.delta > 0 ? `+${count.delta}` : count.delta, stateLabel[count.state]].map(escape).concat(
    role === 'regional_manager' && count.state === 'pending'
      ? form('盘差复核', [picker('decision','决定',[option('posted','批准过账'),option('rejected','退回重盘')]), field('note','复核意见')],
        '提交复核', `data-kind="review" data-id="${count.id}"`) : escape(count.reviewer_note || '—')));
  root.innerHTML = input + table(['凭证','批号','账存','实盘','差额','状态','复核'], rows, '仓库盘差台账');
  listen(root, 'form', (data, tags) => tags.kind === 'submit'
    ? post('/warehouse/counts', {...data, lot_id: Number(data.lot_id), counted_units: Number(data.counted_units)})
    : put(`/warehouse/counts/${tags.id}`, data), reload, toast);
}
