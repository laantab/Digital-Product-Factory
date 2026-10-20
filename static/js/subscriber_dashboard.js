'use strict';
(() => {
  const el=id=>document.getElementById(id);
  let project=null,timer=null,stopped=false;
  const message=s=>{el('notice').textContent=s||'';};
  async function api(path,data){
    const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),30000);
    try{
      const r=await fetch(path,{method:data===undefined?'GET':'POST',headers:data===undefined?{}:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data),signal:controller.signal});
      const b=await r.json();if(!r.ok||b.ok===false)throw new Error(b.error||b.message||'This step could not finish. Your progress is saved.');return b;
    }finally{clearTimeout(timeout);}
  }
  function safeLink(href,label){
    let u;try{u=new URL(href,location.origin);}catch{return null;}
    if(u.origin!==location.origin||!u.pathname.startsWith('/'))return null;
    const a=document.createElement('a');a.href=u.href;a.textContent=label;a.className='link';return a;
  }
  async function credits(){const b=await api('/account/subscription');el('creditBalance').textContent=`${b.credits.available} product credit${b.credits.available===1?'':'s'} available`;el('createBook').disabled=b.credits.available<1||b.credits.payment_hold;if(el('topupPanel'))el('topupPanel').hidden=!b.topup;if(b.topup&&['credited','refunded'].includes(b.topup.last_state))sessionStorage.removeItem('factoryTopupRequest');}
  function show(b){
    project=b.project_id;sessionStorage.setItem('factorySubscriberProject',String(project));
    el('buildPanel').hidden=false;el('buildTitle').textContent=b.title||'Building your ebook';
    el('progress').value=b.percent||0;el('buildMessage').textContent=b.message||'';
    el('resume').hidden=b.finished||!(b.failed||b.retrying||b.activity?.state==='stalled'||b.accounting_pending);
    el('choices').replaceChildren();el('downloads').replaceChildren();
    if(b.finished){for(const [kind,label] of [['pdf','Download PDF'],['zip','Download ZIP']]){const href=b.downloads?.[kind]||b.saved_downloads?.[kind];if(href){const a=safeLink(href,label);if(a)el('downloads').append(a);}}}
    if(b.awaiting_cover_choice){renderChoice(b.cover_choice);return true;}
    return b.finished||b.failed||b.retrying||b.activity?.state==='stalled';
  }
  function renderChoice(choice){
    if(!choice){message('Your cover choice is saved. Open the book to review the available choices.');return;}
    const titleLabel=document.createElement('label');titleLabel.textContent='Choose your title';
    const select=document.createElement('select');select.id='titleChoice';
    for(const t of choice.title_options||[]){const o=document.createElement('option');o.value=t.id;o.textContent=t.title+(t.subtitle?' — '+t.subtitle:'');o.selected=t.id===choice.selected_title_id;select.append(o);}
    const change=document.createElement('button');change.type='button';change.textContent='Update title and covers';
    change.onclick=()=>choose({action:'title',title_id:select.value});
    el('choices').append(titleLabel,select,change);
    for(const v of choice.variants||[]){
      const card=document.createElement('div');card.className='choice';
      const link=safeLink(v.thumb_url,v.label||'Cover');
      if(!link)continue;
      const image=document.createElement('img');image.src=link.href;image.alt=v.label||'Book cover preview';
      const button=document.createElement('button');button.type='button';button.textContent='Use this cover and finish';
      button.onclick=()=>choose({action:'finish',title_id:choice.selected_title_id,layout_id:v.layout_id,digest:v.digest});
      card.append(image,button);el('choices').append(card);
    }
  }
  async function choose(body){
    el('choices').querySelectorAll('button').forEach(b=>b.disabled=true);
    try{const b=await api(`/ebook/build/${project}/cover-choice`,body);show(b);await poll();}
    catch(e){message(e.message);el('choices').querySelectorAll('button').forEach(b=>b.disabled=false);}

  }
  async function poll(){
    clearTimeout(timer);if(!project||stopped)return;
    try{let b=await api(`/ebook/build/${project}/status`);if(!b.finished&&!b.failed&&!b.awaiting_cover_choice&&!b.retrying){b=await api(`/ebook/build/${project}/advance`,{});}const pause=show(b);if(b.finished){await credits();await saved();}if(pause)return;}
    catch(e){message(e.name==='AbortError'?'Connection timed out. Your book is saved; use Continue to reconnect.':e.message);el('resume').hidden=false;return;}
    timer=setTimeout(poll,2500);
  }
  async function saved(){
    const b=await api('/projects');const rows=Array.isArray(b)?b:(b.projects||b.items||[]);el('savedBooks').replaceChildren();
    for(const p of rows){if(p.type&&p.type!=='ebook')continue;const row=document.createElement('div');row.className='book';const label=document.createElement('p');label.textContent=p.name||p.title||'Saved ebook';const open=document.createElement('button');open.type='button';open.textContent='Open book';open.onclick=async()=>{project=p.id;stopped=false;await poll();};row.append(label,open);el('savedBooks').append(row);}
  }
  el('ebookForm').onsubmit=async e=>{e.preventDefault();el('createBook').disabled=true;message('');try{const b=await api('/ebook/build',{fields:{topic:el('topic').value.trim(),author_brand:el('author').value.trim(),ebook_creation_mode:el('mode').value,guided_cover_choice:true,theme_id:el('theme').value,include_images:'Yes'}});project=b.project_id;stopped=false;show(b);await poll();}catch(e){message(e.message);}finally{await credits().catch(()=>{});}};
  el('resume').onclick=async()=>{if(!project)return;el('resume').disabled=true;try{await api(`/ebook/build/${project}/resume`,{});stopped=false;await poll();}catch(e){message(e.message);}finally{el('resume').disabled=false;}};
  el('signout').onclick=async()=>{stopped=true;clearTimeout(timer);await api('/auth/logout',{});sessionStorage.removeItem('factorySubscriberProject');location.assign('/plans');};
  el('manage').onclick=async()=>{try{const b=await api('/account/portal',{});location.assign(b.url);}catch(e){message(e.message);}};
  if(el('buyCredits'))el('buyCredits').onclick=async()=>{el('buyCredits').disabled=true;try{let key=sessionStorage.getItem('factoryTopupRequest');if(!key){key=crypto.randomUUID();sessionStorage.setItem('factoryTopupRequest',key);}const b=await api('/account/topup',{request_key:key});location.assign(b.checkout_url);}catch(e){message(e.message);el('buyCredits').disabled=false;}};
  if(el('subscribe'))el('subscribe').onclick=async()=>{el('subscribe').disabled=true;try{const b=await api('/account/checkout',{plan_id:el('subscribe').dataset.plan,billing_period:'monthly',provider:el('provider').value});location.assign(b.checkout_url);}catch(e){message(e.message);el('subscribe').disabled=false;}};
  el('mode').onchange=()=>{const custom=el('mode').value==='custom';el('theme').disabled=!custom;el('theme').hidden=!custom;el('themeLabel').hidden=!custom;};
  async function init(){
    try{await credits();await saved();const id=sessionStorage.getItem('factorySubscriberProject');if(/^[1-9][0-9]*$/.test(id||'')){project=Number(id);await poll();}}catch(e){message(e.message);}
  }
  init();
})();
