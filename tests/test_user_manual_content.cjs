const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const source=fs.readFileSync(path.join(root,'web/features/help/user-manual.js'),'utf8');
const context=vm.createContext({routes:{}});
vm.runInContext(source.slice(0,source.indexOf('const manualPage=')),context);
const data=vm.runInContext('({manualChapters,manualFaq,routes})',context);
const forbidden=/(?:\/(?:login|dashboard|handover|api)\b|https?:\/\/|\b(?:API|DB|SSO|HTTP|HTML|CSS|JSON|OCR|Vercel|Supabase|Neon|SQLite|PostgreSQL|SAEOLL_ID|USER_ID)\b|서버|컴포넌트|변수명|개발환경|개발 환경|내부 시스템 구조)/i;
test('전체 장과 질문에 개발자 설명이 없다',()=>{
 assert.equal(data.manualChapters.length,14);assert.equal(data.manualFaq.length,19);
 for(const c of data.manualChapters){for(const text of [c.title,...c.steps,c.tip||''])assert.equal(forbidden.test(text),false,text);}
 for(const pair of data.manualFaq)for(const text of pair)assert.equal(forbidden.test(text),false,text);
 for(const text of data.routes.guide)assert.equal(forbidden.test(text),false,text);
});
test('모든 안내 이미지가 존재하고 최신 안내 이미지를 가리킨다',()=>{
 for(const c of data.manualChapters){if(!c.image)continue;assert.match(c.image,/-20261109$/);assert.ok(fs.existsSync(path.join(root,'public/media/manual',c.image+'.png')),c.image);}
});
test('후임자 확정과 문서 반영을 실제 버튼명으로 안내한다',()=>{
 const text=JSON.stringify(data.manualChapters);for(const label of ['후임자 확정','직원 조회','문서에 반영','자료함에서 선택','AI 예상 질문 만들기'])assert.ok(text.includes(label),label);
});
test('목차 검색 인쇄 이미지 확대 기능이 유지된다',()=>{
 for(const id of ['manual-search','manual-toc','manual-print','manual-prev','manual-next','manualImageDialog.showModal()'])assert.ok(source.includes(id),id);
});
