/* Sender cards share the recipient design; progress comes only from stored facts. */
function sentReviewLabel(r){return r.recipient_account_pending?'수신 계정 연결 대기':({requested:'열람 확인 전',reviewing:'열람 확인 · 검토 중',needs_info:'보완 요청',accepted:'인수 수락',completed:'최종 인수 완료'})[r.state];}
function sentNextAction(r){
 if(r.state==='completed')return '최종 인수인계가 완료되었습니다. 전달 문서와 처리 이력을 확인하세요.';
 if(r.recipient_account_pending)return '요청이 저장되었습니다. 인수자의 계정이 연결되면 받은 요청함에 표시됩니다.';
 if(r.state==='needs_info')return '보완 요청: '+(r.reason||'진행 상황에서 요청 내용을 확인하세요.');
 if(r.unanswered_count)return '미답변 추가 질문 '+r.unanswered_count+'건 · 진행 상황에서 답변을 작성하세요.';
 if(r.state==='accepted')return '인수자가 수락했습니다. 진행 상황에서 최종 완료·확정본 저장을 처리하세요.';
 if(r.question_count&&!r.answers_reviewed)return '답변을 전달했습니다. 인수자의 답변 확인을 기다리고 있습니다.';
 return r.state==='requested'?'인수자의 문서 열람 확인을 기다리고 있습니다.':'인수자가 문서를 검토 중입니다. 추가 질문과 처리 상태를 확인하세요.';
}
function sentRequestProgress(r){
 const final=r.state==='completed',accepted=['accepted','completed'].includes(r.state);
 const steps=[
  ['요청 전달',!r.recipient_account_pending,r.recipient_account_pending?'계정 연결 대기':'전달됨'],
  ['인수자 검토',accepted,sentReviewLabel(r)],
  ['질문·답변',!!r.question_count&&!r.unanswered_count&&r.answers_reviewed,r.question_count?(r.unanswered_count?'질문 '+r.question_count+'건 · 미답변 '+r.unanswered_count+'건':r.answers_reviewed?'질문 '+r.question_count+'건 · 답변 확인됨':'답변 전달 · 인수자 확인 대기'):r.state==='needs_info'?'보완 요청 있음':'추가 질문 없음'],
  ['최종 인수 완료',final,final?'최종 완료':r.state==='accepted'?'수락됨 · 최종 완료 대기':'인수 수락 전']
 ];
 const current=final?-1:r.recipient_account_pending?0:r.state==='requested'?1:r.state==='needs_info'||r.unanswered_count||r.question_count&&!r.answers_reviewed?2:accepted?3:1;
 const list=node('ol','received-progress sent-progress');list.setAttribute('aria-label','보낸 요청 진행 상태');list.dataset.requestState=r.state;
 steps.forEach(([label,done,text],i)=>{const item=node('li',done?'done':i===current?'current':i===2&&!r.question_count&&r.state!=='needs_info'?'optional':'');if(i===current&&!done)item.setAttribute('aria-current','step');item.append(node('strong','',label),node('small','',text));list.append(item);});return list;
}

const sentPanel=$('page-sent'),sentForm=node('form','received-filters sent-filters'),sentQuery=node('input'),sentStatus=node('select'),sentSort=node('select'),sentSummary=node('p','received-summary'),sentError=node('p','message error'),sentPages=node('nav','received-pages');
sentQuery.id='sent-query';sentQuery.type='search';sentQuery.maxLength=100;sentQuery.placeholder='업무명, 문서명, 인수자 검색';sentStatus.id='sent-status';sentSort.id='sent-sort';sentError.hidden=true;sentError.setAttribute('role','status');sentSummary.setAttribute('role','status');sentPages.setAttribute('aria-label','보낸 요청 페이지');
for(const [value,label] of [['all','모든 상태'],['requested','인수자 열람 대기'],['reviewing','인수자 검토 중'],['needs_info','보완 요청'],['accepted','인수 수락 · 완료 대기'],['completed','최종 인수 완료']])sentStatus.append(new Option(label,value));
for(const [value,label] of [['created','최근 요청순'],['updated','최근 처리순'],['title','문서명순']])sentSort.append(new Option(label,value));
for(const [label,field] of [['업무명 검색',sentQuery],['진행 상태',sentStatus],['정렬',sentSort]]){const wrap=node('label','field',label);wrap.append(field);sentForm.append(wrap);}
const sentSearch=()=>{clearTimeout(sentSearchTimer);sentPage=1;void loadSentRequests();};sentForm.append(button('검색',sentSearch,'button secondary small'),button('검색 초기화',()=>{sentQuery.value='';sentStatus.value='all';sentSort.value='created';sentSearch();},'button secondary small'));
$('sent-requests').before(sentForm,sentSummary,sentError);$('sent-requests').after(sentPages);sentPanel.querySelector('h2').textContent='보낸 요청 목록';
let sentPage=1,sentEpoch=0,sentPending=null,sentPendingKey='',sentSearchTimer=null,sentPoll=null,sentFailures=0;
function paintSentRequests(data){
 sentSummary.textContent='검색 결과 '+data.filtered_total+'건 / 전체 '+data.total+'건 · '+data.page+'페이지';sentPage=data.page;
 const host=$('sent-requests');host.replaceChildren();for(const r of data.items)host.append(handoverRequestCard(r,'sent'));
 if(!data.items.length)host.append(node('p','received-empty',data.total?'검색 조건에 맞는 요청이 없습니다. 검색어나 상태를 바꿔 보세요.':'아직 보낸 인수인계 요청이 없습니다.'));
 sentPages.replaceChildren();for(const [label,delta] of [['이전',-1],['다음',1]]){const b=button(label,()=>{sentPage+=delta;void loadSentRequests();},'button secondary small');b.disabled=delta<0?data.page<=1:data.page*data.page_size>=data.filtered_total;sentPages.append(b);}sentPages.hidden=data.filtered_total<=data.page_size;sentError.hidden=true;
}
async function loadSentRequests(force=false){
 if(!account.user)return;const uid=account.user.id,params=new URLSearchParams({box:'sent',page:sentPage,page_size:20,q:sentQuery.value.trim(),status:sentStatus.value,sort:sentSort.value}),key=uid+':'+params;
 if(!force&&sentPending&&sentPendingKey===key)return sentPending;const epoch=++sentEpoch;sentPendingKey=key;
 const task=(async()=>{try{const data=await api('/api/requests?'+params);if(epoch!==sentEpoch||uid!==account.user?.id||data.user_id!==uid||data.box!=='sent')return;paintSentRequests(data);sentFailures=0;}catch(e){if(epoch!==sentEpoch||uid!==account.user?.id)return;sentFailures++;sentError.textContent=e.message+' 기존 목록은 유지됩니다. 새로 불러오기로 다시 확인하세요.';sentError.hidden=false;}})().finally(()=>{if(sentPending===task)sentPending=null;});sentPending=task;return task;
}
sentForm.onsubmit=e=>{e.preventDefault();sentSearch();};sentQuery.oninput=()=>{clearTimeout(sentSearchTimer);sentSearchTimer=setTimeout(sentSearch,300);};sentStatus.onchange=sentSort.onchange=sentSearch;
const sentListOriginal=renderRequestList;renderRequestList=function(id,rows){if(id==='sent-requests'){if(state.route==='sent')void loadSentRequests();return;}sentListOriginal(id,rows);};
const sentSyncOriginal=syncReceiptProgress;syncReceiptProgress=function(r){sentSyncOriginal(r);if(!r.can_send)return;const overview=$('request-detail').querySelector('.received-overview');if(!overview)return;overview.querySelector('.received-progress')?.replaceWith(sentRequestProgress(r));overview.querySelector('.received-detail-guide').textContent=sentNextAction(r);const preview=overview.querySelector('.received-card-actions .button');if(preview){preview.textContent='인수인계서 보기';preview.setAttribute('aria-label','인수인계서 보기');}if(state.route==='sent')void loadSentRequests(true);};
const sentReloadOriginal=$('reload-sent-requests').onclick;$('reload-sent-requests').onclick=async()=>{await loadSentRequests(true);await sentReloadOriginal();};
function scheduleSentRequests(){clearTimeout(sentPoll);sentPoll=setTimeout(async()=>{if(!document.hidden&&state.route==='sent')await loadSentRequests();scheduleSentRequests();},Math.min(300000,60000*2**Math.min(sentFailures,3)));}
window.addEventListener('hashchange',()=>{if(state.route==='sent')void loadSentRequests();});document.addEventListener('visibilitychange',()=>{if(!document.hidden&&state.route==='sent')void loadSentRequests();});
const sentInitializeOriginal=initialize;initialize=async function(){await sentInitializeOriginal();if(state.route==='sent')await loadSentRequests();scheduleSentRequests();};
