/* Readable document views. Raw source locations and stored references are never rewritten. */
function readableText(target,text){
 let list=null;
 for(const line of String(text||'').split(/\n+/)){
  const value=line.trim();if(!value)continue;
  if(/^[○●•▪\-]\s*/.test(value)){if(!list){list=node('ul');target.append(list);}list.append(node('li','',value.replace(/^[○●•▪\-]\s*/,'')));continue;}
  list=null;const heading=value.length<65&&/^(?:[1-9]\d*[.)]\s|[가-힣][.)]\s|제\s*\d+\s*[장절])/.test(value);
  target.append(node(heading?'h3':'p','',value));
 }
}
function sourceDocument(doc,highlight){
 const article=node('article','source-document');article.setAttribute('aria-label','연속된 원문 본문');let sheet=null,table=null,columns=[];
 for(const [index,source] of doc.sources.entries()){
  const match=String(source.location).match(/^(.*?) · (\d+)행$/);let block;
  if(fileType(doc.name)==='xlsx'&&match){
   if(sheet!==match[1]){sheet=match[1];columns=[...new Set(doc.sources.filter(s=>String(s.location).match(/^(.*?) · (\d+)행$/)?.[1]===sheet).flatMap(s=>[...s.text.matchAll(/(?:^| \| )([A-Z]+):/g)].map(m=>m[1])))];columns.sort((a,b)=>a.length-b.length||a.localeCompare(b));article.append(node('h3','sheet-title',sheet));table=node('table','source-table');article.append(table);}
   const pairs=[];for(const part of source.text.split(' | ')){const cell=part.match(/^([A-Z]+):\s*([\s\S]*)$/);if(cell)pairs.push([cell[1],cell[2]]);else if(pairs.length)pairs[pairs.length-1][1]+=' | '+part;}
   for(const [column] of pairs)if(!columns.includes(column))columns.push(column);
   block=node('tr','source-block');const cells=new Map(pairs);for(const column of columns){const value=cells.get(column)||'';const td=node('td','',value);td.dataset.column=column;block.append(td);}table.append(block);
  }else{sheet=null;block=node('div','source-block');readableText(block,source.text);article.append(block);}
  block.dataset.location=source.location;block.dataset.sourceIndex=String(index);block.tabIndex=-1;
  const position=node('small','source-position',source.location);if(block.tagName==='TR'){const td=node('td','source-row-position');td.append(position);block.append(td);}else block.prepend(position);
  if(source.location===highlight){block.classList.add('source-highlight');block.setAttribute('aria-current','true');}
 }
 return article;
}
function sourcePositionToggle(article){const control=button('근거 위치 표시',()=>{const show=article.classList.toggle('show-source-positions');control.textContent=show?'근거 위치 숨기기':'근거 위치 표시';control.setAttribute('aria-pressed',String(show));},'button secondary small');control.setAttribute('aria-pressed','false');return control;}
const sourceDialog=node('dialog','source-document-dialog');sourceDialog.id='source-document-dialog';const sourceDialogHead=node('div','source-dialog-header');const sourceDialogTitle=node('h2');const sourceDialogClose=button('원문 창 닫기',()=>sourceDialog.close(),'button secondary small');sourceDialogHead.append(sourceDialogTitle,sourceDialogClose);const sourceDialogInfo=node('p','muted'),sourceDialogBody=node('div','source-dialog-body');sourceDialog.append(sourceDialogHead,sourceDialogInfo,sourceDialogBody);document.body.append(sourceDialog);
function storedSourceDocument(ref){
 const request=typeof requestSelection!=='undefined'?requestSelection:null;
 const original=request?.documents?.find(doc=>doc.id===ref.document_id&&doc.revision===ref.revision);
 if(original){const sources=typeof original.sources==='string'?JSON.parse(original.sources):original.sources;if(sources.some(s=>s.location===ref.location&&s.text===ref.text))return {...original,sources,note:'요청 당시 보존된 원문'};}
 const refs=Object.entries(state.draft?.references||{}).filter(([key,r])=>r.document_id===ref.document_id&&r.revision===ref.revision).sort((a,b)=>Number(a[0].match(/-S(\d+)$/)?.[1]||0)-Number(b[0].match(/-S(\d+)$/)?.[1]||0)).map(([key,r])=>({location:r.location,text:r.text}));
 if(refs.some(s=>s.location===ref.location&&s.text===ref.text))return {name:ref.name,sources:refs,note:'초안 작성 당시 보존된 원문'};
 return null;
}
async function viewSourceReference(ref){
 sourceDialogTitle.textContent=ref.name;sourceDialogInfo.textContent='원문을 불러옵니다.';sourceDialogBody.replaceChildren();sourceDialog.showModal();
 try{
  let doc=storedSourceDocument(ref);
  if(!doc&&ref.document_id){const fetched=await api('/api/documents/'+ref.document_id);if(fetched.revision===ref.revision&&fetched.sources.some(s=>s.location===ref.location&&s.text===ref.text))doc={...fetched,note:'등록된 원문'};}
  if(!doc)doc={name:ref.name,sources:[{location:ref.location,text:ref.text}],note:'보존된 근거 발췌만 표시합니다. 전체 원문 또는 동일 버전을 확인할 수 없습니다.'};
  sourceDialogInfo.textContent=doc.note+' · 선택 근거: '+ref.location;
  const article=sourceDocument(doc,ref.location);sourceDialogBody.append(sourcePositionToggle(article),article);requestAnimationFrame(()=>{const active=article.querySelector('.source-highlight');active?.scrollIntoView({block:'center'});active?.focus({preventScroll:true});});
 }catch(error){sourceDialogInfo.textContent=error.message+' 작성 내용은 유지됩니다.';}
}
citation=function(ref){if(!ref)return node('p','message warning','출처 없음 · 전임자 확인 필요');const details=node('details','citation');details.append(node('summary','','출처 보기 · '+ref.name),node('p','source-exact-location',ref.location),node('p','source-excerpt',ref.text),button('원문에서 보기',()=>void viewSourceReference(ref),'button secondary small'));return details;};
function itemSourceView(refs){const details=node('details','citation item-sources');details.append(node('summary','','출처 보기 · '+new Set(refs.map(r=>r.name)).size+'개 자료'));for(const name of new Set(refs.map(r=>r.name))){const group=node('section','source-file-group');group.append(node('h4','',name));for(const ref of refs.filter(r=>r.name===name)){const row=node('div','source-evidence');row.append(node('p','source-exact-location',ref.location),node('p','source-excerpt',ref.text),button('원문에서 보기',()=>void viewSourceReference(ref),'button secondary small'));group.append(row);}details.append(group);}return details;}
openDocument=async function(id){const token=++state.readerToken;state.selectedDoc=id;renderFiles();loading($('reader-content'),'원문을 불러옵니다');try{const doc=await api('/api/documents/'+id);if(token!==state.readerToken)return;$('reader-title').textContent=doc.name;$('reader-meta').textContent='추출 본문 · '+fileType(doc.name).toUpperCase()+' · 원본의 일부 서식은 생략될 수 있습니다.';const article=sourceDocument(doc);$('reader-content').replaceChildren(sourcePositionToggle(article),article);}catch(error){if(token===state.readerToken)empty($('reader-content'),'원문을 열지 못했습니다',error.message,'info');}};
function resizeDocumentInputs(){for(const field of $('draft-items').querySelectorAll('textarea')){if(!field.offsetParent)continue;field.style.height='auto';field.style.height=Math.max(field.scrollHeight,68)+'px';}}
const readableEditor=renderEditor;renderEditor=function(){readableEditor();$('draft-items').classList.add('readable-handover');requestAnimationFrame(resizeDocumentInputs);};$('draft-items').addEventListener('input',resizeDocumentInputs);window.addEventListener('resize',resizeDocumentInputs);

const readableObserver=new ResizeObserver(()=>requestAnimationFrame(resizeDocumentInputs));readableObserver.observe($('draft-items'));
