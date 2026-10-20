// The same emitted artifacts and result encoding run in Node and a browser worker.
function typed(value) {
  if (value === null) return {type: 'none'};
  if (typeof value === 'boolean') return {type: 'bool', value};
  if (typeof value === 'bigint') return {type: 'int', value: value.toString()};
  if (value?.type === 'str' && Array.isArray(value.codepoints))
    return {type: 'str', codepoints: [...value.codepoints]};
  if (value?.type === 'tuple' && Array.isArray(value.items))
    return {type: 'tuple', items: value.items.map(typed)};
  throw new TypeError('Unadopted target result');
}

export async function runCases(cases) {
  const results = [];
  for (const item of cases) {
    const {createModule} = await import(new URL(item.url, import.meta.url));
    let stdout = '', value = null, error = null, stack = '';
    try {
      const app = createModule({write: text => {stdout += text;}});
      if (item.export) value = await app[item.export]();
    } catch (caught) {
      error = {name: caught.name, message: caught.message, location: caught.location};
      stack = String(caught.stack);
    }
    results.push({id: item.id, stdout, value: typed(value), error, stack});
  }
  const order = [];
  const pending = Promise.resolve(1).then(() => {order.push('callback');});
  order.push('sync'); await pending; order.push('await');
  return {cases: results, native: {'array-length': Array.of(1, 2, 3).length,
    'promise-order': order, 'utf16-length': '😀'.length}};
}
