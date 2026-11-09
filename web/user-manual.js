/* 직원용 사용 안내. 기존 검색·목차·인쇄 기능을 유지한다. */
const manualChapters=[
  {
    "title": "바통터치 시작하기",
    "image": "home-20261109",
    "steps": [
      "바통터치는 업무자료를 정리하고 인수인계서를 작성해 후임자에게 전달하는 도구입니다.",
      "로그인한 뒤 홈에서 인수인계 시작하기를 누르세요. 자료 등록, 초안 작성, 질문·답변 확인, 후임자 지정, 요청 발송 순서로 진행합니다.",
      "이미 작성하던 업무가 있다면 홈의 작성 중인 인수인계에서 문서를 선택하세요."
    ],
    "tip": "처음에는 동영상 사용 가이드를 함께 보며 따라 해 보세요."
  },
  {
    "title": "로그인과 로그아웃",
    "image": "login-20261109",
    "steps": [
      "로그인 화면에서 본인의 새올 ID와 바통터치 비밀번호를 입력한 뒤 로그인을 누르세요.",
      "처음 로그인한 뒤 비밀번호 변경 화면이 나오면 새 비밀번호를 두 번 입력하고 비밀번호 설정을 누르세요.",
      "로그인 후 비밀번호를 바꾸려면 오른쪽 위 이름을 누르고 비밀번호 변경을 선택하세요.",
      "업무를 마치면 오른쪽 위 이름을 누르고 로그아웃을 선택하세요."
    ],
    "tip": "비밀번호를 잊었거나 로그인할 수 없으면 관리자에게 문의하세요. 비밀번호는 다른 사람에게 알려 주지 마세요."
  },
  {
    "title": "홈과 왼쪽 메뉴",
    "image": "home-20261109",
    "steps": [
      "홈에서 작성 중인 인수인계, 받은 요청, 보낸 요청과 완료된 인수인계를 확인하세요.",
      "새 업무는 인수인계 시작하기 또는 오른쪽 위 새 인수인계 버튼으로 시작하세요.",
      "받은 인수인계에서 본인에게 온 문서를, 보낸 인수인계에서 본인이 전달한 문서를 확인하세요.",
      "자료함에서는 업무자료, 인수인계 문서, AI 작성 대화를 선택해 필요한 자료와 기록을 찾으세요.",
      "대화방에서 인계자 또는 인수자와 메시지를 주고받으세요."
    ],
    "tip": "화면이 좁아 왼쪽 메뉴가 보이지 않으면 왼쪽 위 메뉴 버튼을 누르세요."
  },
  {
    "title": "새 인수인계 작성",
    "image": "journey-20261109",
    "steps": [
      "왼쪽 인수인계 시작하기를 누르고 인계할 업무명을 입력하세요. 예: 사무용품 구매 및 관리.",
      "업무 저장하고 자료 등록을 누른 뒤 업무자료를 등록하세요. 업무명 아래 저장 안내도 확인하세요.",
      "자료 등록이 끝나면 다음: AI 초안 작성을 누르세요. 화면 위의 단계 표시로 현재 위치를 확인할 수 있습니다.",
      "이전 단계로 돌아가려면 이전을 누르세요. 작업을 쉬려면 임시저장을 누르고 저장 완료 안내를 확인하세요."
    ],
    "tip": "저장이 끝나기 전에 창을 닫지 마세요. 저장에 실패하면 현재 내용을 유지한 채 다시 저장하세요."
  },
  {
    "title": "업무자료 등록과 찾기",
    "image": "files-20261109",
    "steps": [
      "1단계 업무자료 등록에서 파일 선택 또는 폴더 선택을 누르세요. 사용할 파일이 목록에 나타나는지 확인하세요.",
      "선택한 자료 등록을 누르고 등록완료 표시를 확인하세요. 이미 등록완료인 파일은 다시 등록하지 않아도 됩니다.",
      "글자를 선택할 수 있는 PDF, 한글 문서인 HWPX, 엑셀 문서인 XLSX, 텍스트 문서인 TXT를 사용할 수 있습니다.",
      "등록에 실패한 파일은 안내를 읽고 파일 크기, 암호 설정, 파일 형식을 확인하세요. 사진으로 된 문서는 글자를 읽을 수 있는 문서로 준비하세요.",
      "기존 자료는 자료함의 업무자료에서 검색하세요. 미리보기로 내용을 확인하고 필요한 자료를 선택한 뒤 선택한 자료 연결을 누르세요."
    ],
    "tip": "파일 크기는 선택할 때 표시되는 안내를 따르세요. 자료를 바꾼 뒤에는 초안의 내용도 다시 확인하세요."
  },
  {
    "title": "AI로 초안 작성하기",
    "image": "draft-20261109",
    "steps": [
      "2단계 AI 초안 작성에서 사용할 등록 자료를 선택하고 Gemini로 초안 만들기를 누르세요. 진행 중에는 완료 안내를 기다리세요.",
      "완성된 초안의 업무 내용, 일정, 진행사항과 출처 보기를 확인하세요. 자료에 없는 내용은 확인 필요로 남겨 두세요.",
      "대화로 작성하려면 왼쪽 AI 대화로 작성을 누르세요. 자료 첨부 또는 자료함에서 선택으로 업무자료를 준비하세요.",
      "입력창에 원하는 내용을 적고 전송을 누르세요. 예: 첨부한 자료를 바탕으로 후임자가 해야 할 일을 정리해 주세요.",
      "현재 작성 중인 인수인계서에서 기존 대화를 선택해 이어갈 수 있습니다. 다른 업무를 시작하려면 새 업무 시작을 누르세요.",
      "AI가 제안한 내용을 읽고 수정한 뒤 문서에 반영을 누르세요. 저장된 인수인계서에 원하는 내용이 반영됐는지 확인하세요."
    ],
    "tip": "AI가 작성한 일정, 금액, 담당자는 반드시 자료와 비교하세요. 업무자료는 기관에서 사용을 허용한 범위에서만 첨부하세요."
  },
  {
    "title": "AI 예상 질문·답변 확인",
    "image": "qa-20261109",
    "steps": [
      "3단계 AI 예상 질문·답변에서 AI 예상 질문 만들기를 누르세요.",
      "후임자가 궁금해할 질문과 추천 답변을 읽고, 질문과 답변을 직접 수정한 뒤 답변 확인·저장을 누르세요.",
      "필요한 질문이 없으면 질문 직접 추가를 누르세요. 자료가 필요하면 해당 질문에 첨부하세요.",
      "관련 없는 질문은 해당 없음으로, 아직 답하기 어려운 질문은 나중에 처리로 표시하세요.",
      "답변을 문서에 반영을 누르면 수정 전후 내용을 비교할 수 있습니다. 내용을 확인한 뒤 반영하세요.",
      "문서와 후임자에게 전달할 질문을 선택하고 마지막 검토 확인란을 체크한 뒤 다음 단계로 이동하세요."
    ],
    "tip": "추천 답변이 정확한지 직접 확인하세요. 알 수 없는 내용은 추가 확인 필요로 남겨 두세요."
  },
  {
    "title": "내용 수정과 문서 미리보기",
    "image": "preview-20261109",
    "steps": [
      "2단계에서 항목을 펼치고 업무 내용을 직접 수정하세요. 긴 문서는 모두 펼치기 또는 모두 접기를 이용하세요.",
      "AI 대화로 작성 화면에서는 저장된 인수인계서에서 문장을 선택해 직접 고치거나 AI 수정 요청을 할 수 있습니다. 수정안을 비교한 뒤 반영하세요.",
      "내용을 수정한 뒤 저장 또는 임시저장을 누르고 완료 안내를 확인하세요.",
      "오른쪽 저장된 인수인계서에서 문서를 확인하세요. 미리보기가 접혀 있으면 문서 미리보기 펼치기를 누르세요.",
      "자료함의 인수인계 문서에서 열어서 수정을 누르면 작성하던 문서를 이어서 수정할 수 있습니다."
    ],
    "tip": "AI 답변이 나왔다고 바로 저장되는 것은 아닙니다. 문서에 반영한 내용과 저장 완료 여부를 확인하세요."
  },
  {
    "title": "후임자 지정과 요청 발송",
    "image": "recipient-20261109",
    "steps": [
      "4단계 후임자 지정에서 인수받을 부서를 선택하세요. 해당 부서 직원이 표시됩니다.",
      "직원 이름·직급 검색에 이름을 입력해 직원을 찾으세요. 다른 부서 직원도 검색할 수 있습니다.",
      "직원을 선택하고 성명, 직급, 실제 소속 부서를 확인한 뒤 후임자 확정을 누르세요.",
      "검색어를 지우면 현재 선택한 부서 직원 목록으로 돌아갑니다. 직원이 보이지 않으면 직원 조회를 눌러 보세요.",
      "5단계에서 최종 문서, 전달할 질문·답변, 인수자를 확인하세요. 최종 검토를 확인한 뒤 인수인계 요청하기를 누르세요.",
      "확인창에서 인수자를 다시 확인하고 발송하세요. 보낸 인수인계에서 발송된 요청을 확인하세요."
    ],
    "tip": "아직 계정을 발급받지 않은 직원도 선택할 수 있습니다. 선택할 수 없는 직원은 안내를 확인하고 관리자에게 문의하세요."
  },
  {
    "title": "받은 인수인계 검토",
    "image": "request-detail-20261109",
    "steps": [
      "받은 인수인계에서 업무명을 확인하고 인수인계서 확인을 누르세요.",
      "진행·질문 확인을 눌러 인계자, 전달 문서, 첨부자료와 질문·답변을 확인하세요.",
      "부족한 내용은 추가 질문으로 남기거나 보완 요청에 사유를 작성하세요.",
      "인계자가 답변하거나 문서를 다시 전달하면 변경된 내용과 처리 이력을 확인하세요.",
      "검토가 끝나면 답변 확인 완료 등 화면에 표시된 확인 절차를 마치고 인수 수락을 누르세요."
    ],
    "tip": "인수 수락 후에는 인계자가 최종 완료합니다. 받은 문서와 자료는 업무에 필요한 범위에서만 사용하세요."
  },
  {
    "title": "대화방과 질문 활용",
    "image": "request-detail-20261109",
    "steps": [
      "왼쪽 대화방에서 대화할 업무를 선택하세요. 요청 상세의 대화하기로도 같은 대화방을 열 수 있습니다.",
      "인수자는 인계자에게 질문하기를, 인계자는 인수자와 대화하기를 눌러 대화를 시작할 수 있습니다.",
      "메시지를 입력하고 보내기를 누르세요. 필요한 자료는 파일 보내기로 전달하세요.",
      "읽지 않은 메시지 수를 확인하세요. 알림을 사용하려면 알림 설정을 열고 원하는 알림을 켜세요.",
      "중요한 메시지는 업무 노하우로 저장할 수 있습니다. 문서에 넣기 전에는 내용을 다시 확인하세요.",
      "자료에 관한 AI 답변이 필요하면 자료 기반 질문을 이용하고 답변의 출처를 확인하세요."
    ],
    "tip": "직원 간 대화와 AI에게 묻는 질문은 서로 다릅니다. 사이트를 닫은 동안에는 새 메시지 알림을 놓칠 수 있으니 받은 대화도 확인하세요."
  },
  {
    "title": "한글 문서 내려받기",
    "image": "preview-20261109",
    "steps": [
      "수정 내용을 저장하세요. AI 대화로 작성에서는 남양주시 양식 다운로드를 누르세요.",
      "인수인계 문서의 문서 내려받기·복사에서는 한글(HWPX)을 선택하세요. 받은 요청 상세에서는 요청 문서 한글 내려받기를 누르세요.",
      "내려받은 파일을 한글 프로그램에서 열어 제목, 업무 내용, 인계자와 인수자 정보를 확인하세요.",
      "문서 끝의 업무 인계·인수 요약서도 확인하세요. 필요한 경우 한글 프로그램에서 수정하고 저장하세요.",
      "문서를 다른 사람에게 전달하기 전에 모든 페이지를 확인하세요. 미리보기와 한글에서 보이는 줄바꿈이나 페이지 나눔이 다를 수 있습니다."
    ],
    "tip": "최종 한글 문서에는 출처 번호를 표시하지 않습니다. 업무 내용의 근거는 바통터치의 출처 보기에서 확인하세요."
  },
  {
    "title": "완료한 업무와 이전 기록",
    "image": "library-20261109",
    "steps": [
      "인수자가 수락한 뒤 보낸 인수인계에서 요청을 열고 처리 결과를 확인하세요.",
      "남은 질문과 보완사항을 확인한 뒤 최종 완료를 누르세요.",
      "자료함의 인수인계 문서에서 작성 중 문서와 완료 문서를 구분해 확인하세요.",
      "업무자료에서는 파일을, AI 작성 대화에서는 이전 작성 대화를 검색할 수 있습니다.",
      "완료 당시 문서와 대화는 해당 요청 상세에서 확인하세요. 나중에 수정한 작업 문서와 구분하세요."
    ],
    "tip": "업무 연습에는 가상자료를 사용하고 실제 직원에게 연습 요청을 보내지 마세요."
  },
  {
    "title": "자주 묻는 질문",
    "steps": []
  }
];
const manualFaq=[
  [
    "로그인이 안 됩니다.",
    "새올 ID와 비밀번호를 다시 확인하세요. 여러 번 실패했다면 잠시 후 다시 시도하고, 계속 안 되면 관리자에게 문의하세요."
  ],
  [
    "비밀번호는 어디서 바꾸나요?",
    "오른쪽 위 이름을 누르고 비밀번호 변경을 선택하세요."
  ],
  [
    "작성하던 문서는 어디서 찾나요?",
    "홈의 작성 중인 인수인계 또는 자료함의 인수인계 문서에서 찾으세요. 열어서 수정을 누르면 이어서 작성할 수 있습니다."
  ],
  [
    "다음 단계로 이동할 수 없습니다.",
    "현재 단계의 안내를 확인하세요. 자료 등록, 초안 저장, 질문 검토, 후임자 확정 중 아직 끝내지 않은 항목을 완료하세요."
  ],
  [
    "AI 초안이 나오지 않습니다.",
    "등록완료 자료가 선택됐는지 확인하세요. 화면의 오류 안내를 읽고 잠시 후 다시 시도하세요. 계속 실패하면 관리자에게 문의하세요."
  ],
  [
    "오늘 AI 사용 한도에 도달했다고 나옵니다.",
    "현재 내용은 그대로 두고 안내된 시간 이후에 다시 이용하세요. 필요한 내용은 직접 작성하고 저장할 수 있습니다."
  ],
  [
    "파일 등록에 실패했습니다.",
    "지원하는 파일 형식인지, 암호가 설정돼 있는지, 화면의 용량 안내를 넘지 않는지 확인하세요. 사진으로 된 문서는 글자를 읽을 수 있는 문서로 준비하세요."
  ],
  [
    "이미 등록완료인데 다시 등록해야 하나요?",
    "다시 등록하지 않아도 됩니다. 등록된 자료를 선택해 다음 단계로 진행하세요."
  ],
  [
    "AI 내용이 틀렸습니다.",
    "출처 보기로 자료와 비교하고 직접 고쳐 저장하세요. 확인되지 않은 내용은 확인 필요로 남겨 두세요."
  ],
  [
    "다른 부서 직원도 찾을 수 있나요?",
    "직원 이름·직급 검색에 이름을 입력하세요. 실제 소속 부서와 직급을 확인한 뒤 후임자 확정을 누르세요."
  ],
  [
    "후임자를 잘못 선택했습니다.",
    "발송 전이라면 4단계로 돌아가 올바른 직원을 선택하고 후임자 확정을 누르세요. 이미 발송했다면 요청 상세에서 가능한 조치를 확인하고 관리자에게 문의하세요."
  ],
  [
    "후임자 질문은 어디서 확인하나요?",
    "보낸 인수인계에서 해당 요청의 진행 상황 확인을 누르거나 대화방을 확인하세요."
  ],
  [
    "한글 문서가 내려받아지지 않습니다.",
    "먼저 수정 내용을 저장하세요. 화면의 오류 안내와 다운로드 차단 여부를 확인한 뒤 다시 내려받으세요."
  ],
  [
    "오른쪽 문서가 보이지 않습니다.",
    "먼저 문서에 반영하고 저장됐는지 확인하세요. 문서 미리보기 펼치기 또는 다시 불러오기를 누르세요."
  ],
  [
    "자동으로 저장되나요?",
    "업무명 입력이나 단계 이동 뒤 저장 안내를 확인하세요. 중요한 수정 후에는 저장 또는 임시저장을 직접 누르고 완료 안내를 확인하세요."
  ],
  [
    "모바일에서도 사용할 수 있나요?",
    "사용할 수 있습니다. 왼쪽 메뉴가 안 보이면 메뉴 버튼을 누르세요. 파일 선택과 내려받기 방법은 사용하는 기기에 따라 다를 수 있습니다."
  ],
  [
    "모의 AI 응답이라고 나옵니다.",
    "실제 자료 분석 결과가 아닌 연습용 답변입니다. 업무에 그대로 사용하지 말고 내용을 직접 확인하세요."
  ],
  [
    "자료를 바꾸면 초안도 바뀌나요?",
    "자동으로 바뀌지 않습니다. 최신 자료로 초안을 다시 만들거나 직접 수정하고 근거를 확인하세요."
  ],
  [
    "완료 후에도 문서와 대화를 볼 수 있나요?",
    "받은 인수인계 또는 보낸 인수인계에서 해당 요청을 열어 문서, 처리 이력과 대화를 확인하세요."
  ]
];
routes.guide=['사용 방법','바통터치 사용자 매뉴얼','필요한 장을 선택하고 화면의 메뉴와 버튼을 따라 해 보세요.','사용자 매뉴얼'];
const manualPage=$('page-guide');manualPage.replaceChildren();manualPage.classList.add('manual-page');manualPage.innerHTML='<div class="manual-header"><h2>바통터치 사용자 매뉴얼</h2><div><a href="#video-guide" class="button secondary small">동영상 사용 가이드</a><button id="manual-print" class="button secondary small">인쇄·PDF 저장</button></div></div><label class="manual-search">궁금한 기능 검색<input id="manual-search" type="search" placeholder="예: 자료 등록, 저장, 후임자, 한글 문서"></label><p id="manual-search-status" role="status"></p><div class="manual-layout"><details class="manual-toc" open><summary>목차</summary><nav id="manual-toc" aria-label="사용자 매뉴얼 목차"></nav></details><div id="manual-content"></div></div><div class="manual-pagination"><button id="manual-prev" class="button secondary">이전 장</button><button id="manual-top" class="text-button">맨 위로</button><button id="manual-next" class="button primary">다음 장</button></div>';
let manualIndex=0;const manualImageDialog=node('dialog','manual-image-dialog');manualImageDialog.setAttribute('aria-label','안내 화면 확대');manualImageDialog.append(button('닫기',()=>manualImageDialog.close(),'button secondary'));const manualLargeImage=node('img');manualLargeImage.alt='사용 가이드 화면 확대';manualImageDialog.append(manualLargeImage);document.body.append(manualImageDialog);
function manualGo(index){manualIndex=index;manualSearch.value='';manualRender();manualPage.scrollIntoView({block:'start'});$('manual-content').focus({preventScroll:true});}
const manualSearch=$('manual-search');$('manual-content').tabIndex=-1;
function manualArticle(chapter,index){const article=node('article','manual-chapter');article.append(node('small','muted','제'+(index+1)+'장'),node('h2','',chapter.title));if(index===0){const flow=node('ol','manual-flow');for(const t of ['로그인','자료 등록','AI 초안','전임자 검토','후임자 지정','요청·수락','최종 완료'])flow.append(node('li','',t));article.append(flow);}if(chapter.image){const figure=node('figure','manual-figure'),image=node('img');image.src='/media/manual/'+chapter.image+'.png';image.alt=chapter.title+' 안내 화면';image.loading='lazy';image.onerror=()=>{image.hidden=true;figure.querySelector('figcaption').textContent='이 장의 단계별 설명을 따라 진행하세요. 화면 캡처를 불러오지 못했습니다.';};image.onclick=()=>{manualLargeImage.src=image.src;manualImageDialog.showModal();};figure.append(image,node('figcaption','','사용할 메뉴와 버튼을 확인하세요. 그림을 누르면 크게 볼 수 있습니다.'));article.append(figure);}const list=node('ol','manual-steps');for(const text of chapter.steps)list.append(node('li','',text));article.append(list);if(chapter.tip)article.append(node('aside','guide-tip',chapter.tip));if(index===13)for(const [q,a] of manualFaq){const details=node('details','manual-faq');details.append(node('summary','',q),node('p','',a));article.append(details);}return article;}
function manualRender(){const q=manualSearch.value.trim().toLocaleLowerCase('ko'),toc=$('manual-toc'),content=$('manual-content');toc.replaceChildren();content.replaceChildren();let matches=0;manualChapters.forEach((chapter,i)=>{const hit=!q||[chapter.title,...chapter.steps,chapter.tip||'',...(i===13?manualFaq.flat():[])].join(' ').toLocaleLowerCase('ko').includes(q);if(!hit)return;matches++;const b=button((i+1)+'. '+chapter.title,()=>manualGo(i),'manual-toc-button');if(!q&&i===manualIndex)b.setAttribute('aria-current','page');toc.append(b);if(q||i===manualIndex)content.append(manualArticle(chapter,i));});$('manual-search-status').textContent=q?'검색 결과 '+matches+'개 장':'원하는 장을 선택하거나 검색하세요.';$('manual-prev').disabled=!!q||manualIndex===0;$('manual-next').disabled=!!q||manualIndex===manualChapters.length-1;if(!matches)content.append(node('p','','검색 결과가 없습니다. 다른 단어를 입력하세요.'));}
manualSearch.oninput=manualRender;$('manual-prev').onclick=()=>manualGo(manualIndex-1);$('manual-next').onclick=()=>manualGo(manualIndex+1);$('manual-top').onclick=()=>manualPage.scrollIntoView({behavior:'smooth'});$('manual-print').onclick=async()=>{const q=manualSearch.value;manualSearch.value='';const box=$('manual-content');box.replaceChildren(...manualChapters.map(manualArticle));box.querySelectorAll('details').forEach(d=>d.open=true);await Promise.all([...box.querySelectorAll('img')].map(i=>i.decode().catch(()=>{})));window.print();manualSearch.value=q;manualRender();};manualRender();
