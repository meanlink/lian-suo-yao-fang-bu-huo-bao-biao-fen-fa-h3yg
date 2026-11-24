import {get, post} from '../api.js';
import {escape, field, form, listen, option, picker, table} from './view.js';

export async function lotPage({root, role, reload, toast}) {
  const {lots, warehousing_day} = await get('/warehouse/lots');
  const input = role === 'shift_coordinator' ? form('收货登记', [
    field('sku', 'SKU', {placeholder: 'RX-1001'}), field('lot_code', '批号'), field('supplier_ref', '供货凭证'),
    field('expires_on', '有效期', {type: 'date', min: warehousing_day}),
    picker('temperature_band', '存储类型', [option('ambient','常温'),option('chilled','冷藏')]),
    field('units', '收货件数', {type: 'number', min: 1, max: 1000000, step: 1}),
  ], '登记入库') : '';
  const rows = lots.map(lot => [lot.sku, lot.lot_code, lot.supplier_ref, lot.expires_on,
    lot.temperature_band === 'chilled' ? '冷藏' : '常温', lot.on_hand, lot.reserved,
    lot.state === 'recalled' ? '已召回' : lot.expires_on <= warehousing_day ? '已过期' : lot.free_units].map(escape));
  root.innerHTML = input + table(['SKU', '批号', '供货凭证', '有效期', '存储', '账存', '预留', '可用'], rows, '仓库存量');
  listen(root, 'form', data => post('/warehouse/lots', {...data, units: Number(data.units)}), reload, toast);
}
