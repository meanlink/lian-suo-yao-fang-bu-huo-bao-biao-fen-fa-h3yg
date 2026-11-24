import {get, post} from '../api.js';
import {escape, field, form, listen, option, picker, table} from './view.js';

export async function temperaturesPage({root, role, reload, toast}) {
  const {picklists, measurements, low_c, high_c} = await get('/warehouse/temperatures');
  const open = picklists.filter(pick => ['reserved','packed'].includes(pick.status));
  const input = role === 'shift_coordinator' && open.length ? form('录入冷藏交接测温', [
    picker('pick_id','冷藏拣货单', open.map(pick => option(pick.id, `#${pick.id} · ${pick.store_code}`))),
    field('instrument_ref','测温仪或凭证'), field('observed_c','实测温度 °C', {type: 'number', step: 0.01, min: -60, max: 80}),
  ], '登记温度') : '';
  const rows = measurements.map(entry => [`#${entry.picklist_id}`, entry.instrument_ref, `${entry.observed_c} °C`,
    entry.passed ? '合格' : '越界', entry.observer, entry.measured_at].map(escape));
  root.innerHTML = `<p class="wh-policy">本演示仓库冷藏交接规则为 ${escape(low_c)}–${escape(high_c)} °C，末次合格记录在 60 分钟内有效。</p>` + input
    + table(['拣货单','仪器','读数','判定','记录人','时间'], rows, '测温回执');
  listen(root, 'form', ({pick_id, instrument_ref, observed_c}) => post(`/warehouse/temperatures/${pick_id}`, {instrument_ref, observed_c}), reload, toast);
}
