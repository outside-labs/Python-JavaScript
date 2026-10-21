// Trusted measurement fixtures use the same tagged result shape in both targets.
function typed(value) {
  if (value === null) return {type:'none'};
  if (typeof value === 'boolean') return {type:'bool',value};
  if (typeof value === 'bigint') return {type:'int',value:String(value)};
  if (value?.type === 'str') return {type:'str',codepoints:[...value.codepoints]};
  if (value?.type === 'tuple') return {type:'tuple',items:value.items.map(typed)};
  throw new TypeError('Unadopted measurement result');
}

export async function execute(url, exported = 'main') {
  const before = performance.now();
  const {createModule} = await import(url);
  const imported = performance.now();
  let stdout = '', value = null, app = null, error = null;
  try {
    app = createModule({write:text=>{stdout+=text;}});
    if (exported) value = await app[exported]();
  } catch (caught) {
    const {filename,line,column} = caught.location || {};
    error = {name:caught.name,message:caught.message,location:{filename,line,column}};
  }
  // Retain one module/result for the separate post-GC worker-heap observation.
  globalThis.measurementRetained = {app,value,stdout};
  return {result:{stdout,value:typed(value),error},
    module_import_ms:imported-before,initialize_and_run_ms:performance.now()-imported};
}
