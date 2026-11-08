/* Received requests use server-scoped counts, filtering and pagination. */
const inboxPanel=$('page-inbox'),inboxCounts=node('div','received-counts'),inboxForm=node('form','received-filters'),inboxQuery=node('input'),inboxStatus=node('select'),inboxSort=node('select'),inboxSummary=node('p','received-summary'),inboxError=node('p','message error'),inboxPages=node('nav','received-pages');
inboxError.hidden=true;inboxError.setAttribute('role','status');inboxSummary.setAttribute('role','status');inboxPages.setAttribute('aria-label','받은 요청 페이지');
inboxQuery.type='search';inboxQuery.maxLength=100;inboxQuery.placeholder='업무명, 문서명, 인계자·인수자 검색';inboxQuery.id='inbox-query';inboxStatus.id='inbox-status';inboxSort.id='inbox-sort';
for(const [value,label] of [['all','모든 상태'],['requested','미확인 · 새 요청'],['reviewing','문서 검토 중'],['needs_info','보완 요청'],['accepted','인수 수락 · 완료 대기'],['completed','인수인계 완료']])inboxStatus.append(new Option(label,value));
for(const [value,label] of [['created','최근 요청순'],['updated','최근 수정순'],['title','문서명순']])inboxSort.append(new Option(label,value));
for(const [label,input] of [['요청 검색',inboxQuery],['진행 상태',inboxStatus],['정렬',inboxSort]]){const field=node('label','field',label);field.append(input);inboxForm.append(field);}
const inboxReset=button('초기화',()=>{inboxQuery.value='';inboxStatus.value='all';inboxSort.value='created';inboxPage=1;void loadReceivedInbox();},'button secondary small');inboxForm.append(button('검색',()=>{inboxPage=1;void loadReceivedInbox();},'button secondary small'),inboxReset);
const inboxNote=node('p','received-count-note','미확인은 열람 확인 기록이 없는 요청이며 문서 확인 시 갱신됩니다. 전체는 완료 건을 포함하며 검색·필터와 관계없이 표시됩니다.');
$('received-requests').before(inboxCounts,inboxNote,inboxForm,inboxSummary,inboxError);$('received-requests').after(inboxPages);inboxPanel.querySelector('h2').textContent='받은 인수인계 요청';
let inboxPage=1,inboxEpoch=0,inboxPending=null,inboxPendingKey='',inboxSearchTimer=null,inboxPoll=null,inboxFailures=0;
function inboxPerson(p){return [p?.department,p?.position,p?.name].filter(Boolean).join(' · ');}
function receivedProgress(r){
 const noQuestionsFinal=!r.question_count&&['accepted','completed'].includes(r.state),states=[true,r.state!=='requested',r.question_count>0||noQuestionsFinal,r.answers_reviewed||noQuestionsFinal,r.state==='completed'];
 const list=node('ol','received-progress');list.setAttribute('aria-label','인수 진행 상태');
 const labels=['요청 수신','문서 검토','추가 질문','답변 확인','인수 완료'];
 let current=r.state==='completed'?4:r.state==='accepted'?4:r.state==='requested'?1:r.unanswered_count?3:r.question_count&&!r.answers_reviewed?3:!r.question_count?2:4;
 labels.forEach((label,i)=>{const step=node('li',states[i]?'done':i===current?'current':'');if(i===current&&!states[i])step.setAttribute('aria-current','step');step.append(node('strong','',label));let text=['수신됨',r.state==='requested'?'열람 전':'열람 확인',r.question_count?r.question_count+'건':noQuestionsFinal?'추가 질문 없음':'필요시 작성',r.question_count?(r.unanswered_count?'답변 대기 '+r.unanswered_count+'건':r.answers_reviewed?'확인 완료':'답변 도착 · 확인 필요'):noQuestionsFinal?'해당 없음':'질문 시 진행',r.state==='completed'?'최종 완료':r.state==='accepted'?'수락됨 · 인계자 완료 대기':'문서·답변 검토 후 수락'][i];step.append(node('small','',text));list.append(step);});return list;
}
function paintReceivedInbox(data){
 inboxCounts.replaceChildren();for(const [label,key] of [['미확인','unread'],['진행 중','active'],['전체','total']]){const item=node('div','received-count');item.append(node('span','',label),node('strong','',String(data[key])));inboxCounts.append(item);}
 const badge=$('nav-inbox-count');badge.textContent=String(data.unread);badge.title='미확인 '+data.unread+'건 · 전체 '+data.total+'건';badge.setAttribute('aria-label','미확인 요청 '+data.unread+'건');const nav=badge.closest('a');if(nav)nav.setAttribute('aria-label','받은 인수인계 · 미확인 '+data.unread+'건 · 전체 '+data.total+'건');
 inboxSummary.textContent='검색 결과 '+data.filtered_total+'건 / 전체 '+data.total+'건 · '+data.page+'페이지';inboxPage=data.page;
 const host=$('received-requests');host.replaceChildren();for(const r of data.items){
  const card=node('article','request-list-row received-card');card.dataset.requestId=String(r.id);const heading=node('div','received-card-heading'),title=button(r.workspace_title||r.title,()=>void openAddressedRequest(r.id),'text-button received-title');title.dataset.requestControl='detail';heading.append(title,node('span','badge '+(r.state==='requested'?'received-unread':r.state==='needs_info'?'amber':'neutral'),r.state==='requested'?'미확인':r.state_label));card.append(heading);
  if(r.workspace_title!==r.title)card.append(node('p','received-document-title',r.title));
  const meta=node('dl','received-meta');for(const [label,value] of [['인계자',inboxPerson(r.sender)],['인수자',inboxPerson(r.recipient)],['요청일',formatRequestTime(r.created)],['전달 자료',r.attachment_count+'개'],['미답변 추가 질문',r.unanswered_count+'건']]){const field=node('div');field.append(node('dt','',label),node('dd','',value));meta.append(field);}card.append(meta,receivedProgress(r));
  const actions=node('div','received-card-actions'),preview=button('인수인계서 확인',()=>void previewReceivedRequest(r.id),'button primary small');preview.dataset.requestControl='detail';actions.append(preview,button('대화하기',()=>void openChat(r.id),'button secondary small'),button('진행·질문 확인',()=>void openAddressedRequest(r.id),'text-button'));card.append(actions);host.append(card);
 }
 if(!data.items.length)host.append(node('p','received-empty',data.total?'검색 조건에 맞는 요청이 없습니다. 검색어나 상태를 바꿔 보세요.':'아직 전달받은 인수인계 요청이 없습니다.'));
 inboxPages.replaceChildren();for(const [label,delta] of [['이전',-1],['다음',1]]){const b=button(label,()=>{inboxPage+=delta;void loadReceivedInbox();},'button secondary small');b.disabled=delta<0?data.page<=1:data.page*data.page_size>=data.filtered_total;inboxPages.append(b);}inboxPages.hidden=data.filtered_total<=data.page_size;inboxError.hidden=true;
}
async function loadReceivedInbox(force=false){
 if(!account.user)return;const uid=account.user.id,params=new URLSearchParams({box:'received',page:inboxPage,page_size:20,q:inboxQuery.value.trim(),status:inboxStatus.value,sort:inboxSort.value}),key=uid+':'+params;
 if(!force&&inboxPending&&inboxPendingKey===key)return inboxPending;inboxPendingKey=key;const epoch=++inboxEpoch;
 const task=(async()=>{try{const data=await api('/api/requests?'+params);if(epoch!==inboxEpoch||uid!==account.user?.id||data.user_id!==uid)return;paintReceivedInbox(data);inboxFailures=0;}catch(e){if(epoch!==inboxEpoch||uid!==account.user?.id)return;inboxFailures++;inboxError.textContent=e.message+' 기존 목록은 유지됩니다. 새로 불러오기를 눌러 주세요.';inboxError.hidden=false;}})().finally(()=>{if(inboxPending===task)inboxPending=null;});inboxPending=task;return task;
}
async function confirmReceiptRead(r){
 if(!r.can_receive||r.state!=='requested')return r;
 try{await post('/api/requests/action',{id:r.id,revision:r.revision,action:'view'});const fresh=await api('/api/requests/'+r.id);void loadReceivedInbox(true);return fresh;}catch(e){message('request-message','문서는 열었지만 열람 확인을 저장하지 못했습니다. '+e.message,'error');return r;}
}
async function previewReceivedRequest(id){const r=await openAddressedRequest(id);if(r?.id===id)await previewHandoverReport('/api/requests/'+id+'/export','hwpx');}
const oldReceivedList=renderRequestList;renderRequestList=function(id,rows){if(id==='received-requests'){void loadReceivedInbox();return;}oldReceivedList(id,rows);};
inboxForm.onsubmit=e=>{e.preventDefault();clearTimeout(inboxSearchTimer);inboxPage=1;void loadReceivedInbox();};inboxQuery.oninput=()=>{clearTimeout(inboxSearchTimer);inboxSearchTimer=setTimeout(()=>{inboxPage=1;void loadReceivedInbox();},300);};for(const field of [inboxStatus,inboxSort])field.onchange=()=>{inboxPage=1;void loadReceivedInbox();};
const oldInboxReload=$('reload-requests').onclick;$('reload-requests').onclick=async()=>{await loadReceivedInbox();await oldInboxReload();};

const receivedDetailOriginal=renderAddressedRequest;renderAddressedRequest=function(){
 receivedDetailOriginal();const r=requestSelection,box=$('request-detail');if(!r)return;
 const overview=node('section','received-overview');overview.append(receivedProgress(r),node('p','received-detail-guide',r.state==='completed'?'최종 인수인계가 완료되었습니다. 전달 문서와 이력을 확인할 수 있습니다.':r.state==='accepted'?'인수 수락이 완료되었습니다. 인계자가 최종 완료하면 확정본이 보관됩니다.':'전달 문서를 확인하고, 필요한 질문의 답변을 검토한 뒤 인수 수락하세요.'));
 const actions=node('div','received-card-actions');actions.append(button('인수인계서 확인',()=>void previewHandoverReport('/api/requests/'+r.id+'/export','hwpx'),'button primary small'),button('대화하기',()=>void openChat(r.id),'button secondary small'));
 overview.append(actions);box.prepend(overview);
 syncReceiptProgress(r);
 const body=node('details','received-document-body');body.append(node('summary','','전달 문서 본문과 자료 '+r.attachment_count+'개 확인'));for(const item of [...box.querySelectorAll(':scope > .recipient-row')])body.append(item);
 const docs=[...box.children].find(el=>el.tagName==='SECTION'&&el!==overview&&!el.classList.contains('journey-request-tools')&&el.querySelector(':scope > h3')?.textContent.includes('연결된 자료'));if(docs)body.append(docs);overview.after(body);
 for(const b of [...box.children])if(b.tagName==='BUTTON'&&b.textContent==='인쇄 미리보기')b.remove();
};
function syncReceiptProgress(r){
 const overview=$('request-detail').querySelector('.received-overview');if(!overview)return;
 overview.querySelector('.received-progress')?.replaceWith(receivedProgress(r));
 let confirm=overview.querySelector('[data-request-control="answers"]');
 if(!r.can_receive||!r.question_count||r.answers_reviewed||r.state==='completed'){confirm?.remove();return;}
 if(!confirm){confirm=button('답변 확인 완료',()=>void requestJob('answers',async()=>{const current=requestSelection;if(!current||current.id!==r.id)return;await post('/api/requests/answers-reviewed',{id:current.id,revision:current.revision,answer_token:receiptDisplayedTokens.get(current.id)?.token});await openAddressedRequest(current.id);await loadReceivedInbox();message('request-message','최신 추가 질문·답변의 확인 상태를 저장했습니다.');}),'button secondary small');confirm.dataset.requestControl='answers';overview.querySelector('.received-card-actions').append(confirm);}
 const displayed=receiptDisplayedTokens.get(r.id);confirm.disabled=!!r.unanswered_count||reqBusy.has('answers')||displayed?.token!==r.answer_token||displayed?.revision!==r.revision;confirm.title=r.unanswered_count?'인계자의 답변이 모두 도착한 뒤 확인할 수 있습니다.':'추가 질문과 답변을 읽고 확인 상태를 저장합니다.';
}
// Update request-scoped progress after question mutations, without replacing inputs.
const receiptDisplayedTokens=new Map();
const receivedQuestionsOriginal=loadJourneyQuestions;loadJourneyQuestions=async function(requestId=null,host='journey-gap-list'){
 const displayed=await receivedQuestionsOriginal(requestId,host);if(!requestId||requestSelection?.id!==requestId||!displayed)return;receiptDisplayedTokens.set(requestId,{token:displayed.answer_token,revision:displayed.request_revision});
 try{const fresh=await api('/api/requests/'+requestId);if(requestSelection?.id!==requestId)return;if(fresh.revision!==requestSelection.revision){syncReceiptProgress(requestSelection);message('request-message','인계자가 새 버전을 전달했습니다. 새로 불러오기를 눌러 최신 문서와 답변을 확인하세요.','warning');return;}requestSelection=fresh;syncReceiptProgress(fresh);void loadReceivedInbox(true);}catch(e){message('request-message','진행 상태를 다시 확인하지 못했습니다. '+e.message,'error');}
};
function pollReceivedInbox(){clearTimeout(inboxPoll);inboxPoll=setTimeout(async()=>{if(!document.hidden)await loadReceivedInbox();pollReceivedInbox();},Math.min(300000,60000*2**Math.min(inboxFailures,3)));}
function inboxRouteHint(){if(state.route==='inbox'&&$('global-message').textContent.startsWith('새 인수인계로 업무를 시작하거나'))$('global-message').hidden=true;}
window.addEventListener('hashchange',()=>{if(state.route==='inbox'){inboxRouteHint();void loadReceivedInbox();}});document.addEventListener('visibilitychange',()=>{if(!document.hidden){void loadReceivedInbox();pollReceivedInbox();}});
const receivedInitializeOriginal=initialize;initialize=async function(){await receivedInitializeOriginal();await loadReceivedInbox();inboxRouteHint();pollReceivedInbox();};
