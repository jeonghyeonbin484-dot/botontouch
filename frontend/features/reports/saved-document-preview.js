/* 저장된 실제 출력 모델의 전체 A4 페이지. 위치 연결은 서버가 만든 식별자만 사용한다. */
let studioPaperDispose=()=>{},studioPaperKey=null,studioPaperEpoch=0,studioPaperController=null,studioPaperFrame=null,studioPaperZoom='fit';
const studioPaperRenderOriginal=studioRender;
studioRender=function(options={}){
 const previous=studioPaperFrame;studioPaperRenderOriginal(options);const host=$('studio-document');
 if(!studioData?.draft){studioPaperKey=null;studioPaperEpoch++;studioPaperController?.abort();studioPaperDispose();studioPaperFrame=null;host.replaceChildren(node('p','muted','AI 제안을 확인하고 문서에 반영하면 전체 A4 문서가 표시됩니다.'));return;}
 const key=JSON.stringify([studioData.session.id,studioData.draft,studioData.questions]);
 if(key===studioPaperKey&&previous){host.replaceChildren(previous);return;}
 void loadStudioPaper(key,studioData.draft.id,studioData.session.workspace_id,!!previous?.classList.contains('studio-paper-expanded'));
};
async function loadStudioPaper(key,draftId,workspaceId,expanded=false){
 studioPaperDispose();studioPaperKey=key;const epoch=++studioPaperEpoch;studioPaperController?.abort();const controller=studioPaperController=new AbortController();
 const sid=studioData.session.id,host=$('studio-document'),viewer=node('div','studio-paper-viewer'),bar=node('div','studio-paper-toolbar'),status=node('p','studio-paper-status','문서 전체 페이지를 준비합니다…');
 const zoom=node('select');zoom.setAttribute('aria-label','문서 확대 비율');for(const [v,t] of [['fit','너비 맞춤'],['0.5','50%'],['0.75','75%'],['1','100%'],['1.25','125%'],['1.5','150%'],['2','200%']])zoom.append(new Option(t,v));zoom.value=studioPaperZoom;
 const frame=node('iframe','studio-paper-frame');frame.title='남양주시 인수인계서 전체 페이지';frame.setAttribute('sandbox','allow-scripts');frame.setAttribute('scrolling','no');
 const scroll=node('div','studio-paper-scroll');scroll.setAttribute('aria-label','A4 전체 문서 세로 스크롤');scroll.append(frame);
 let targets={},disposed=false,oldOverflow=null,pendingHtml=null;
 const labelFull=value=>{full.textContent=value;full.setAttribute('aria-label',value);full.title=value;};
 const fit=()=>{if(disposed||scroll.clientWidth<=0)return;const width=Math.max(260,scroll.clientWidth-2),factor=zoom.value==='fit'?'fit':Number(zoom.value);frame.style.width=Math.max(width,factor==='fit'?width:794*factor+24)+'px';if(pendingHtml!==null){frame.srcdoc=pendingHtml;pendingHtml=null;}frame.contentWindow?.postMessage({type:'baton-paper-zoom',epoch,zoom:factor},'*');};
 const step=direction=>{const values=[.5,.75,1,1.25,1.5,2],current=zoom.value==='fit'?Math.max(.25,(scroll.clientWidth-24)/794):Number(zoom.value);const value=direction>0?values.find(v=>v>current+.01)||2:[...values].reverse().find(v=>v<current-.01)||.5;zoom.value=String(value);studioPaperZoom=zoom.value;fit();};
 const full=button('전체 화면',()=>{if(viewer.classList.contains('studio-paper-expanded')){viewer.classList.remove('studio-paper-expanded');document.body.style.overflow=oldOverflow??'';oldOverflow=null;labelFull('전체 화면');viewer.removeAttribute('role');viewer.removeAttribute('aria-modal');fit();window.dispatchEvent(new Event('studio-paper-fullscreen'));full.focus();return;}oldOverflow=document.body.style.overflow;document.body.style.overflow='hidden';viewer.classList.add('studio-paper-expanded');viewer.setAttribute('role','dialog');viewer.setAttribute('aria-modal','true');viewer.setAttribute('aria-label','인수인계서 전체 화면 및 AI 문장 수정');labelFull('전체 화면 종료');fit();window.dispatchEvent(new Event('studio-paper-fullscreen'));full.focus();},'button secondary small');full.classList.add('studio-paper-fullscreen');full.title='문서를 넓게 보고 문장을 선택해 AI로 수정합니다.';
 const onFullscreen=()=>{labelFull(document.fullscreenElement===viewer?'전체 화면 종료':'전체 화면');fit();};
 const onEscape=e=>{if(!viewer.classList.contains('studio-paper-expanded'))return;if(e.key==='Escape'){e.preventDefault();full.click();}if(e.key==='Tab'){const focusable=[...viewer.querySelectorAll('button:not(:disabled),select:not(:disabled),textarea:not(:disabled),iframe')].filter(el=>el.getClientRects().length);const first=focusable[0],last=focusable.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}}};
 zoom.onchange=()=>{studioPaperZoom=zoom.value;fit();};
 bar.append(button('−',()=>step(-1),'button secondary small'),zoom,button('＋',()=>step(1),'button secondary small'),full);
 viewer.append(bar,status,scroll,node('p','studio-paper-caption','본문의 ○ 문단을 클릭하면 AI에게 수정을 요청할 수 있습니다. 축약된 문단은 연결된 원문 문단을 선택합니다. 한글과 글꼴·페이지 배치는 다를 수 있습니다.'));
 host.replaceChildren(viewer);studioPaperFrame=viewer;viewer.dataset.epoch=String(epoch);viewer.dataset.documentId=String(draftId);
 if(expanded)full.click();
 const onMessage=async event=>{
  if(disposed||event.source!==frame.contentWindow||event.data?.epoch!==epoch)return;
  if(event.data.type==='baton-paper-size'){frame.style.height=Math.max(300,Math.min(200000,Number(event.data.height)||300))+'px';viewer.dataset.ready='true';status.hidden=true;}
  if(event.data.type==='baton-paper-select'){
   const target=targets[event.data.id];if(!target||studioData?.session.id!==sid||studioData?.draft?.id!==draftId)return;
   studioSelectParagraph({...target,session_id:sid,workspace_id:workspaceId});
  }
 };
 const resize=new ResizeObserver(fit);resize.observe(scroll);window.addEventListener('message',onMessage);document.addEventListener('fullscreenchange',onFullscreen);document.addEventListener('keydown',onEscape);
 const timer=setTimeout(()=>controller.abort(),25000);
 studioPaperDispose=()=>{disposed=true;resize.disconnect();window.removeEventListener('message',onMessage);document.removeEventListener('fullscreenchange',onFullscreen);document.removeEventListener('keydown',onEscape);clearTimeout(timer);if(oldOverflow!==null)document.body.style.overflow=oldOverflow;};
 try{
  const result=await api('/api/studio/sessions/'+sid+'/paper',{headers:{'X-Workspace-Id':String(workspaceId)},signal:controller.signal});
  if(disposed||epoch!==studioPaperEpoch)return;targets=result.targets;
  const css='<style>.preview-toolbar{display:none!important}html,body{background:#e8eaed;overflow:hidden}#pages{width:210mm}p[data-edit-id]{cursor:pointer}p[data-edit-id]:hover,p[data-edit-id]:focus,p.paper-selected{outline:2px solid #21806b;outline-offset:3px;background:#e8f6ef}.paper-edit-action{position:absolute;z-index:10;border:0;border-radius:6px;padding:10px 14px;background:#195e50;color:white;font:14px sans-serif;box-shadow:0 2px 8px #0003}</style>';
  const code=`<script>(()=>{document.documentElement.dataset.embedded='true';const epoch=${epoch};let zoom='fit',chosen=null;const action=document.createElement('button');action.textContent='AI 수정 요청';action.className='paper-edit-action';action.hidden=true;document.body.append(action);function fit(){const pages=document.getElementById('pages');if(!pages||document.documentElement.dataset.ready!=='true')return;const factor=zoom==='fit'?Math.min(1,Math.max(.2,(innerWidth-24)/794)):Number(zoom);pages.style.zoom=String(factor);parent.postMessage({type:'baton-paper-size',epoch,height:pages.getBoundingClientRect().height+80},'*');}function select(e){const p=e.target.closest('[data-edit-id]');if(!p)return;document.querySelectorAll('.paper-selected').forEach(x=>x.classList.remove('paper-selected'));p.classList.add('paper-selected');chosen=p.dataset.editId;const box=p.getBoundingClientRect();action.hidden=false;action.style.left=Math.max(8,Math.min(box.left,innerWidth-180))+'px';action.style.top=(box.bottom+scrollY+4)+'px';action.focus({preventScroll:true});}document.addEventListener('click',select);document.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.matches('[data-edit-id]')){e.preventDefault();select(e);}});action.onclick=()=>{parent.postMessage({type:'baton-paper-select',epoch,id:chosen},'*');action.hidden=true;};addEventListener('message',e=>{if(e.source!==parent||e.data?.epoch!==epoch)return;if(e.data.type==='baton-paper-clear'){chosen=null;action.hidden=true;document.querySelectorAll('.paper-selected').forEach(p=>p.classList.remove('paper-selected'));return;}if(e.data.type!=='baton-paper-zoom')return;zoom=e.data.zoom;action.hidden=true;fit();});new MutationObserver(fit).observe(document.documentElement,{attributes:true,attributeFilter:['data-ready']});addEventListener('resize',fit);fit();})();<`+`/script>`;
  pendingHtml=result.html.replace('</style>','</style>'+css).replace('</body>',code+'</body>');frame.onload=fit;fit();
 }catch(error){if(disposed||epoch!==studioPaperEpoch)return;status.textContent='미리보기를 불러오지 못했습니다. 저장된 문서는 유지됩니다.';status.append(button('다시 불러오기',()=>void loadStudioPaper(key,draftId,workspaceId),'button secondary small'));studioPaperKey=null;}
 finally{clearTimeout(timer);}
}
