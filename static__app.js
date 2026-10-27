const tg=window.Telegram?.WebApp;tg?.ready();tg?.expand();
const $=x=>document.getElementById(x);const state={matches:[],selected:new Map(),view:'matches',user:null,league:'Все',details:null};
let pendingBetKey=null;
let avatarVersion=Date.now();
function avatarImage(id,cls='avatar-picture'){
 const src=`/api/avatars/${encodeURIComponent(id)}?v=${avatarVersion}`;
 return `<img class="${cls}" src="${src}" alt="Аватар игрока" onerror="this.hidden=true">`;
}
function telegramAvatar(){const url=tg?.initDataUnsafe?.user?.photo_url||'';try{const parsed=new URL(url);return parsed.protocol==='https:'?url:''}catch{return ''}}
function applyMyAvatar(){
 if(!state.user)return;
 const url=telegramAvatar(), saved=localStorage.getItem(`rdg_avatar_${state.user.id}`)||'custom';
 document.querySelectorAll('[data-own-avatar]').forEach(el=>{
   const id=state.user.id;
   const img=el.querySelector('img');
   if(!img)return;
   const target=saved==='telegram'?url:saved==='initials'?'':`/api/avatars/${id}?v=${avatarVersion}`;
   img.hidden=!target;
   if(target)img.src=target;
   img.onerror=()=>{if(saved==='custom'&&url&&img.src!==url){img.onerror=()=>{img.hidden=true};img.src=url}else{img.hidden=true}};
 });
}


function toggleProfileMenu(force){
 const menu=$('profileMenu'), btn=$('profileMenuButton');
 const next=typeof force==='boolean'?force:menu.classList.contains('hidden');
 menu.classList.toggle('hidden',!next);
 btn.setAttribute('aria-expanded',String(next));
}
const dev=new URLSearchParams(location.search).get('dev');
const markets={H:'П1',D:'X',A:'П2',O15:'ТБ 1.5',U15:'ТМ 1.5',O25:'ТБ 2.5',U25:'ТМ 2.5',O35:'ТБ 3.5',U35:'ТМ 3.5',GG:'ОЗ: да',NG:'ОЗ: нет',F1M1:'Ф1 (-1)',F1P1:'Ф1 (+1)',F2M1:'Ф2 (-1)',F2P1:'Ф2 (+1)',IH15O:'ИТБ1 1.5',IH15U:'ИТМ1 1.5',IA15O:'ИТБ2 1.5',IA15U:'ИТМ2 1.5'};
const championBadge=n=>Number(n)>0?` <span class="champion-badge" title="Победитель сезона · ${Number(n)} титул(ов)" aria-label="Победитель сезона">✦</span>`:'';
const escapeHTML=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,method='GET',body){let h={'Content-Type':'application/json'};if(tg?.initData)h['X-Telegram-Init-Data']=tg.initData;if(dev)h['X-Dev-User']=dev;const r=await fetch('/api/'+path,{method,headers:h,body:body?JSON.stringify(body):undefined});let d=await r.json().catch(()=>({}));if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:'Ошибка запроса');return d}
function notice(s){$('note').textContent=s;setTimeout(()=>{if($('note').textContent===s)$('note').textContent=''},6500)}
async function refreshUser(){try{state.user=await api('me');const balanceValue=state.user.balance.toLocaleString('ru-RU')+' монет';$('balance').innerHTML=`<div class="balance-shell"><span class="balance-label">Баланс</span><strong class="balance-value"><span class="balance-coin">🪙</span>${balanceValue}</strong></div>`;const initials=((state.user.name||'RD').trim().slice(0,2)||'RD').toUpperCase();$('profileMenuInitials').textContent=initials;$('adminMenuTab').hidden=!state.user.is_admin;applyMyAvatar();}catch(e){state.user=null;$('adminMenuTab').hidden=true;$('balance').innerHTML=`<div class="balance-shell"><span class="balance-label">Баланс</span><strong class="balance-value balance-muted">Не авторизован</strong></div>`;$('profileMenuInitials').textContent='RD';notice(!tg?.initData?'Открой RDG кнопкой «Играть» внутри Telegram. Данные входа не получены.':e.message)}}
function fmtDate(s){return new Date(s).toLocaleString('ru-RU',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'})}
const additionalOdds={O15:1.40,U15:2.75,O25:1.92,U25:1.92,O35:2.45,U35:1.53,GG:1.88,NG:1.88,F1M1:2.65,F1P1:1.54,F2M1:2.65,F2P1:1.54,IH15O:2.20,IH15U:1.64,IA15O:2.20,IA15U:1.64};
function liveOdds(m){return Object.entries(markets).map(([id,label])=>[id,label,id==='H'?m.odd_h:id==='D'?m.odd_d:id==='A'?m.odd_a:additionalOdds[id]])}
function crest(url){try{const u=new URL(url);if(u.protocol!=='https:')return '' ;return `<img class="team-crest" src="${escapeHTML(u.href)}" alt="" loading="lazy" onerror="this.style.display='none'">`}catch{return ''}}
function teamPair(m){return `<div class="teams with-crests"><span class="team-name">${crest(m.home_crest)}${escapeHTML(m.home)}</span><em>VS</em><span class="team-name">${crest(m.away_crest)}${escapeHTML(m.away)}</span></div>`}
function openCoupon(){if(!state.selected.size)return;$('couponOverlay').hidden=false;document.body.classList.add('sheet-open');updateBar()}
function closeCoupon(){ $('couponOverlay').hidden=true;document.body.classList.remove('sheet-open') }
function updateBar(){
 const picks=[...state.selected.values()], count=picks.length;
 const odds=picks.reduce((v,p)=>v*p.odd,1),stake=Number($('stake').value)||0;
 $('couponFloat').hidden=!count||state.view!=='matches';
 $('floatCount').textContent=count===1?'1 событие':`${count} события`;
 $('floatOdds').textContent=odds.toFixed(2);
 $('couponHeading').textContent=count===1?'Одиночный прогноз':`Экспресс · ${count} матчей`;
 $('selectionCount').textContent=`Выбрано: ${count}`;
 $('totalOdd').textContent=odds.toFixed(2);
 $('potential').textContent='Возможная выплата: '+Math.round(stake*odds).toLocaleString('ru-RU')+' монет';
 $('couponLines').innerHTML=picks.map(p=>{const m=state.matches.find(x=>x.id===p.match_id);return `<div class="coupon-line"><span><b>${escapeHTML(m?.home||'Матч')} — ${escapeHTML(m?.away||'')}</b><small>${escapeHTML(markets[p.pick])} · ×${p.odd.toFixed(2)}</small></span><button data-remove="${p.match_id}" aria-label="Убрать исход">×</button></div>`}).join('');
 document.querySelectorAll('[data-remove]').forEach(b=>b.onclick=()=>{state.selected.delete(Number(b.dataset.remove));pendingBetKey=null;if(!state.selected.size)closeCoupon();updateBar();render()});
}
function choosePick(id,pick){pendingBetKey=null;let m=state.matches.find(x=>x.id===id);if(!m)return;let o=liveOdds(m).find(x=>x[0]===pick);if(!o)return;if(state.selected.get(id)?.pick===pick)state.selected.delete(id);else if(state.selected.size<8)state.selected.set(id,{match_id:id,pick,odd:Number(o[2])});else return notice('Максимум 8 исходов');updateBar();render()}
const expandedMatches=new Set();
let scheduleRange='week',teamSearch='';
const activeMatchMarkets=new Map();
const marketGroups=[['Исход матча',['H','D','A']],['Тоталы',['O15','U15','O25','U25','O35','U35']],['Обе забьют',['GG','NG']],['Форы',['F1M1','F1P1','F2M1','F2P1']],['Индивидуальные тоталы',['IH15O','IH15U','IA15O','IA15U']]];
function marketButtons(m,group='result'){const ids=group==='result'?marketGroups[0][1]:marketGroups.find(g=>g[0]===group)?.[1]||[];return `<div class="odds ${ids.length%3===0?'':'odds-pairs'}">${liveOdds(m).filter(x=>ids.includes(x[0])).map(([pick,label,odd])=>`<button class="${state.selected.get(m.id)?.pick===pick?'chosen':''}" data-id="${m.id}" data-pick="${pick}"><small>${label}</small>${Number(odd).toFixed(2)}</button>`).join('')}</div>`}
function connectMarketButtons(){document.querySelectorAll('[data-pick]').forEach(b=>b.onclick=()=>choosePick(Number(b.dataset.id),b.dataset.pick))}
function filterControls(){const leagues=['Все',...new Set(state.matches.filter(m=>['SCHEDULED','TIMED'].includes(m.status)).map(m=>m.league))];$('filters').hidden=false;$('filters').innerHTML=leagues.map(l=>`<button data-league="${escapeHTML(l)}" class="${state.league===l?'active':''}">${escapeHTML(l)}</button>`).join('');document.querySelectorAll('[data-league]').forEach(b=>b.onclick=()=>{state.league=b.dataset.league;matchesView()})}
function matchMarketChooser(m){
 const active=activeMatchMarkets.get(m.id)||'result';
 const groups=[['result','Исход'],['Тоталы','Тоталы'],['Обе забьют','ОЗ'],['Форы','Форы'],['Индивидуальные тоталы','ИТБ/ИТМ']];
 return `<div class="match-market-tabs" role="group" aria-label="Рынки матча">${groups.map(([key,label])=>`<button type="button" data-market-match="${m.id}" data-market-name="${escapeHTML(key)}" class="${active===key?'active':''}">${label}</button>`).join('')}</div><div class="match-market-body">${marketButtons(m,active)}</div>`;
}
function connectMatchCardControls(){
 connectMarketButtons();
 document.querySelectorAll('[data-expand-match]').forEach(b=>b.onclick=()=>{
  const id=Number(b.dataset.expandMatch);
  if(expandedMatches.has(id))expandedMatches.delete(id);else expandedMatches.add(id);
  matchesView();
 });
 document.querySelectorAll('[data-market-match]').forEach(b=>b.onclick=()=>{
  const id=Number(b.dataset.marketMatch);
  activeMatchMarkets.set(id,b.dataset.marketName);
  matchesView();
 });
 document.querySelectorAll('[data-details]').forEach(b=>b.onclick=()=>{state.details=Number(b.dataset.details);state.view='details';render()});
}
function matchesView(){
 filterControls();
 const start=new Date();start.setHours(0,0,0,0);
 const end=new Date(start);end.setDate(end.getDate()+(scheduleRange==='today'?1:scheduleRange==='tomorrow'?2:8));
 const from=scheduleRange==='tomorrow'?new Date(start.getTime()+86400000):start;
 const upcoming=state.matches.filter(m=>['SCHEDULED','TIMED'].includes(m.status)&&new Date(m.kickoff)>new Date(Date.now()+60000)&&(state.league==='Все'||m.league===state.league)&&new Date(m.kickoff)>=from&&new Date(m.kickoff)<end&&(`${m.home} ${m.away}`.toLocaleLowerCase('ru').includes(teamSearch.toLocaleLowerCase('ru')))).sort((a,b)=>new Date(a.kickoff)-new Date(b.kickoff));
 const groups=upcoming.reduce((a,m)=>((a[m.league]??=[]).push(m),a),{});
 const scheduleToolbar=`<div class="schedule-toolbar"><div class="schedule-days">${[['today','Сегодня'],['tomorrow','Завтра'],['week','7 дней']].map(([key,label])=>`<button type="button" data-schedule="${key}" class="${scheduleRange===key?'active':''}">${label}</button>`).join('')}</div><input id="teamSearch" aria-label="Поиск команды" placeholder="Поиск команды" value="${escapeHTML(teamSearch)}" autocomplete="off"></div>`;
  $('content').innerHTML=Object.keys(groups).length?Object.entries(groups).map(([league,ms])=>`<div class="league">${escapeHTML(league)}</div>`+ms.map(m=>{
  const expanded=expandedMatches.has(m.id);
  return `<article class="match match-premium"><div class="matchtop"><span>${fmtDate(m.kickoff)}</span><span class="match-status">До начала</span></div>${teamPair(m)}<div class="market-label">Исход матча</div>${marketButtons(m)}<div class="match-actions"><button type="button" class="more-markets" data-expand-match="${m.id}" aria-expanded="${expanded}">${expanded?'Свернуть рынки':'Все рынки'} <span>${expanded?'−':'+'}</span></button><button type="button" class="details-link" data-details="${m.id}">О матче</button></div>${expanded?`<div class="expanded-markets"><div class="expanded-title">Другие варианты прогноза</div>${matchMarketChooser(m)}</div>`:''}</article>`;
 }).join('')).join(''):'<p class="loading">Нет матчей по выбранным фильтрам.</p>';
 $('content').insertAdjacentHTML('afterbegin',scheduleToolbar);
 document.querySelectorAll('[data-schedule]').forEach(b=>b.onclick=()=>{scheduleRange=b.dataset.schedule;matchesView()});
 $('teamSearch').oninput=e=>{const value=e.target.value;teamSearch=value;matchesView();const input=$('teamSearch');input.focus();input.setSelectionRange(value.length,value.length)};
 connectMatchCardControls();
}
function detailsView(){let m=state.matches.find(x=>x.id===state.details);if(!m){state.view='matches';return matchesView()}$('content').innerHTML=`<button class="back-button" id="back">← Все матчи</button><article class="match detail"><div class="eyebrow">${escapeHTML(m.league)}</div>${teamPair(m)}<p class="meta">Начало: ${fmtDate(m.kickoff)} · Статус: ${escapeHTML(m.status)}</p>${marketGroups.map(([title])=>`<section class="market-section"><h3>${title}</h3>${marketButtons(m,title==='Исход матча'?'result':title)}</section>`).join('')}<p class="meta">Коэффициенты игровые, не букмекерские. Форы (+1/-1): при точном равенстве с учётом форы исход возвращается с коэффициентом 1.0.</p></article>`;$('back').onclick=()=>{state.view='matches';render()};connectMarketButtons()}
// LIVE data always comes from the server. No fake timer or invented goal events.
function renderLiveMatch(m){
 const source=state.matches.find(x=>x.id===m.id);
 const homeLogo=source?.home_crest||m.home_crest;
 const awayLogo=source?.away_crest||m.away_crest;
 const elapsed=Number(m.estimated_minute);
 const minute=Number.isFinite(elapsed)&&elapsed>=0?`≈ ${Math.floor(elapsed)}′`:'В игре';
 const scoreHome=m.home_score??'–',scoreAway=m.away_score??'–';
 const events=Array.isArray(m.events)?m.events:[];
 const eventRows=events.length?events.map(e=>{
   const kind=e.kind==='score_changed'?'Изменение счёта':e.kind==='live_started'?'Начало матча':e.kind==='finished'?'Матч завершён':'Событие';
   return `<div class="live-event"><time>${fmtDate(e.occurred_at)}</time><span>${kind}</span><b>${e.home_score??'–'} : ${e.away_score??'–'}</b></div>`;
 }).join(''):'<p class="meta live-no-events">Обновлений счёта пока нет</p>';
 return `<article class="match live-match-card">
   <div class="live-match-top"><span class="live-league">${escapeHTML(m.league)}</span><span class="live-indicator ${m.fresh?'is-fresh':'is-stale'}">${m.fresh?'LIVE · данные актуальны':'Данные задерживаются'}</span></div>
   <div class="live-match-middle"><div class="live-team">${crest(homeLogo)}<span>${escapeHTML(m.home)}</span></div><div class="live-result"><div class="live-numbers">${scoreHome}<span>:</span>${scoreAway}</div><span class="live-minute">${minute}</span></div><div class="live-team">${crest(awayLogo)}<span>${escapeHTML(m.away)}</span></div></div>
   <div class="live-match-footer"><span>Обновлено ${fmtDate(m.updated_at)}</span><span>${m.fresh?'Счёт из футбольного API':'Проверь актуальность данных'}</span></div>
   <details class="live-events"><summary>История обновлений (${events.length})</summary><div class="live-event-list">${eventRows}</div></details>
 </article>`;
}
let liveRequestInFlight=false;
async function liveView(){
 if(liveRequestInFlight)return;
 liveRequestInFlight=true;
 try{
  const data=await api('live');
  if(state.view!=='live')return;
  const matches=Array.isArray(data.matches)?data.matches:[];
  const count=matches.length;
  $('content').innerHTML=`<section class="live-dashboard"><div class="live-dashboard-heading"><div><span class="eyebrow">МАТЧИ В РЕАЛЬНОМ ВРЕМЕНИ</span><h3>Live-центр</h3></div><span class="live-count">${count} ${count===1?'матч':'матчей'}</span></div><p>Данные обновляются автоматически каждые 20 секунд на экране. Источник может передавать счёт с задержкой; минута приблизительная.</p></section>`+
   (count?matches.map(renderLiveMatch).join(''):'<div class="live-empty"><div class="live-empty-symbol">LIVE</div><h3>Сейчас нет матчей в прямом эфире</h3><p>Когда футбольный API передаст текущие матчи, они появятся здесь автоматически.</p></div>');
 }finally{liveRequestInFlight=false;}
}

function couponView(){let picks=[...state.selected.values()];$('content').innerHTML=`<article class="ticket"><h3>Мой купон · ${picks.length} из 8</h3>${picks.length?picks.map(p=>{const m=state.matches.find(x=>x.id===p.match_id);return `<div class="coupon-line"><span>${escapeHTML(m?.home||'Матч')} — ${escapeHTML(m?.away||'')}<br><small>${escapeHTML(markets[p.pick])} · ${p.odd.toFixed(2)}</small></span><button data-remove="${p.match_id}" aria-label="Убрать исход">×</button></div>`}).join(''):'<p class="meta">Нажми на коэффициент в разделе «Матчи».</p>'}<p class="possible">Общий коэффициент: ${picks.reduce((v,p)=>v*p.odd,1).toFixed(2)}</p><label class="stake-label">Ставка в монетах <input id="couponStake" type="number" min="10" max="100000" value="${Number($('stake').value)||100}"></label><p id="couponPotential" class="possible"></p><button class="primary" id="couponPlace" ${picks.length?'':'disabled'}>Сделать ставку</button></article>`;document.querySelectorAll('[data-remove]').forEach(b=>b.onclick=()=>{state.selected.delete(Number(b.dataset.remove));updateBar();couponView()});$('couponStake').oninput=()=>{pendingBetKey=null; $('stake').value=$('couponStake').value; couponEstimate() };couponEstimate();$('couponPlace').onclick=()=>{$('stake').value=$('couponStake').value;placeBet()}}
function couponEstimate(){let odds=[...state.selected.values()].reduce((v,p)=>v*p.odd,1);$('couponPotential').textContent='Возможная выплата: '+Math.round((Number($('couponStake').value)||0)*odds).toLocaleString('ru')+' монет'}
// v2.5: Keep filters in the history view only. A new slip always starts in "All".
let slipStatusFilter='all';
const slipStatusLabels={pending:'Ожидается',won:'Выиграно',lost:'Проиграно',void:'Возврат',cashed_out:'Кэшаут'};
const slipLegLabels={pending:'Ожидается',won:'Выиграл',lost:'Проиграл',void:'Возврат',cashed_out:'Кэшаут'};
const slipCoins=n=>Math.round(Number(n)||0).toLocaleString('ru-RU');
function slipCard(s){
 const status=String(s.status||'pending');
 const type=s.legs.length===1?'Одиночный прогноз':`Экспресс · ${s.legs.length} события`;
 const odds=Number(s.combined_odd)||1;
 const payout=Number(s.payout)||0;
 const possible=Math.round(Number(s.stake)*odds);
 const settled=status!=='pending';
 const figure=settled?payout:possible;
 const legs=s.legs.map((l,i)=>`<div class="history-leg"><span class="history-leg-index">${i+1}</span><div class="history-leg-main"><b>${escapeHTML(l.home)} — ${escapeHTML(l.away)}</b><small>${escapeHTML(markets[l.pick]||l.pick)} · ×${Number(l.locked_odd).toFixed(2)}</small></div><span class="history-leg-state" data-state="${escapeHTML(l.status||'pending')}">${escapeHTML(slipLegLabels[l.status]||l.status||'Ожидается')}</span></div>`).join('');
 return `<article class="ticket history-card"><div class="history-card-head"><div><span class="history-type">${type}</span><small class="history-id">Купон №${s.id}</small></div><span class="history-status" data-state="${escapeHTML(status)}">${escapeHTML(slipStatusLabels[status]||status)}</span></div><div class="history-finances"><div><small>Ставка</small><b>${slipCoins(s.stake)} монет</b></div><div><small>Коэффициент</small><b>×${odds.toFixed(2)}</b></div><div><small>${settled?'Выплачено':'Возможная выплата'}</small><strong>${slipCoins(figure)} монет</strong></div></div><details class="history-details"><summary>События и исходы <span>${s.legs.length}</span></summary><div class="history-leg-list">${legs}</div></details>${status==='pending'&&s.legs.length===1?`<div id="cashout-${s.id}" class="cashout"><button data-quote="${s.id}">Проверить кэшаут</button><small>Только при свежем счёте во время матча. Предложение может измениться.</small></div>`:status==='pending'&&s.legs.length>1?'<p class="history-hint">Кэшаут для экспрессов недоступен.</p>':''}</article>`;
}
async function slipsView(){
 const a=await api('slips');
 const filters=[['all','Все'],['pending','Ожидаются'],['won','Выиграно'],['lost','Проиграно'],['other','Возвраты']];
 const list=a.filter(s=>slipStatusFilter==='all'||(slipStatusFilter==='other'?['void','cashed_out'].includes(s.status):s.status===slipStatusFilter));
 const summary=`<div class="history-overview"><div><span>Всего прогнозов</span><b>${a.length}</b></div><div><span>Ожидают</span><b>${a.filter(s=>s.status==='pending').length}</b></div><div><span>Выиграно</span><b>${a.filter(s=>s.status==='won').length}</b></div></div>`;
 const tabs=`<div class="history-tabs" aria-label="Фильтр истории">${filters.map(([key,label])=>`<button type="button" data-history-filter="${key}" class="${slipStatusFilter===key?'active':''}" aria-pressed="${slipStatusFilter===key}">${label}</button>`).join('')}</div>`;
 $('content').innerHTML=`${summary}${tabs}<div class="history-list">${list.length?list.map(slipCard).join(''):`<div class="history-empty"><h3>${a.length?'Нет прогнозов с таким статусом':'История пока пуста'}</h3><p>${a.length?'Попробуй другой фильтр.':'Открой раздел «Матчи», выбери коэффициент и подтверди прогноз.'}</p>${a.length?'':'<button id="historyGoMatches" type="button">К матчам</button>'}</div>`}</div>`;
 document.querySelectorAll('[data-history-filter]').forEach(b=>b.onclick=()=>{slipStatusFilter=b.dataset.historyFilter;slipsView()});
 document.querySelectorAll('[data-quote]').forEach(b=>b.onclick=()=>showCashout(Number(b.dataset.quote)));
 const go=$('historyGoMatches');if(go)go.onclick=()=>{state.view='matches';render()};
}
async function showCashout(id){const node=$(`cashout-${id}`);if(!node)return;try{const q=await api(`slips/${id}/cashout`);node.innerHTML=`<p>Текущий счёт: ${escapeHTML(q.score)} · ${q.elapsed}-я минута</p><h3>Забрать сейчас: ${q.amount} 🪙</h3><small>Предложение действует недолго и перепроверяется при принятии.</small><button data-close-cashout="${id}" ${q.amount<1?'disabled':''}>Забрать ${q.amount} монет</button>`;node.querySelector('[data-close-cashout]').onclick=async()=>{if(!confirm(`Закрыть одиночную ставку за ${q.amount} монет? Отменить действие нельзя.`))return;try{const result=await api(`slips/${id}/cashout`,'POST',{expected_amount:q.amount});notice(`Кэшаут +${result.amount} 🪙`);await refreshUser();await slipsView()}catch(e){notice(e.message);await showCashout(id)}}}catch(e){node.innerHTML=`<p class="meta">${escapeHTML(e.message)}</p><button data-quote="${id}">Обновить предложение</button>`;node.querySelector('button').onclick=()=>showCashout(id)}}
// Balance chart uses the same authenticated ledger aggregate as the table.
// Rebuild daily closing balances backwards from the current wallet balance.
function balanceChart(history){
 const chronological=[...history.daily].reverse();
 const netInWindow=chronological.reduce((sum,day)=>sum+Number(day.net),0);
 let balance=Number(history.lifetime.current_balance)-netInWindow;
 const points=[{date:'До периода',value:balance},...chronological.map(day=>({date:day.date,value:(balance+=Number(day.net))}))];
 const values=points.map(p=>p.value),minimum=Math.min(...values),maximum=Math.max(...values);
 const padding=Math.max(10,(maximum-minimum)*0.12),lo=minimum-padding,hi=maximum+padding;
 const w=680,h=232,left=58,right=15,top=20,bottom=37;
 const x=i=>left+(w-left-right)*i/(points.length-1);
 const y=value=>top+(h-top-bottom)*(hi-value)/(hi-lo);
 const coords=points.map((p,i)=>[x(i),y(p.value)]);
 const path=coords.map(([cx,cy],i)=>`${i?'L':'M'}${cx.toFixed(1)},${cy.toFixed(1)}`).join(' ');
 const floor=h-bottom;
 const fill=`${path} L${x(points.length-1).toFixed(1)},${floor} L${x(0)},${floor} Z`;
 const format=n=>Math.round(n).toLocaleString('ru-RU');
 const marks=[0,1,2,3].map(i=>{const v=lo+(hi-lo)*i;return `<line x1="${left}" x2="${w-right}" y1="${y(v)}" y2="${y(v)}" stroke="#34484b" stroke-dasharray="4 6"/><text x="${left-8}" y="${y(v)+4}" text-anchor="end" fill="#a6b8b9" font-size="12">${format(v)}</text>`}).join('');
 const labels=[0,Math.floor((points.length-1)/2),points.length-1].map(i=>`<text x="${x(i)}" y="${h-10}" text-anchor="middle" fill="#a6b8b9" font-size="12">${i===0?'Начало':points[i].date.slice(5).split('-').reverse().join('.')}</text>`).join('');
 const last=coords.at(-1),diff=points.at(-1).value-points[0].value;
 $('balanceChart').innerHTML=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Баланс по дням за ${history.days} дней, от ${format(points[0].value)} до ${format(points.at(-1).value)} виртуальных монет" xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="balanceAreaFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#b5fe63" stop-opacity=".3"/><stop offset="100%" stop-color="#b5fe63" stop-opacity="0"/></linearGradient></defs>${marks}<path d="${fill}" fill="url(#balanceAreaFill)"/><path d="${path}" fill="none" stroke="#b5fe63" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><circle cx="${last[0]}" cy="${last[1]}" r="5" fill="#b5fe63" stroke="#11231a" stroke-width="2"/>${labels}</svg>`;
 $('balanceChartSummary').innerHTML=`<span>Начало: <b>${format(points[0].value)} 🪙</b></span><span>Сейчас: <b>${format(points.at(-1).value)} 🪙</b></span><strong class="${diff>=0?'win':'lose'}">${diff>0?'+':''}${format(diff)} 🪙</strong>`;
}
let profileActiveTab='stats';
function selectProfileTab(tab){profileActiveTab=tab;document.querySelectorAll('[data-profile-tab]').forEach(btn=>{const active=btn.dataset.profileTab===tab;btn.classList.toggle('active',active);btn.setAttribute('aria-selected',String(active));});document.querySelectorAll('[data-profile-panel]').forEach(panel=>{panel.hidden=panel.dataset.profilePanel!==tab;});}
async function profileView(){
 const [p,progress,awards,history]=await Promise.all([api('profile'),api('progression'),api('seasons/current'),api('profile/balance-history?days=30')]),u=p.user,t=p.stats;
 const initials=(u.name||'Игрок').trim().slice(0,2).toUpperCase();
 $('content').innerHTML=`<section class="profile-card"><div class="profile-head"><div class="profile-avatar" data-own-avatar><img hidden alt="Мой аватар">${escapeHTML(initials)}</div><div><div class="eyebrow">МОЙ АККАУНТ</div><h2>${escapeHTML(u.name)}${championBadge(awards.me?.champion_titles)}</h2><small>Telegram ID: ${u.id}</small></div></div><div class="avatar-actions"><label class="avatar-upload">Загрузить фото<input id="avatarUpload" type="file" accept="image/jpeg,image/png,image/webp" hidden></label><button id="avatarTelegram">Фото Telegram</button><button id="avatarInitials">Инициалы</button></div><p class="avatar-hint">Фото Telegram используется, если оно доступно Mini App. Свой снимок сохраняется в профиле RDG.</p><div class="profile-wallet"><span class="wallet-label">Баланс</span><strong class="wallet-value"><span class="wallet-coin">🪙</span> ${u.balance.toLocaleString('ru-RU')}</strong><small class="wallet-note">Премиальный игровой счёт RDG</small></div></section>
 <div class="profile-tabs" role="tablist" aria-label="Разделы профиля"><button type="button" data-profile-tab="stats" role="tab">Статистика</button><button type="button" data-profile-tab="achievements" role="tab">Достижения</button><button type="button" data-profile-tab="balance" role="tab">История баланса</button></div>
 <div class="profile-tab-panel" data-profile-panel="stats" role="tabpanel"><article class="ticket progression-panel"><div class="progression-level"><div><small>УРОВЕНЬ ИГРОКА</small><h3>Уровень ${progress.level}</h3></div><strong>${progress.xp} XP</strong></div><div class="xp-track"><div style="width:${Math.min(100,100*progress.progress_xp/progress.needed_xp)}%"></div></div><p class="meta">${progress.progress_xp} / ${progress.needed_xp} XP до следующего уровня · опыт нельзя обменять на монеты</p></article></div><div class="profile-tab-panel" data-profile-panel="achievements" role="tabpanel"><article class="ticket"><h3>Ежедневные задания</h3><p class="meta">Обновляются в 00:00 UTC</p>${progress.quests.map(q=>`<div class="quest-row"><div><b>${escapeHTML(q.title)}</b><small>+${q.xp} XP</small></div>${q.claimed?'<span class="quest-done">Получено ✓</span>':`<button data-quest="${q.id}" ${q.completed?'':'disabled'}>${q.completed?'Забрать':'Не выполнено'}</button>`}</div>`).join('')}</article><article class="ticket"><h3>Достижения</h3><div class="achievement-list">${progress.achievements.map(a=>`<div class="achievement ${a.unlocked?'unlocked':''}"><span>${a.unlocked?'🏅':'🔒'}</span><div><b>${escapeHTML(a.title)}</b><small>${a.current} / ${a.target}</small></div></div>`).join('')}</div></article></div><div class="profile-tab-panel" data-profile-panel="stats"><div class="profile-stats">${[['Всего ставок',t.total],['Выиграно',t.won],['Проиграно',t.lost],['Успех',t.win_rate+'%'],['В ожидании',t.pending],['Кэшаутов',t.cashed_out]].map(([label,value])=>`<div class="profile-metric"><span>${label}</span><b>${value}</b></div>`).join('')}</div>
 <article class="ticket"><h3>Статистика монет</h3><div class="profile-sums"><span>Всего поставлено</span><b>${t.total_staked.toLocaleString('ru-RU')} 🪙</b><span>Начислено по ставкам</span><b>${t.total_paid.toLocaleString('ru-RU')} 🪙</b></div><p class="meta">Процент успеха считается только по завершённым выигранным и проигранным ставкам.</p></article>
 </div><div class="profile-tab-panel" data-profile-panel="balance" role="tabpanel"><article class="ticket"><h3>История виртуальных монет</h3><p class="meta">Суммы из журнала операций · даты по UTC</p><div class="balance-table-wrap"><table class="balance-table"><thead><tr><th>Период</th><th>Получено</th><th>Потрачено</th><th>Итог</th></tr></thead><tbody><tr class="balance-highlight"><th>Сегодня</th><td class="win">+${history.today.received.toLocaleString('ru-RU')}</td><td class="lose">−${history.today.spent.toLocaleString('ru-RU')}</td><td class="${history.today.net>=0?'win':'lose'}">${history.today.net>0?'+':''}${history.today.net.toLocaleString('ru-RU')}</td></tr><tr class="balance-highlight"><th>За всё время</th><td class="win">+${history.lifetime.received.toLocaleString('ru-RU')}</td><td class="lose">−${history.lifetime.spent.toLocaleString('ru-RU')}</td><td class="${history.lifetime.net>=0?'win':'lose'}">${history.lifetime.net>0?'+':''}${history.lifetime.net.toLocaleString('ru-RU')}</td></tr></tbody></table></div><div class="balance-table-tools"><b>Динамика баланса</b><select id="historyDays" aria-label="Период истории баланса"><option value="7">7 дней</option><option value="30" selected>30 дней</option><option value="90">90 дней</option></select></div><div id="balanceChart" class="balance-chart"></div><div id="balanceChartSummary" class="balance-chart-summary"></div><h4>По дням</h4><div class="balance-table-wrap"><table class="balance-table"><thead><tr><th>Дата</th><th>Получено</th><th>Потрачено</th><th>Итог</th></tr></thead><tbody id="balanceRows"></tbody></table></div><p class="meta">Начальные монеты входят в текущий баланс, но не считаются заработанными. Итого = получено − потрачено. В расчёт входят бонусы, ставки, выплаты, кэшауты и корректировки.</p></article>
 <article class="ticket"><h3>Последние операции</h3>${p.transactions.length?p.transactions.map(x=>`<div class="profile-tx"><div><b>${escapeHTML(x.reason)}</b><small>${fmtDate(x.created_at)}</small></div><strong class="${x.amount>=0?'win':'lose'}">${x.amount>0?'+':''}${x.amount} 🪙</strong></div>`).join(''):'<p class="meta">Операций пока нет.</p>'}</article></div><button class="primary" id="profileHistory">Моя история ставок →</button>`;
 const drawBalanceRows=(r)=>{$('balanceRows').innerHTML=r.daily.map(d=>`<tr><th>${d.date.split('-').reverse().join('.')}</th><td class="win">+${d.received.toLocaleString('ru-RU')}</td><td class="lose">−${d.spent.toLocaleString('ru-RU')}</td><td class="${d.net>=0?'win':'lose'}">${d.net>0?'+':''}${d.net.toLocaleString('ru-RU')}</td></tr>`).join('')};
 applyMyAvatar();
 $('avatarUpload').onchange=async e=>{
   const file=e.target.files?.[0];if(!file)return;
   if(file.size>2*1024*1024)return notice('Размер фото — не более 2 МБ');
   try{const headers={};if(tg?.initData)headers['X-Telegram-Init-Data']=tg.initData;if(dev)headers['X-Dev-User']=dev;
     headers['Content-Type']=file.type;const res=await fetch('/api/avatar',{method:'PUT',headers,body:file});
     const data=await res.json();if(!res.ok)throw Error(data.detail||'Ошибка загрузки');
     avatarVersion=Date.now();localStorage.setItem(`rdg_avatar_${state.user.id}`,'custom');applyMyAvatar();notice('Аватар обновлён');
   }catch(err){notice(err.message)}
 };
 $('avatarTelegram').onclick=()=>{if(!telegramAvatar())return notice('Telegram не передал фото профиля. Можно загрузить своё.');localStorage.setItem(`rdg_avatar_${state.user.id}`,'telegram');applyMyAvatar()};
 $('avatarInitials').onclick=()=>{localStorage.setItem(`rdg_avatar_${state.user.id}`,'initials');applyMyAvatar()};
 document.querySelectorAll('[data-profile-tab]').forEach(btn=>btn.onclick=()=>selectProfileTab(btn.dataset.profileTab));
 selectProfileTab(profileActiveTab);
 drawBalanceRows(history);balanceChart(history);
 $('historyDays').onchange=async ev=>{try{const r=await api('profile/balance-history?days='+encodeURIComponent(ev.target.value));drawBalanceRows(r);balanceChart(r)}catch(e){notice(e.message)}};
 document.querySelectorAll('[data-quest]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{await api(`quests/${b.dataset.quest}/claim`,'POST');notice('Опыт за задание получен!');await profileView()}catch(e){notice(e.message);b.disabled=false}});
 $('profileHistory').onclick=()=>{state.view='slips';render()};
}
async function referralsView(){
 const r=await api('referrals');
 const invite=r.invite_link||'';
 $('content').innerHTML=`<article class="ticket"><h3>👥 Приглашай друзей</h3><p class="meta">Оба игрока получают опыт после повторного посещения другом приложения в другой день. Никаких денежных наград или условий по ставкам.</p><div class="profile-stats"><div class="profile-metric"><span>Приглашены</span><b>${r.invited}</b></div><div class="profile-metric"><span>Подтверждены</span><b>${r.qualified}</b></div><div class="profile-metric"><span>Получено опыта</span><b>${r.earned_xp} XP</b></div></div>${invite?`<div class="invite-link">${escapeHTML(invite)}</div><button class="primary" id="copyInvite">Скопировать ссылку</button><button id="shareInvite">Поделиться с другом</button>`:'<p class="meta">Чтобы создать персональную ссылку, укажи BOT_USERNAME в настройках сервера.</p>'}</article><article class="ticket"><h3>Мои приглашения</h3>${r.invited_users.length?r.invited_users.map(u=>`<div class="quest-row"><b>${escapeHTML(u.name)}</b><span class="meta">${u.status==='qualified'?'✅ Подтверждено':'⏳ Ожидается'}</span></div>`).join(''):'<p class="meta">Пока нет приглашённых друзей.</p>'}</article>`;
 if(invite){$('copyInvite').onclick=async()=>{try{await navigator.clipboard.writeText(invite);notice('Ссылка скопирована')}catch{notice('Выдели ссылку и скопируй вручную')}}; $('shareInvite').onclick=()=>{if(tg?.openTelegramLink)tg.openTelegramLink('https://t.me/share/url?url='+encodeURIComponent(invite)+'&text='+encodeURIComponent('Присоединяйся к RDG — Rates Diffy Game! Виртуальная футбольная игра.'));else if(navigator.share)navigator.share({url:invite,text:'RDG — Rates Diffy Game'}).catch(()=>{});else notice('Скопируй ссылку выше')}}
}
let chatAfter=0, chatPolling=false;
function chatEntry(m){return `<div class="chat-entry" data-message-id="${m.id}"><button class="chat-author" data-player="${m.user_id}" title="Открыть профиль"><span class="chat-avatar">${escapeHTML((m.name||'И').slice(0,1).toUpperCase())}${avatarImage(m.user_id,'chat-avatar-image')}</span>${escapeHTML(m.name)}${championBadge(m.champion_titles)}</button><small>${fmtDate(m.created_at)}</small><p>${escapeHTML(m.body)}</p>${m.user_id===state.user?.id?'':`<button class="chat-report" data-report="${m.id}">Пожаловаться</button>`}</div>`}
function bindChatEntries(){document.querySelectorAll('[data-player]').forEach(b=>b.onclick=()=>showPublicProfile(Number(b.dataset.player)));document.querySelectorAll('[data-report]').forEach(b=>b.onclick=async()=>{if(!confirm('Отправить жалобу модератору?'))return;try{await api(`chat/messages/${b.dataset.report}/report`,'POST');notice('Жалоба передана модератору')}catch(e){notice(e.message)}})}
async function chatRefresh(){if(chatPolling||state.view!=='chat')return;chatPolling=true;try{const data=await api('chat/messages?after='+chatAfter);const box=$('chatMessages');if(!box)return;if(chatAfter===0){box.innerHTML=data.messages.map(chatEntry).join('')||'<p class="meta">Напиши первое сообщение!</p>'}else if(data.messages.length){if(box.querySelector('.meta'))box.innerHTML='';box.insertAdjacentHTML('beforeend',data.messages.map(chatEntry).join(''))}if(data.messages.length){chatAfter=data.messages.at(-1).id;bindChatEntries();box.scrollTop=box.scrollHeight}}catch(e){notice(e.message)}finally{chatPolling=false}}
async function chatView(){chatAfter=0;$('content').innerHTML=`<section class="chat-shell"><div class="chat-intro"><b>💬 ОБЩИЙ ЧАТ</b><span>Общайся, обсуждай матчи и открывай профили игроков.</span></div><div id="chatMessages" class="chat-messages" role="log" aria-live="polite"></div><form id="chatForm" class="chat-form"><input id="chatText" maxlength="350" autocomplete="off" aria-label="Сообщение" placeholder="Написать сообщение..." required><button type="submit">➤</button></form><small class="chat-rules">Правила: без спама, оскорблений и личных данных. До 350 символов, не чаще раза в 5 секунд.</small></section>`;$('chatForm').onsubmit=async e=>{e.preventDefault();let input=$('chatText');let body=input.value.trim();if(!body)return;let btn=$('chatForm').querySelector('button');btn.disabled=true;try{await api('chat/messages','POST',{body});input.value='';await chatRefresh()}catch(err){notice(err.message)}finally{btn.disabled=false}};await chatRefresh()}
async function showPublicProfile(id){try{
 let [p,f]=await Promise.all([api(`players/${id}/public`),api(`players/${id}/subscription`)]);
 let overlay=document.createElement('div');overlay.className='player-overlay';
 overlay.innerHTML=`<div class="player-modal" role="dialog" aria-modal="true" aria-label="Профиль игрока"><button class="modal-close" aria-label="Закрыть">✕</button><div class="profile-avatar public-profile-avatar">${escapeHTML(p.name.slice(0,2).toUpperCase())}${avatarImage(p.id,'public-avatar-image')}</div><h2>${escapeHTML(p.name)}${championBadge(p.champion_titles)}</h2>${p.champion_titles?`<p class="meta">🏆 Победитель сезона · ${p.champion_titles} титул(ов)</p>`:''}<p class="meta">Публичный профиль игрока</p><div class="profile-stats"><div class="profile-metric"><span>Ставок</span><b>${p.bets}</b></div><div class="profile-metric"><span>Побед</span><b>${p.wins}</b></div><div class="profile-metric"><span>Подписчики</span><b id="followerCount">${f.followers}</b></div><div class="profile-metric"><span>Точность прогнозов</span><b>${p.win_rate}%</b></div><div class="profile-metric"><span>Рассчитано</span><b>${p.resolved}</b></div><div class="profile-metric"><span>Проигрышей</span><b>${p.losses}</b></div></div>${f.is_self?'':`<button class="primary" id="followToggle">${f.subscribed?'Отписаться':'Подписаться'}</button>`}<p class="meta">Баланс, Telegram ID и история операций скрыты.</p></div>`;
 document.body.appendChild(overlay);overlay.onclick=e=>{if(e.target===overlay||e.target.closest('.modal-close'))overlay.remove()};
 let button=overlay.querySelector('#followToggle');if(button)button.onclick=async()=>{button.disabled=true;try{f=await api(`players/${id}/follow`,f.subscribed?'DELETE':'POST');button.textContent=f.subscribed?'Отписаться':'Подписаться';overlay.querySelector('#followerCount').textContent=f.followers;notice(f.subscribed?'Подписка оформлена':'Подписка отменена')}catch(e){notice(e.message)}finally{button.disabled=false}};
 }catch(e){notice(e.message)}}
function rankingAvatar(u){
 const initials=escapeHTML((u.name||'Игрок').trim().slice(0,2).toUpperCase());
 return `<span class="ranking-avatar">${initials}${avatarImage(u.id,'ranking-avatar-image')}</span>`;
}
function leaderboardRow(u){
 const own=u.id===state.user?.id;
 return `<button class="ranking-player ${own?'is-me':''}" data-player="${u.id}" aria-label="Открыть профиль ${escapeHTML(u.name)}">
 <span class="ranking-position">${u.rank}</span>${rankingAvatar(u)}
 <span class="ranking-player-info"><strong>${escapeHTML(u.name)}${championBadge(u.champion_titles)}${own?' · ты':''}</strong><small>Побед: ${u.wins} · Завершено: ${u.resolved}</small></span>
 <span class="ranking-score"><strong>${u.points}</strong><small>очков</small></span></button>`;
}
async function rankingView(){
 const r=await api('seasons/current');const me=r.me;
 const leaders=r.top.slice(0,3), others=r.top.slice(3);
 const days=Math.max(0,Math.ceil(r.remaining_days));
 const movement=r.rank_change===null?'Нет предыдущего снимка':r.rank_change>0?`Поднялся на ${r.rank_change} мест`:r.rank_change<0?`Опустился на ${Math.abs(r.rank_change)} мест`:'Место не изменилось';
 $('content').innerHTML=`<section class="ranking-hero"><span class="eyebrow">СЕЗОННЫЙ РЕЙТИНГ</span><h2>Сезон №${r.season}</h2><p>До завершения: ${days} дн. · Участников: ${r.total_players}</p><div class="ranking-rule">Победа: +3 очка · Кэшаут: +1 · Поражение: 0</div></section>
 ${me?`<section class="ranking-my-place"><span class="ranking-my-label">ТВОЯ ПОЗИЦИЯ</span><strong>№${me.rank}</strong><span>${me.points} очков</span><small>${movement}</small></section>`:''}
 <section class="ranking-board"><div class="ranking-section-title"><h3>Лидеры сезона</h3><small>Топ-3</small></div>
 ${leaders.length?`<div class="ranking-podium">${[leaders[1],leaders[0],leaders[2]].filter(Boolean).map(u=>`<button class="ranking-podium-player place-${u.rank}" data-player="${u.id}" aria-label="Профиль ${escapeHTML(u.name)}"><span class="ranking-medal">${u.rank}</span>${rankingAvatar(u)}<strong>${escapeHTML(u.name)}</strong><span class="ranking-podium-points">${u.points} очков</span><small>${u.wins} побед</small></button>`).join('')}</div>`:'<p class="loading">Игроков пока нет.</p>'}</section>
 ${others.length?`<section class="ranking-board"><div class="ranking-section-title"><h3>Таблица игроков</h3><small>${others.length} участников в списке</small></div><div class="ranking-player-list">${others.map(leaderboardRow).join('')}</div></section>`:''}
 <p class="ranking-note">Места определяются очками сезона, затем количеством побед и рассчитанных купонов. Размер виртуальной ставки не влияет на место. Значок чемпиона получает победитель завершённого сезона.</p>`;
 document.querySelectorAll('[data-player]').forEach(b=>b.onclick=()=>showPublicProfile(Number(b.dataset.player)));
}
async function subscriptionsView(){
 let r=await api('subscriptions');$('content').innerHTML=`<article class="ticket"><h3>👥 Мои подписки</h3><p class="meta">Следи за интересными прогнозистами. Личных сообщений нет.</p>${r.players.length?r.players.map(p=>`<button class="leader-row" data-player="${p.id}"><span>${escapeHTML(p.name)}</span><span>Профиль ›</span></button>`).join(''):'<p class="meta">Нажми на профиль участника в чате или сезонном рейтинге и выбери «Подписаться».</p>'}</article>`;
 document.querySelectorAll('[data-player]').forEach(b=>b.onclick=()=>showPublicProfile(Number(b.dataset.player)));
}

let feedMode='all';
async function feedView(){
 const data=await api('community/feed?mode='+feedMode);
 const upcoming=state.matches.filter(m=>['SCHEDULED','TIMED'].includes(m.status)&&new Date(m.kickoff)>new Date(Date.now()+300000));
 $('content').innerHTML=`<article class="ticket"><h3>📣 Прогнозы сообщества</h3><p class="meta">Публикации — мнения игроков, не советы по ставкам. Прогнозы не приносят очков или монет.</p><div class="filter-row"><button id="feedAll" class="${feedMode==='all'?'active':''}">Все</button><button id="feedFollowing" class="${feedMode==='following'?'active':''}">Подписки</button></div><form id="postForm"><label>Матч<select id="postMatch" required>${upcoming.map(m=>`<option value="${m.id}">${escapeHTML(m.home)} — ${escapeHTML(m.away)}</option>`).join('')}</select></label><label>Исход<select id="postPick">${Object.entries(markets).map(([k,v])=>`<option value="${k}">${escapeHTML(v)}</option>`).join('')}</select></label><textarea id="postComment" maxlength="280" placeholder="Почему такой прогноз? (необязательно)"></textarea><button class="primary" type="submit" ${upcoming.length?'':'disabled'}>Опубликовать прогноз</button></form></article>${data.posts.length?data.posts.map(p=>`<article class="ticket"><div class="matchtop"><button class="chat-author" data-player="${p.author_id}"><span class="chat-avatar">${escapeHTML((p.name||'И').slice(0,1).toUpperCase())}${avatarImage(p.author_id,'chat-avatar-image')}</span>${escapeHTML(p.name)}${championBadge(p.champion_titles)}</button><small>${fmtDate(p.created_at)}</small></div><p><b>${escapeHTML(p.home)} — ${escapeHTML(p.away)}</b></p><p>Прогноз: <strong class="win">${escapeHTML(markets[p.pick]||p.pick)}</strong></p><p>${escapeHTML(p.comment)}</p><div class="filter-row"><button data-like="${p.id}">${p.liked?'♥':'♡'} ${p.likes}</button><button data-report-post="${p.id}">Жалоба</button></div></article>`).join(''):'<p class="meta">Прогнозов пока нет</p>'}`;
 $('feedAll').onclick=()=>{feedMode='all';feedView()};$('feedFollowing').onclick=()=>{feedMode='following';feedView()};
 $('postForm').onsubmit=async e=>{e.preventDefault();try{await api('community/posts','POST',{match_id:Number($('postMatch').value),pick:$('postPick').value,comment:$('postComment').value});notice('Прогноз опубликован');await feedView()}catch(err){notice(err.message)}};
 document.querySelectorAll('[data-player]').forEach(b=>b.onclick=()=>showPublicProfile(Number(b.dataset.player)));
 document.querySelectorAll('[data-like]').forEach(b=>b.onclick=async()=>{try{await api(`community/posts/${b.dataset.like}/like`,'POST');await feedView()}catch(e){notice(e.message)}});
 document.querySelectorAll('[data-report-post]').forEach(b=>b.onclick=async()=>{if(!confirm('Отправить жалобу?'))return;try{await api(`community/posts/${b.dataset.reportPost}/report`,'POST');notice('Жалоба отправлена')}catch(e){notice(e.message)}});
}
async function notificationView(){let data=await api('notifications');$('content').innerHTML=`<article class="ticket"><h3>🔔 Уведомления</h3><p class="meta">События внутри Mini App. Telegram-уведомления могут приходить отдельно.</p>${data.items.length?data.items.map(n=>`<div class="quest-row"><div><b>${escapeHTML(n.text)}</b><small>${fmtDate(n.created_at)}</small></div>${n.read_at?'<span class="meta">Прочитано</span>':`<button data-read="${n.id}">Прочитано ✓</button>`}</div>`).join(''):'<p class="meta">Новых событий нет</p>'}</article>`;document.querySelectorAll('[data-read]').forEach(b=>b.onclick=async()=>{try{await api(`notifications/${b.dataset.read}/read`,'POST');await notificationView()}catch(e){notice(e.message)}})}

function helpView(){
 $('content').innerHTML=`<article class="ticket"><h3>📖 Правила и помощь</h3><p class="meta">RDG — Rates Diffy Game — развлекательная игра на виртуальные монеты. Монеты и XP нельзя покупать, выводить, передавать, обменивать на деньги, Stars или призы.</p>
 <details open><summary>⚽ Одиночные ставки</summary><p>Выбираешь один исход матча. Система фиксирует коэффициент при принятии. За пять минут до начала события приём закрывается. После принятия обычная отмена невозможна.</p></details>
 <details><summary>🎟 Экспрессы</summary><p>От 2 до 8 разных матчей. Для выигрыша должны пройти все невозвращённые исходы. Если событие признано отменённым, соответствующий коэффициент считается 1.0. Досрочное закрытие экспрессов отсутствует.</p></details>
 <details><summary>💸 Кэшаут</summary><p>Только для одиночных ставок и лишь когда сервер получил свежие live-данные. Может быть доступен с 2-й до 84-й минуты. Сумма не гарантирована, обычно снижается при ухудшении шансов; при задержке данных кэшаут выключен.</p></details>
 <details><summary>🏆 Сезоны</summary><p>Один сезон длится 90 дней. Выигранный купон: +3 очка, кэшаут: +1, проигрыш: 0. Значок ✦ навсегда получает только победитель завершённого сезона. Подписки на игроков не сбрасываются.</p></details>
 <details><summary>💬 Чат и публикации</summary><p>Не спамь, не оскорбляй других, не публикуй чужие персональные данные и рекламу денежных ставок. На сообщения и прогнозы можно отправлять жалобы. Модераторы вправе удалить публикацию или временно ограничить чат.</p></details>
 <details><summary>🪙 История монет</summary><p>В профиле доступны таблица и график баланса за 7, 30 и 90 дней. Начальные монеты не учитываются как заработок. Значения формируются из серверного журнала операций.</p></details>
 <details><summary>🛟 Ошибка или вопрос?</summary><p>Сделай скриншот проблемы, запиши время и номер купона (если есть), затем напиши администратору бота через официальный Telegram-канал поддержки, когда он будет указан владельцем проекта. Никогда не отправляй токены, пароли и данные сессии.</p></details>
 <p class="meta">Тестовая версия. Итоги матчей зависят от внешнего футбольного API; при задержках расчёт может выполняться позднее.</p></article>`;
}
async function render(){document.querySelectorAll('.bottom-nav button').forEach(b=>b.classList.toggle('active',b.dataset.view===state.view));$('viewTitle').textContent=({matches:'Ближайшие матчи',live:'Live-центр',slips:'История ставок',coupon:'Мой купон',details:'О матче',ranking:'Таблица лидеров',profile:'Мой профиль',chat:'Общий чат',referrals:'Приглашения',subscriptions:'Подписки',feed:'Лента прогнозов',notifications:'Уведомления',help:'Правила и помощь',admin:'Панель управления'})[state.view];$('filters').hidden=state.view!=='matches';updateBar();$('filters').hidden=state.view!=='matches';try{if(state.view==='matches')matchesView();else if(state.view==='details')detailsView();else if(state.view==='live')await liveView();else if(state.view==='coupon')couponView();else if(state.view==='slips')await slipsView();else if(state.view==='ranking')await rankingView();else if(state.view==='profile')await profileView();else if(state.view==='referrals')await referralsView();else if(state.view==='subscriptions')await subscriptionsView();else if(state.view==='chat')await chatView();else if(state.view==='feed')await feedView();else if(state.view==='notifications')await notificationView();else if(state.view==='help')helpView();else await adminView()}catch(e){notice(e.message)}}
document.querySelectorAll('.bottom-nav button').forEach(b=>b.onclick=()=>{state.view=b.dataset.view;render()});
document.querySelectorAll('[data-menu-view]').forEach(b=>b.onclick=()=>{state.view=b.dataset.menuView;toggleProfileMenu(false);render()});
$('bonus').onclick=async()=>{try{await api('bonus','POST');notice('Начислено +200 монет!');await refreshUser()}catch(e){notice(e.message)}};
async function placeBet(){let stake=Number($('stake').value);if(!Number.isInteger(stake))return notice('Введи целое число монет');$('place').disabled=true;try{let picks=[...state.selected.values()].map(({match_id,pick})=>({match_id,pick}));if(!pendingBetKey)pendingBetKey=crypto.randomUUID();let r=await api('slips','POST',{stake,picks,request_key:pendingBetKey});pendingBetKey=null;state.selected.clear();updateBar();await refreshUser();closeCoupon();notice('Прогноз №'+r.id+' принят! Возможная выплата: '+r.potential+' монет');await render()}catch(e){notice(e.message)}finally{$('place').disabled=false}}
$('place').onclick=placeBet;$('stake').oninput=()=>{pendingBetKey=null;updateBar()};$('couponFloat').onclick=openCoupon;$('closeCoupon').onclick=closeCoupon;$('couponScrim').onclick=closeCoupon;document.addEventListener('keydown',e=>{if(e.key==='Escape')closeCoupon()});
async function start(){try{state.matches=(await api('matches')).matches;await refreshUser();await render()}catch(e){notice(e.message)}}start();setInterval(()=>{if(state.view==='chat')chatRefresh()},3500);setInterval(async()=>{try{state.matches=(await api('matches')).matches;if(state.view==='matches')matchesView();else if(state.view==='live')await liveView()}catch{}},20000);

async function showChatModeration(){try{let reports=await api('admin/chat/reports');let node=$('chatModeration');if(!node)return;node.innerHTML='<b>Жалобы на сообщения</b>'+(reports.length?reports.map(r=>`<div class="admin-row"><b>${escapeHTML(r.name)}</b> (${r.reports} жалоб): ${escapeHTML(r.body)}<div><button data-delmsg="${r.id}">Удалить</button> <button data-muteuser="${r.user_id}">Мут 60 мин</button></div></div>`).join(''):'<p class="meta">Новых жалоб нет.</p>');node.querySelectorAll('[data-delmsg]').forEach(b=>b.onclick=async()=>{if(!confirm('Удалить сообщение?'))return;try{await api(`admin/chat/messages/${b.dataset.delmsg}`,'DELETE');await showChatModeration()}catch(e){notice(e.message)}});node.querySelectorAll('[data-muteuser]').forEach(b=>b.onclick=async()=>{if(!confirm('Ограничить чат на 60 минут?'))return;try{await api(`admin/chat/players/${b.dataset.muteuser}/mute`,'POST',{minutes:60});notice('Мут установлен')}catch(e){notice(e.message)}})}catch(e){notice(e.message)}}
async function adminView(){
 if(!state.user?.is_admin){$('content').textContent='Доступ запрещён';return}
 const [o,users,activity]=await Promise.all([api('admin/overview'),api('admin/players'),api('admin/activity')]);
 $('content').innerHTML=`<div class="admin-grid">${[['Игроки',o.users],['Матчи',o.matches],['Купоны',o.slips],['Ожидают',o.pending_slips]].map(([k,v])=>`<div class="metric">${k}<b>${v}</b></div>`).join('')}</div>
 <div class="admin-panel"><b>Управление матчами</b><input id="cancelId" type="number" placeholder="ID матча"><button class="danger" id="cancelMatch">Отменить матч и пересчитать</button><button id="forceSync">Обновить матчи из API</button></div>
 <div class="admin-panel"><b>Корректировка виртуального баланса</b><input id="playerId" type="number" placeholder="Telegram ID игрока"><input id="adjustAmount" type="number" placeholder="Монеты (например, 100 или -100)"><input id="adjustReason" type="text" maxlength="120" placeholder="Причина корректировки"><button id="adjust">Применить изменение</button></div>
 <div class="admin-panel"><b>Игроки (последние 50)</b>${users.map(u=>`<div class="admin-row">${escapeHTML(u.name)} · ID ${u.id} · ${u.balance} ◈ · Купонов ${u.slips}</div>`).join('')}</div>
 <div class="admin-panel"><b>Аудит сезонного рейтинга</b><button id="auditSeason">Проверить аномалии</button><button id="snapshotSeason">Сохранить снимок рейтинга</button><div id="auditResults"></div></div><div class="admin-panel" id="chatModeration"><button id="loadReports">Открыть жалобы чата</button></div>
 <div class="admin-panel"><b>Последние операции</b>${activity.map(a=>`<div class="admin-row">${escapeHTML(a.name)} · ${a.amount>0?'+':''}${a.amount} ◈ · ${escapeHTML(a.reason)}</div>`).join('')}</div>`;
 $('loadReports').onclick=showChatModeration;$('auditSeason').onclick=async()=>{try{const a=await api('admin/seasons/audit');$('auditResults').textContent=a.flags.length?a.flags.map(x=>`ID ${x.user_id}: ${x.reason}`).join(' | '):'Флагов нет'}catch(e){notice(e.message)}};$('snapshotSeason').onclick=async()=>{try{const a=await api('admin/seasons/snapshot','POST');notice('Снимок сохранён для '+a.players+' игроков')}catch(e){notice(e.message)}};
 $('forceSync').onclick=()=>adminAction('admin/sync',{});
 $('cancelMatch').onclick=()=>{let id=Number($('cancelId').value);if(!Number.isSafeInteger(id))return notice('Укажи ID матча');if(confirm('Отменить матч '+id+'?'))adminAction(`admin/matches/${id}/cancel`,{})};
 $('adjust').onclick=()=>{let id=Number($('playerId').value),amount=Number($('adjustAmount').value),reason=$('adjustReason').value.trim();if(!Number.isSafeInteger(id)||id<=0||!Number.isSafeInteger(amount)||!amount||!reason)return notice('Заполни ID, сумму и причину');if(confirm('Изменить баланс игрока '+id+' на '+amount+'?'))adminAction(`admin/players/${id}/balance`,{amount,reason})};
}
async function adminAction(path,body){try{await api(path,'POST',body);notice('Операция выполнена');await refreshUser();await adminView()}catch(e){notice(e.message)}}
$('reload').onclick=async()=>{try{state.matches=(await api('matches')).matches;await render();notice('Данные обновлены')}catch(e){notice(e.message)}};
$('profileMenuButton').onclick=(e)=>{e.stopPropagation();toggleProfileMenu()};
document.addEventListener('click',e=>{const menu=$('profileMenu');const btn=$('profileMenuButton');if(menu.classList.contains('hidden'))return;if(!menu.contains(e.target)&&!btn.contains(e.target))toggleProfileMenu(false)});

