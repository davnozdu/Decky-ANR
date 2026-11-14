// Verify Steam language priority, interpolation and protocol-safe result localization without a browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const catalog = JSON.parse(fs.readFileSync('src/locales/ru.json', 'utf8'));
const source = ts.transpileModule(fs.readFileSync('src/i18n.ts','utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true }
}).outputText;
let subscription;
const moduleState={exports:{}};
const sandbox={module:moduleState,exports:moduleState.exports,require:()=>catalog, setTimeout,clearTimeout,
 navigator:{language:'en-US'},window:{addEventListener(){},removeEventListener(){}},
 SteamClient:{Settings:{GetCurrentLanguage:async()=> 'russian',RegisterForSettingsChanges:fn=>{subscription=fn;return {unregister(){}};}}}};
vm.runInNewContext(source,sandbox);
const i18n=moduleState.exports;
(async()=>{
 const stop=i18n.initializeLanguage(async()=>({language:'english'}));
 await new Promise(setImmediate);
 assert.equal(i18n.getLanguage(),'ru');
 assert.equal(i18n.t('Choose a game'),'Выберите игру');
 assert.equal(i18n.translateMessage('Close the game first.'),'Сначала закройте игру.');
 assert.equal(i18n.translateMessage('FSR 4 DLL refreshed: My Game.'),'Библиотека FSR 4 обновлена: My Game.');
 const raw={status:'success',choice:'quality',path:'/home/Game',log:'Close the game first.',options:[{value:'quality',label:'Quality'}],message:'Close the game first.'};
 const translated=i18n.localizeResult(raw);
 assert.equal(translated.status,'success'); assert.equal(translated.choice,'quality'); assert.equal(translated.path,raw.path); assert.equal(translated.log,raw.log);
 assert.equal(translated.options[0].value,'quality'); assert.equal(translated.options[0].label,'Качество');
 assert.equal(i18n.translateMessage('FSR Lite libraries 2.4.0.4370 imported. Installed in: My Game. For other games, choose FSR 4 Lite in Upscaler.'),
 'Библиотеки FSR Lite 2.4.0.4370 импортированы. Установлено в: My Game. Для остальных игр выберите FSR 4 Lite в настройке «Апскейлер».');
 sandbox.SteamClient.Settings.GetCurrentLanguage=async()=> 'english'; sandbox.navigator.language='ru-RU'; subscription(); await new Promise(setImmediate); assert.equal(i18n.getLanguage(),'en');
 assert.equal(i18n.t('Choose a game'),'Choose a game'); stop();
 sandbox.SteamClient.Settings.GetCurrentLanguage=async()=>{throw Error('old client')};
 const stop2=i18n.initializeLanguage(async()=>({language:'russian'})); await new Promise(setImmediate); assert.equal(i18n.getLanguage(),'ru'); stop2();
 i18n.setLanguage('de-DE'); assert.equal(i18n.getLanguage(),'en');
 for(const [key,value] of Object.entries(catalog)) {
  const indices=s=>[...new Set(s.match(/\{\d+\}/g)||[])].sort();
  assert.deepEqual(indices(key),indices(value),key);
 }
 console.log(`Language checks passed: ${Object.keys(catalog).length} entries; Steam overrides browser locale; safe English fallback; protocol values preserved.`);
})().catch(e=>{console.error(e);process.exitCode=1});
