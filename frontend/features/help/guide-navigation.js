
// Guide navigation is local-only; it does not save data or request AI.
document.querySelectorAll('[data-guide-jump]').forEach(button=>button.addEventListener('click',()=>{const section=document.getElementById(button.dataset.guideJump);if(section){section.focus({preventScroll:true});section.scrollIntoView({behavior:'auto',block:'start'});}}));
