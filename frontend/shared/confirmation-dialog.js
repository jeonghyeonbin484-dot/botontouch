let confirmResolver=null;
function confirmAction(title,description,accept='삭제하기'){return new Promise(resolve=>{if(confirmResolver){resolve(false);return;}$('confirm-title').textContent=title;$('confirm-description').textContent=description;$('confirm-accept').textContent=accept;$('confirm-accept').className='button '+(accept==='삭제하기'?'danger':'primary');confirmResolver=resolve;$('confirm-dialog').showModal();$('confirm-cancel').focus();});}
function settleConfirmation(value){$('confirm-dialog').close();const resolve=confirmResolver;confirmResolver=null;resolve?.(value);}
$('confirm-cancel').onclick=()=>settleConfirmation(false);$('confirm-accept').onclick=()=>settleConfirmation(true);$('confirm-dialog').addEventListener('cancel',event=>{event.preventDefault();settleConfirmation(false);});
