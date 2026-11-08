/* 문단 위치 선택 → 기존 AI 대화 → 전후 비교 → 명시적 반영. */
let studioParagraphSelection=null;
const studioParagraphChip=node('section','studio-paragraph-selection');studioParagraphChip.hidden=true;studioParagraphChip.setAttribute('aria-label','AI 수정 대상 문단');$('studio-input').before(studioParagraphChip);
function studioSelectParagraph(target){
 if(studioBusy)return;studioParagraphSelection=target;studioParagraphChip.replaceChildren(node('strong','','선택한 원문 문단만 수정합니다'),node('p','',target.before));
 const actions=node('div','form-actions');for(const text of ['더 간결하게','공문서 문체로','구체적으로 작성'])actions.append(button(text,()=>{$('studio-input').value=text;$('studio-input').focus();},'button secondary small'));
 actions.append(button('선택 해제',studioClearParagraph,'text-button'));studioParagraphChip.append(actions);studioParagraphChip.hidden=false;studioPage.dataset.tab='chat';studioControls();$('studio-input').focus();
}
function studioClearParagraph(){studioParagraphSelection=null;studioParagraphChip.hidden=true;studioParagraphChip.replaceChildren();studioControls();}
const studioParagraphControlsOriginal=studioControls;studioControls=function(){studioParagraphControlsOriginal();if(studioParagraphSelection)$('studio-mode').disabled=true;studioParagraphChip.querySelectorAll('button').forEach(b=>b.disabled=studioBusy);};
async function studioSendParagraph(target,text,nonce=crypto.randomUUID(),retry=false){
 if(studioBusy||!text)return;if(studioData?.session.id!==target.session_id||studioData?.draft?.id!==target.draft_id){studioNotice('선택한 문서를 다시 열고 문단을 선택하세요.',true);return;}
 await studioOperation(async()=>{try{studioData=await post('/api/studio/sessions/'+target.session_id+'/paragraphs',{draft_id:target.draft_id,target_id:target.id,baseline:target.baseline,text,nonce,retry});if($('studio-input').value.trim()===text)$('studio-input').value='';studioRender();}catch(error){try{studioData=await api('/api/studio/sessions/'+target.session_id);studioRender();}catch{}throw error;}});
}
async function studioRetryParagraph(message){const target={...message.result.paragraph_request,session_id:studioData.session.id};await studioSendParagraph(target,message.content,message.nonce,true);}
const studioParagraphSendOriginal=studioSend;studioSend=async function(retry){if(!retry&&studioParagraphSelection){await studioSendParagraph(studioParagraphSelection,$('studio-input').value.trim());return;}await studioParagraphSendOriginal(retry);};
async function studioParagraphAction(message,action){const sid=studioData.session.id;await studioOperation(async()=>{studioData=await post('/api/studio/sessions/'+sid+'/'+action,{message_id:message.id});studioRender();if(action!=='paragraph-reject'){await studioList();studioNotice(action==='paragraph-undo'?'선택 문단을 이전 내용으로 되돌렸습니다. 이력은 유지됩니다.':'선택 문단의 승인된 수정만 저장했습니다. 원문과 비교해 다시 검토하세요.');}});}
const studioParagraphRenderOriginal=studioRender;studioRender=function(options={}){
 studioParagraphRenderOriginal(options);
 if(studioParagraphSelection&&(studioData?.session.id!==studioParagraphSelection.session_id||studioData?.draft?.edit_token!==studioParagraphSelection.baseline))studioClearParagraph();
 for(const message of studioData?.messages||[]){const edit=message.result?.paragraph_edit;if(!edit)continue;const host=$('studio-history').querySelector('[data-message-id="'+message.id+'"]');if(!host)continue;
  const compare=node('section','studio-paragraph-comparison');compare.setAttribute('aria-label','선택 문단 수정 전후 비교');
  for(const [label,text] of [['수정 전',edit.before],['수정 후',edit.after]]){const group=node('div');group.append(node('strong','',label),node('p','',text));compare.append(group);}
  const actions=node('div','form-actions');if(message.proposal_state==='pending'){
   const apply=button('수정 반영',()=>void studioParagraphAction(message,'paragraph-apply'),'button primary');apply.dataset.studioMutation='1';
   const cancel=button('취소',()=>void studioParagraphAction(message,'paragraph-reject'),'button secondary');cancel.dataset.studioMutation='1';actions.append(apply,cancel);
  }else if(message.proposal_state==='paragraph_applied'){
   actions.append(node('span','badge','수정 반영됨'));const undo=button('이 수정 되돌리기',()=>void studioParagraphAction(message,'paragraph-undo'),'button secondary');undo.dataset.studioMutation='1';actions.append(undo);
  }else actions.append(node('span','badge',message.proposal_state==='paragraph_reverted'?'이전 내용으로 되돌림':'취소한 수정안'));
  compare.append(actions);host.append(compare);
 }
 studioControls();
};
