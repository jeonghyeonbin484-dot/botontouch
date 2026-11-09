'use strict';
const $ = id => document.getElementById(id);
const paths = {
 grid:'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
 folder:'M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z',
 spark:'m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3zM20 2v4M18 4h4',
 chat:'M21 11a8 8 0 0 1-8 8H7l-5 3 2-6a8 8 0 1 1 17-5zM8 10h8M8 14h5',
 check:'m7 12 3 3 7-7M20 11v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h10',
 settings:'M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1 1-3zM15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0z',
 shield:'M12 3 3 7v6c0 4 5 7 9 9 4-2 9-5 9-9V7l-9-4zm-4 9 3 3 5-5',
 arrow:'M5 12h14m-5-5 5 5-5 5',plus:'M12 5v14M5 12h14',menu:'M4 6h16M4 12h16M4 18h16',
 document:'M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-6-6zm0 0v6h6M8 13h8M8 17h5',
 clock:'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0zM12 7v5l3 2',calendar:'M4 5h16v16H4zM8 2v6M16 2v6M4 10h16M8 14h2M14 14h2',
 upload:'M12 16V3m-5 5 5-5 5 5M3 15v5h18v-5',download:'M12 3v13m-5-5 5 5 5-5M3 17v4h18v-4',
 search:'M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0zm-2 5 6 6',info:'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0zM12 11v6M12 7v1',
 save:'M4 3h13l4 4v14H3V3h1zm3 0v6h10V3M7 21v-7h10v7',copy:'M8 8h13v13H8zM16 8V3H3v13h5',
 trash:'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7',
 close:'m6 6 12 12M18 6 6 18',edit:'m14 4 6 6M3 21l5-1L21 7l-6-6L2 14l-1 6z',
 reset:'M3 11a9 9 0 1 1 2 7M3 4v7h7',user:'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0zM4 21v-2a8 8 0 0 1 16 0v2'
};
function icon(name){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('fill','none');svg.setAttribute('stroke','currentColor');svg.setAttribute('stroke-linecap','round');svg.setAttribute('stroke-linejoin','round');svg.setAttribute('aria-hidden','true');const p=document.createElementNS(svg.namespaceURI,'path');p.setAttribute('d',paths[name]||paths.document);svg.append(p);return svg;}
document.querySelectorAll('[data-icon]').forEach(el=>{const svg=icon(el.dataset.icon);if(el.classList.length){el.removeAttribute('data-icon');el.append(svg);}else el.replaceWith(svg);});
function node(tag,className,text){const el=document.createElement(tag);if(className)el.className=className;if(text!==undefined)el.textContent=text;return el;}
function button(label,action,className='icon-button',iconName){const el=node('button',className);el.type='button';el.setAttribute('aria-label',label);el.title=label;if(iconName)el.append(icon(iconName));if(!className.includes('icon-button'))el.append(document.createTextNode(label));el.onclick=action;return el;}
function empty(container,title,description,iconName='document',compact=false,link){container.replaceChildren();const wrap=node('div','empty-state'+(compact?' compact':''));const mark=node('div','empty-icon');mark.append(icon(iconName));wrap.append(mark,node('strong','',title));if(description)wrap.append(node('p','',description));if(link){const a=node('a','button secondary small',link.label);a.href=link.href;wrap.append(a);}container.append(wrap);}
function loading(container,title){empty(container,title,'잠시만 기다려 주세요.','reset');container.firstElementChild.classList.add('loading');}
function message(id,text,type='success'){const el=$(id);el.hidden=!text;el.textContent=text||'';el.className='message '+type;}
let toastTimer;function toast(text){clearTimeout(toastTimer);$('toast').textContent=text;$('toast').hidden=false;toastTimer=setTimeout(()=>$('toast').hidden=true,4500);}
