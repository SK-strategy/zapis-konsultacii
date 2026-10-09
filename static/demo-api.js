/* Демо-режим для GitHub Pages: подменяет сервер, данные живут в localStorage этого браузера.
   Повторяет правила server/app.py: слоты, запись без дублей, клиенты по телефону, CRM, статистика. */
(function(){
  const FUNNEL = {"expert": "Анастасия Губенко", "privacy_url": "https://disk.yandex.ru/i/gwbEAvPS6gu3oA", "greeting": {"title": "Спасибо, что перешли по ссылке!", "text": "Здесь всего три коротких вопроса о вашей ситуации — это займёт меньше минуты.\n\nСразу после ответов вы узнаете, подходит ли вам списание долгов и какой путь в вашем случае самый реальный. А если захотите, тут же выберете время для бесплатной консультации.", "button": "Начать тест"}, "intro": "Процедура банкротства — это не что-то страшное или постыдное. Она создана для того, чтобы помочь хорошим людям в сложной жизненной ситуации. Ко мне приходят женщины, которые брали кредиты на лечение близких. Люди, пострадавшие от мошенников. И те, кто просто не рассчитал свои финансовые возможности. Я занимаюсь этим вопросом уже много лет и за это время освободила от долгов сотни людей. Я здесь, чтобы помочь и вам.", "questions": [{"id": "debt", "text": "Какова сумма вашего долга?", "options": [{"id": "lt100", "label": "до 100 000 ₽", "short": "долг до 100 тыс."}, {"id": "100_500", "label": "100 000 – 500 000 ₽", "short": "долг 100–500 тыс."}, {"id": "gt500", "label": "более 500 000 ₽", "short": "долг более 500 тыс."}]}, {"id": "property", "text": "Есть ли у вас имущество?", "hint": "Квартира, машина, земельный участок или другое ценное движимое или недвижимое имущество", "options": [{"id": "yes", "label": "Да, есть имущество", "short": "есть имущество"}, {"id": "no", "label": "Нет, имущества нет", "short": "нет имущества"}]}, {"id": "work", "text": "Есть ли у вас официальная работа?", "options": [{"id": "official", "label": "Да, работаю официально", "short": "работает официально"}, {"id": "none", "label": "Нет, официальной работы нет", "short": "нет работы"}, {"id": "business", "label": "Есть ИП / самозанятость / ООО", "short": "ИП / самозанятость / ООО"}]}], "scenarios": {"s1": {"title": "Долг >500к, есть имущество, официальная работа", "text": "Спасибо за ответы! Я проанализировала вашу ситуацию. Сумма более 500 тысяч при наличии официальной работы и имущества — это классическая рабочая ситуация. Сразу успокою: единственное жильё неприкосновенно, а по остальному имуществу мы на консультации разберём, как защитить его и сохранить. Официальная работа не мешает процессу, а зарплата будет приходить раз в месяц. Положенные вам по закону деньги останутся с вами. Списывали долги и с доходом 120 тысяч."}, "s2": {"title": "Долг >500к, нет имущества, нет работы", "text": "Спасибо за ответы! Я проанализировала вашу ситуацию. Долг свыше 500 тысяч рублей и отсутствие работы — это первое основание для списания долгов. Суд понимает кризисы и не наказывает за это. Закон создан как раз для того, чтобы вытащить вас из этой ямы и освободить от звонков кредиторов. Более того, в законе есть фраза, что если долг свыше 500 000 рублей, гражданин обязан подать на процедуру банкротства."}, "s3": {"title": "Долг >500к, есть имущество, ИП / самозанятость / ООО", "text": "Спасибо за ответы! Я проанализировала вашу ситуацию. Наличие бизнеса, статуса ИП или самозанятости требует грамотного подхода: здесь важно правильно отработать вопросы с налоговой и защитить личное имущество. При этом закон позволяет списать как личные кредиты, так и долги, связанные с предпринимательством."}, "s4": {"title": "Долг >500к, есть имущество, нет работы — срочно", "text": "Спасибо за ответы! Я проанализировала вашу ситуацию. Большая сумма долга при наличии имущества и отсутствии работы — ситуация, требующая срочного решения. Я бы даже сказала, что вам нужно было обратиться ещё вчера, чтобы понимать, что делать. Сразу успокою: единственное жильё неприкосновенно, а по остальному имуществу мы на консультации разберём, как его защитить. То, что сейчас нет работы, — это нормально, суд понимает жизненные кризисы и не наказывает за это."}, "s5": {"title": "Долг >500к, нет имущества, официальная работа", "text": "Спасибо за ответы! Я проанализировала вашу ситуацию. Сумма более 500 тысяч при отсутствии имущества и наличии официальной работы — это классическая и очень понятная процедура. Отсутствие имущества упрощает дело (суду нечего описывать). А официальная работа не мешает процессу: по закону зарплата будет приходить раз в месяц. Положенные вам по закону деньги останутся с вами. Списывали долги и с доходом 120 000 рублей."}, "s6": {"title": "Долг >500к, нет имущества, ИП / самозанятость / ООО", "text": "Спасибо за ответы! Я проанализировала вашу ситуацию. Большая сумма долга при наличии бизнеса или статуса ИП/самозанятого (и при отсутствии личного имущества) — частый кейс. Отсутствие лишнего имущества — это плюс, а вот с бизнесом и налогами нужно поработать грамотно. Закон позволяет списать как личные кредиты, так и предпринимательские долги."}, "s7": {"title": "Долг до 500к — оценить варианты, возможно МФЦ", "text": "Спасибо за ответы! Я проанализировала вашу ситуацию. При такой сумме долга стандартное судебное банкротство нужно оценивать аккуратно, чтобы расходы на процедуру не были бессмысленными. Но это не значит, что выхода нет! Есть иные законные пути — например, внесудебное банкротство через МФЦ или инструменты снижения нагрузки без суда. Но есть нюансы, к примеру, если у вас нет просрочек. Приходите на консультацию: мы посмотрим документы и, если вы подходите под списание долгов через МФЦ, скажем об этом."}}, "offer": {"title": "Приглашаю на бесплатную консультацию", "text": "Разберём вашу ситуацию и составим план действий. Консультация проходит в формате телефонного разговора.\n\nЕсли по итогу вы решите идти в процедуру — есть возможность оплаты в беспроцентную рассрочку или после того, как вас признают банкротом. Без рисков и предоплат.", "button": "Выбрать время звонка"}, "done": "Спасибо! Я позвоню вам в выбранное время. Если до этого возникнут вопросы — пишите в Instagram, я на связи!"};
  const HOURS=[6,7,8,9,10,11,12], WORKDAYS=[0,1,2,3,4], DAYS_AHEAD=14, LEAD_MIN=60, SLOT_MIN=60, MSK=3*3600e3;
  const STATUSES={booked:'Записан',came:'Пришёл',noshow:'Не пришёл',bought:'Купил',cancelled:'Отменён'};
  const KEY='zapis-demo-v2';
  const load=()=>{try{return JSON.parse(localStorage.getItem(KEY))||null}catch(e){return null}};
  let db=load()||{seq:1,clients:[],bookings:[],blocked:{},events:{}};
  const save=()=>{try{localStorage.setItem(KEY,JSON.stringify(db))}catch(e){}};
  const pad=n=>String(n).padStart(2,'0');
  const iso=()=>new Date().toISOString().slice(0,19)+'+00:00';
  const dk=t=>`${t.getUTCFullYear()}-${pad(t.getUTCMonth()+1)}-${pad(t.getUTCDate())}`;
  const todayMsk=()=>dk(new Date(Date.now()+MSK));
  const addDays=(s,n)=>{const[y,m,d]=s.split('-').map(Number);return dk(new Date(Date.UTC(y,m-1,d+n)));};
  const wd=s=>{const[y,m,d]=s.split('-').map(Number);return(new Date(Date.UTC(y,m-1,d)).getUTCDay()+6)%7;};
  const start=(s,h)=>{const[y,m,d]=s.split('-').map(Number);return Date.UTC(y,m-1,d,h)-MSK;};
  const startIso=(s,h)=>`${s}T${pad(h)}:00:00+03:00`;
  const slotId=(s,h)=>`${s}_${pad(h)}`;
  const active=b=>b.status!=='cancelled';
  const QUESTIONS={};FUNNEL.questions.forEach(q=>{QUESTIONS[q.id]={};q.options.forEach(o=>QUESTIONS[q.id][o.id]=o);});
  function scenario(a){if(a.debt!=='gt500')return's7';return{'yes|official':'s1','no|none':'s2','yes|business':'s3','yes|none':'s4','no|official':'s5','no|business':'s6'}[a.property+'|'+a.work];}
  function cleanQuiz(r){if(!r||typeof r!=='object')return null;const a={};for(const k in QUESTIONS){if(!QUESTIONS[k][r[k]])return null;a[k]=r[k];}
    const sc=scenario(a);return{answers:a,scenario:sc,scenario_title:FUNNEL.scenarios[sc].title,summary:Object.keys(QUESTIONS).map(k=>QUESTIONS[k][a[k]].short).join(' · ')};}
  function normPhone(raw){let d=String(raw||'').replace(/\D/g,'');if(d.length===11&&d[0]==='8')d='7'+d.slice(1);if(d.length===10)d='7'+d;return d.length>=10&&d.length<=15?'+'+d:null;}
  function problem(date,hour,forClient){
    if(!/^\d{4}-\d{2}-\d{2}$/.test(date||''))return'Неверная дата.';
    if(!HOURS.includes(hour)||!WORKDAYS.includes(wd(date)))return'В это время консультаций нет.';
    if(forClient){const diff=(Date.UTC(...date.split('-').map((x,i)=>i===1?x-1:+x))-Date.UTC(...todayMsk().split('-').map((x,i)=>i===1?x-1:+x)))/864e5;
      if(diff>=DAYS_AHEAD)return'Запись на эту дату ещё не открыта.';if(start(date,hour)-Date.now()<LEAD_MIN*6e4)return'Это время уже прошло или до него меньше часа.';}
    if(db.blocked[slotId(date,hour)])return'Это время закрыто.';return null;}
  function upsertClient(name,phone){let c=db.clients.find(x=>x.phone===phone);const t=iso();
    if(c){c.name=name;c.updated_at=t;return c;}c={id:db.seq++,phone,name,instagram:'',status:'booked',notes:'',quiz:null,created_at:t,updated_at:t};db.clients.push(c);return c;}
  function createBooking(date,hour,name,phone,note,source,quiz){
    const id=slotId(date,hour);if(db.bookings.some(b=>b.slot===id&&active(b)))return null;
    const c=upsertClient(name,phone);const token=Math.random().toString(36).slice(2);
    db.bookings.push({id:db.seq++,slot:id,date,hour,client_id:c.id,note:note||'',source,status:'booked',token,created_at:iso(),created_by:source==='manager'?'Демо-менеджер':null,quiz:quiz||null});
    c.status='booked';c.updated_at=iso();if(quiz)c.quiz=quiz;save();return token;}
  function eventPayload(date,hour,token){
    const s=new Date(start(date,hour)),e=new Date(start(date,hour)+SLOT_MIN*6e4),f=t=>t.toISOString().replace(/[-:]/g,'').slice(0,15)+'Z';
    const title=FUNNEL.event_title||'Консультация';
    const ics=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//zapis-demo//RU','BEGIN:VEVENT',`UID:${token}@zapis-demo`,`DTSTAMP:${f(new Date())}`,`DTSTART:${f(s)}`,`DTEND:${f(e)}`,`SUMMARY:${title}`,'BEGIN:VALARM','TRIGGER:-PT1H','ACTION:DISPLAY',`DESCRIPTION:${title} через час`,'END:VALARM','END:VEVENT','END:VCALENDAR'].join('\r\n');
    return{date,hour,start:startIso(date,hour),ics:'data:text/calendar;charset=utf-8,'+encodeURIComponent(ics),
      gcal:`https://calendar.google.com/calendar/render?action=TEMPLATE&text=${encodeURIComponent(title)}&dates=${f(s)}/${f(e)}`};}
  const clientOf=id=>db.clients.find(c=>c.id===id);
  const row=b=>{const c=clientOf(b.client_id);return{...b,client:{id:c.id,name:c.name,phone:c.phone,instagram:c.instagram}};};
  const R=(status,obj)=>Promise.resolve(new Response(JSON.stringify(obj),{status,headers:{'Content-Type':'application/json'}}));

  const routes=[
    ['GET',/^\/api\/funnel$/,()=>R(200,FUNNEL)],
    ['POST',/^\/api\/track$/,(m,b)=>{if(['open','start','quiz_done'].includes(b.event)&&b.sid){const k=b.sid+'|'+b.event;if(!db.events[k]){db.events[k]=todayMsk();save();}}return R(200,{ok:true});}],
    ['GET',/^\/api\/slots$/,()=>{const out=[],t=todayMsk();for(let i=0;i<DAYS_AHEAD;i++){const s=addDays(t,i);if(!WORKDAYS.includes(wd(s)))continue;
      out.push({date:s,slots:HOURS.map(h=>({hour:h,start:startIso(s,h),free:!db.bookings.some(b=>b.slot===slotId(s,h)&&active(b))&&!db.blocked[slotId(s,h)]&&start(s,h)>Date.now()+LEAD_MIN*6e4}))});}
      return R(200,{days:out,slot_minutes:SLOT_MIN});}],
    ['POST',/^\/api\/book$/,(m,b)=>{const name=(b.name||'').trim(),phone=normPhone(b.phone);
      if(!name)return R(400,{error:'Укажите, как к вам обращаться.'});if(!phone)return R(400,{error:'Проверьте номер телефона: нужен номер с кодом страны или из 10–11 цифр.'});
      if(!b.consent)return R(400,{error:'Отметьте согласие на обработку данных — без него записать не получится.'});
      const p=problem(b.date,b.hour,true);if(p)return R(409,{error:p});
      const quiz=b.quiz?cleanQuiz(b.quiz):null;const tok=createBooking(b.date,b.hour,name,phone,'','bot',quiz);
      return tok?R(200,{ok:true,...eventPayload(b.date,b.hour,tok)}):R(409,{error:'Это время только что заняли. Выберите другое.'});}],
    ['POST',/^\/admin\/logout$/,()=>R(200,{ok:true})],
    ['GET',/^\/api\/admin\/me$/,()=>R(200,{name:'Демо-менеджер',hours:HOURS,workdays:WORKDAYS,statuses:STATUSES})],
    ['GET',/^\/api\/admin\/week$/,(m,b,u)=>{const s=u.searchParams.get('start'),e=addDays(s,7);
      const bl={};for(const k in db.blocked)if(k>=s&&k<e)bl[k]=db.blocked[k].reason||'';
      return R(200,{bookings:db.bookings.filter(x=>active(x)&&x.date>=s&&x.date<e).map(row),blocked:bl,now:iso()});}],
    ['POST',/^\/api\/admin\/bookings$/,(m,b)=>{const name=(b.name||'').trim(),phone=normPhone(b.phone);
      if(!name)return R(400,{error:'Укажите имя.'});if(!phone)return R(400,{error:'Укажите телефон: он нужен, чтобы найти клиента в CRM.'});
      const p=problem(b.date,b.hour,false);if(p)return R(409,{error:p});const tok=createBooking(b.date,b.hour,name,phone,b.note,'manager',null);
      return tok?R(200,{ok:true}):R(409,{error:'Это время только что заняли.'});}],
    ['PATCH',/^\/api\/admin\/bookings\/(\d+)$/,(m,b)=>{const x=db.bookings.find(y=>y.id===+m[1]);if(!x)return R(404,{error:'Запись не найдена.'});
      if(!STATUSES[b.status])return R(400,{error:'Неизвестный статус.'});x.status=b.status;if(b.status!=='cancelled'){const c=clientOf(x.client_id);c.status=b.status;c.updated_at=iso();}save();return R(200,{ok:true});}],
    ['POST',/^\/api\/admin\/blocked$/,(m,b)=>{const id=slotId(b.date,b.hour);if(db.bookings.some(x=>x.slot===id&&active(x)))return R(409,{error:'На это время уже есть запись.'});
      db.blocked[id]={reason:(b.reason||'').slice(0,120)};save();return R(200,{ok:true});}],
    ['DELETE',/^\/api\/admin\/blocked\/(.+)$/,(m)=>{delete db.blocked[decodeURIComponent(m[1])];save();return R(200,{ok:true});}],
    ['GET',/^\/api\/admin\/clients$/,(m,b,u)=>{const q=(u.searchParams.get('q')||'').toLowerCase().trim(),st=u.searchParams.get('status')||'',dg=q.replace(/\D/g,'');
      let list=db.clients.filter(c=>(!st||c.status===st)&&(!q||c.name.toLowerCase().includes(q)||(c.notes||'').toLowerCase().includes(q)||(dg&&c.phone.includes(dg))));
      list=list.sort((a,b)=>a.updated_at<b.updated_at?1:-1).map(c=>{const bs=db.bookings.filter(x=>x.client_id===c.id&&active(x));
        return{...c,visits:bs.length,last_slot:bs.map(x=>x.slot).sort().pop()||null};});return R(200,{clients:list});}],
    ['GET',/^\/api\/admin\/clients\/(\d+)$/,(m)=>{const c=clientOf(+m[1]);if(!c)return R(404,{error:'Клиент не найден.'});
      return R(200,{client:c,bookings:db.bookings.filter(x=>x.client_id===c.id).sort((a,b)=>a.slot<b.slot?1:-1).map(row)});}],
    ['PATCH',/^\/api\/admin\/clients\/(\d+)$/,(m,b)=>{const c=clientOf(+m[1]);if(!c)return R(404,{error:'Клиент не найден.'});
      if(b.name&&b.name.trim())c.name=b.name.trim();if('notes'in b)c.notes=b.notes||'';if('status'in b){if(!STATUSES[b.status]||b.status==='cancelled')return R(400,{error:'Неизвестный статус.'});c.status=b.status;}
      c.updated_at=iso();save();return R(200,{ok:true});}],
    ['GET',/^\/api\/admin\/stats$/,(m,b,u)=>{const days=+(u.searchParams.get('days')||7),since=addDays(todayMsk(),-(days-1)),cnt={open:0,start:0,quiz_done:0};
      for(const k in db.events){const ev=k.split('|')[1];if(db.events[k]>=since&&ev in cnt)cnt[ev]++;}
      cnt.booked=db.bookings.filter(x=>x.source==='bot'&&x.created_at.slice(0,10)>=since).length;return R(200,{days,...cnt});}],
  ];
  const realFetch=window.fetch.bind(window);
  window.fetch=function(input,opt={}){
    const u=new URL(typeof input==='string'?input:input.url,location.origin);
    const path=u.pathname.replace(/^.*?(\/(api|admin)\/)/,'$1');
    const method=(opt.method||'GET').toUpperCase();
    db=load()||db; // другая вкладка могла изменить данные
    for(const[mth,re,fn]of routes){const m=path.match(re);if(m&&mth===method){let b={};try{b=opt.body?JSON.parse(opt.body):{}}catch(e){}return fn(m,b,u);}}
    return realFetch(input,opt);
  };
  window.ZAPIS_DEMO={reset(){db={seq:1,clients:[],bookings:[],blocked:{},events:{}};save();}};
})();
