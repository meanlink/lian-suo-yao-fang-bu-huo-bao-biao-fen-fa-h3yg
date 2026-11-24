const htmlEntities = {'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'};
export const escape = value => String(value ?? '').replace(/[&<>"']/g, character => htmlEntities[character]);
export const option = (value, label) => `<option value="${escape(value)}">${escape(label)}</option>`;

export function picker(name, label, choices) {
  return `<label>${label}<select name="${name}" required><option value="">请选择</option>${choices.join('')}</select></label>`;
}

export function field(name, label, {type = 'text', min, max, step, value, placeholder} = {}) {
  const attributes = Object.entries({type, min, max, step, value, placeholder})
    .filter(([, entry]) => entry !== undefined)
    .map(([key, entry]) => `${key}="${escape(entry)}"`).join(' ');
  return `<label>${label}<input name="${name}" ${attributes} required></label>`;
}

export function form(title, fields, submit, extra = '') {
  return `<form class="wh-form" ${extra}><h3>${title}</h3><div class="wh-fields">${fields.join('')}</div><button class="wh-button" type="submit">${submit}</button></form>`;
}

export function table(columns, rows, caption) {
  if (!rows.length) return `<p class="wh-empty">${escape(caption)}暂无记录</p>`;
  const headings = columns.map(column => `<th scope="col">${escape(column)}</th>`).join('');
  const body = rows.map(row => `<tr>${row.map(cell => `<td>${cell}</td>`).join('')}</tr>`).join('');
  return `<div class="wh-table"><table><caption>${escape(caption)}</caption><thead><tr>${headings}</tr></thead><tbody>${body}</tbody></table></div>`;
}

export function listen(root, selector, action, reload, toast) {
  for (const form of root.querySelectorAll(selector)) {
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const submit = form.querySelector('button[type=submit]');
      submit.disabled = true;
      try {
        await action(Object.fromEntries(new FormData(form)), form.dataset);
        await reload();
        toast('已保存仓配记录');
      } catch (error) {
        toast(error.message);
        submit.disabled = false;
      }
    });
  }
}
