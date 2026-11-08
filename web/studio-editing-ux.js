/* Shared, approval-only paragraph editing in the normal and expanded preview. */
const studioSplit=node('div','studio-splitter');
studioSplit.tabIndex=0;studioSplit.setAttribute('role','separator');studioSplit.setAttribute('aria-orientation','vertical');studioSplit.setAttribute('aria-label','AI 대화와 문서 너비 조절');studioSplit.setAttribute('aria-valuemin','30');studioSplit.setAttribute('aria-valuemax','70');
studioPage.querySelector('.studio-chat').after(studioSplit);
const studioSplitKey=()=> 'baton-studio-split-v1:'+(account.user?.id||'local');
let studioSplitRatio=58,studioSplitOwner=null;
function studioSetSplit(value,save=false){studioSplitRatio=Math.max(30,Math.min(70,value));studioPage.style.setProperty('--studio-chat-ratio',studioSplitRatio+'fr');studioPage.style.setProperty('--studio-preview-ratio',(100-studioSplitRatio)+'fr');studioSplit.setAttribute('aria-valuenow',String(Math.round(studioSplitRatio)));studioSplit.setAttribute('aria-valuetext','AI 대화 '+Math.round(studioSplitRatio)+'%, 문서 '+Math.round(100-studioSplitRatio)+'%');if(save)try{localStorage.setItem(studioSplitKey(),String(studioSplitRatio));}catch{}}
function studioRestoreSplit(){const owner=studioSplitKey();if(owner===studioSplitOwner)return;studioSplitOwner=owner;let value=58;try{const saved=Number(localStorage.getItem(owner));if(Number.isFinite(saved)&&saved>=30&&saved<=70)value=saved;}catch{}studioSetSplit(value);}
studioSplit.onpointerdown=e=>{if(e.button!==0)return;e.preventDefault();studioSplit.setPointerCapture(e.pointerId);studioSplit.classList.add('dragging');document.body.classList.add('studio-resizing');};
studioSplit.onpointermove=e=>{if(!studioSplit.hasPointerCapture(e.pointerId))return;const box=studioPage.querySelector('.studio-layout').getBoundingClientRect();studioSetSplit((e.clientX-box.left)/box.width*100);};
function studioEndSplit(e){if(studioSplit.hasPointerCapture(e.pointerId))studioSplit.releasePointerCapture(e.pointerId);studioSplit.classList.remove('dragging');document.body.classList.remove('studio-resizing');studioSetSplit(studioSplitRatio,true);}
studioSplit.onpointerup=studioEndSplit;studioSplit.onpointercancel=studioEndSplit;studioSplit.ondblclick=()=>studioSetSplit(58,true);
studioSplit.onkeydown=e=>{const values={ArrowLeft:studioSplitRatio-2,ArrowRight:studioSplitRatio+2,Home:30,End:70};if(e.key in values){e.preventDefault();studioSetSplit(values[e.key],true);}};

const studioEditPanel=node('section','studio-expanded-editor');studioEditPanel.hidden=true;studioEditPanel.setAttribute('aria-label','전체 화면 AI 문장 수정');
const studioEditTitle=node('h3','','AI 문장 수정'),studioEditHelp=node('p','muted','문서에서 수정할 문장을 선택하세요.'),studioEditQuote=node('blockquote'),studioEditLabel=node('label','field','수정 지시'),studioEditInput=node('textarea');
studioEditInput.rows=2;studioEditInput.maxLength=8000;studioEditInput.placeholder='예: 더 간결하게, 공문서 문체로';studioEditInput.setAttribute('aria-label','전체 화면 AI 수정 지시');studioEditLabel.append(studioEditInput);
const studioEditPrompts=node('div','form-actions');for(const text of ['더 간결하게','공문서 문체로','구체적으로 작성'])studioEditPrompts.append(button(text,()=>{studioEditInput.value=text;studioEditInput.focus();},'button secondary small'));
const studioEditSend=button('AI 수정 요청',async()=>{
 const target=studioParagraphSelection,text=studioEditInput.value.trim();if(!target||!text||studioBusy)return;
 const previous=studioData.messages.at(-1)?.id;await studioSendParagraph(target,text);
 if(studioData?.messages.at(-1)?.id!==previous&&studioData.messages.at(-1)?.result?.paragraph_edit&&studioEditInput.value.trim()===text)studioEditInput.value='';
 studioRefreshExpandedEditor();
},'button primary');
const studioEditClear=button('선택 해제',()=>{studioClearParagraph();studioEditInput.value='';studioRefreshExpandedEditor();},'text-button');
const studioEditResult=node('div','studio-expanded-result'),studioEditStatus=node('p','studio-expanded-status');studioEditStatus.setAttribute('role','status');
studioEditPanel.append(studioEditTitle,studioEditHelp,studioEditQuote,studioEditLabel,studioEditPrompts,studioEditSend,studioEditClear,studioEditStatus,studioEditResult);
let studioEditScope='',studioEditTarget=null;
function studioRefreshExpandedEditor(){
 const scope=studioData?studioData.session.id+':'+studioData.draft?.id:'';
 if(scope!==studioEditScope){studioEditScope=scope;studioEditTarget=null;studioEditInput.value='';studioEditResult.replaceChildren();}
 const viewer=document.querySelector('.studio-paper-expanded'),target=studioParagraphSelection;
 studioEditPanel.hidden=!viewer;if(!viewer)return;
 viewer.append(studioEditPanel);viewer.classList.toggle('studio-paper-editing',!!target||!!studioEditTarget);
 if(target){studioEditTarget=target.id;studioEditQuote.textContent=target.before;}
 else studioEditQuote.textContent='';
 studioEditQuote.hidden=!target;studioEditLabel.hidden=!target;studioEditPrompts.hidden=!target;studioEditSend.hidden=!target;studioEditClear.hidden=!target;
 studioEditHelp.textContent=target?'선택한 원문만 수정합니다. 결과를 비교하고 반영해야 저장됩니다.':'문서의 문장을 누른 뒤 ‘AI 수정 요청’을 선택하세요.';
 studioEditSend.disabled=studioBusy||!target;studioEditSend.textContent=studioBusy?'AI 수정안 준비 중…':'AI 수정 요청';studioEditInput.disabled=studioBusy;studioEditClear.disabled=studioBusy;studioEditPrompts.querySelectorAll('button').forEach(b=>b.disabled=studioBusy);
 studioEditStatus.textContent=$('studio-notice').hidden?'':$('studio-notice').textContent;
 const latest=[...(studioData?.messages||[])].reverse().find(m=>m.result?.paragraph_edit?.id===studioEditTarget);
 if(latest){const compare=$('studio-history').querySelector('[data-message-id="'+latest.id+'"] .studio-paragraph-comparison');if(compare)studioEditResult.replaceChildren(compare);}else studioEditResult.replaceChildren();
}
window.addEventListener('studio-paragraph-selected',()=>{studioRefreshExpandedEditor();studioEditInput.focus();});
window.addEventListener('studio-paper-fullscreen',()=>{if(!document.querySelector('.studio-paper-expanded')){studioEditPanel.hidden=true;studioRender({preserveScroll:true});}else studioRefreshExpandedEditor();});
const studioUxControls=studioControls;studioControls=function(){studioUxControls();studioRestoreSplit();studioRefreshExpandedEditor();};
const studioUxRender=studioRender;studioRender=function(options={}){studioUxRender(options);studioRestoreSplit();studioRefreshExpandedEditor();};
const studioUxWelcome=studioWelcome;studioWelcome=function(box){
 studioUxWelcome(box);const count=studioData?.documents.length||0,greeting=box.querySelector('.studio-greeting');
 greeting.querySelector('h2').textContent=count?'첨부자료로 인수인계서를 작성해 볼까요?':'담당 업무를 알려 주세요.';
 greeting.querySelector('p').textContent=count?'자료 '+count+'개가 연결되어 있습니다. 원하는 작성 방향을 입력하거나 아래 요청을 선택하세요.':'업무자료를 첨부하거나, 맡은 업무와 전달할 내용을 적어 주세요.';
 const prompts=greeting.querySelectorAll('.studio-prompt');if(!count){prompts[0].textContent='자료 첨부하고 시작';prompts[0].onclick=()=>void studioChooseFiles();}if(!studioData?.draft){prompts[2].hidden=true;prompts[3].hidden=true;}
};
// A document switch clears both the binding and any instruction tied to it.
const studioUxClear=studioClearParagraph;studioClearParagraph=function(){const selected=!!studioParagraphSelection;studioUxClear();if(selected)$('studio-input').value='';studioEditInput.value='';const frame=studioPaperFrame?.querySelector('iframe');frame?.contentWindow?.postMessage({type:'baton-paper-clear',epoch:studioPaperEpoch},'*');};
window.addEventListener('beforeunload',e=>{if(studioEditInput.value.trim()){e.preventDefault();e.returnValue='';}});
studioRestoreSplit();
