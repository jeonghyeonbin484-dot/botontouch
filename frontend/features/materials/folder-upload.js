$('choose-folder').onclick=()=>$('folder-upload').click();$('folder-upload').onchange=()=>{stageFiles($('folder-upload').files);$('folder-upload').value='';};
