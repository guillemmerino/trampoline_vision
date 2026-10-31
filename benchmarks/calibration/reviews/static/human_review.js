/* Review original-pixel candidates; human verdicts never default to model verdicts. */
"use strict";
const B = JSON.parse(document.getElementById("bundle").textContent);
const INITIAL = JSON.parse(document.getElementById("initialState").textContent);
const $ = id => document.getElementById(id);
const clone = value => JSON.parse(JSON.stringify(value));
const STORE = "gymnast-review:" + INITIAL.bundle_sha256;
const CURSOR = STORE + ":cursor";
const NAV = STORE + ":navigation";
const VERDICTS = {pending:"Pendent",approved:"Anotació aprovada",rejected:"Anotació rebutjada",missing:"Falta una anotació útil",corrected:"Caixa corregida",uncertain:"Indeterminat",sufficient:"Caixa suficient aprovada",partial:"Parcial útil, amb avís",incorrect:"Candidata rebutjada",absent:"Cap caixa útil"};
let state = clone(INITIAL), online = false, blocked = false, revision = 0, dirty = 0, saved = 0, saving = false, timer;
let current = B.frames[0], detector = Object.keys(B.detectors)[0], selected = null, filtered = [], position = 0;
let image = null, loadVersion = 0, drawMode = false, drag = null;
const canvas = $("canvas"), ctx = canvas.getContext("2d");
function message(text) { $("notice").textContent = text; $("notice").hidden = !text; }
function status(text, error=false) { $("saveStatus").textContent=text; $("saveStatus").classList.toggle("error",error); }
function defaultEntry() {return {presence:"pending",reference:{verdict:"pending",bbox_xyxy:null,source:"none",candidate:null},detectors:{},notes:"",updated_at:new Date().toISOString()};}
function entry() { return state.entries[current.key] || defaultEntry(); }
function boxes() { return current.variants[detector].boxes; }
function candidate() { return boxes().find(b => b.det_id === selected) || null; }
function overlap(a,b) {if(!a||!b)return 0;const x=Math.max(0,Math.min(a[2],b[2])-Math.max(a[0],b[0])),y=Math.max(0,Math.min(a[3],b[3])-Math.max(a[1],b[1]));return x*y/((a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-x*y);}
function localBackup() {try {localStorage.setItem(STORE,JSON.stringify(state));return true;} catch(e){status("No s’ha pogut fer la còpia local: exporta les decisions",true);return false;}}
function changed(mutator) {
  const e = clone(entry()); mutator(e); e.updated_at=new Date().toISOString();state.entries[current.key]=e;dirty++;
  localBackup();status(online?"Canvis pendents de desar…":"Desat al navegador · exporta per compartir");
  clearTimeout(timer);timer=setTimeout(persist,350);renderControls();updateProgress();paint();
}
async function persist() {
  clearTimeout(timer);
  if (!online || blocked || saving || dirty === saved) return !blocked;
  saving=true;const seq=dirty,payload=clone(state);
  try {
    const response=await fetch("/api/state",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({base_revision:revision,state:payload})});
    const data=await response.json();if(!response.ok){if(response.status===409)blocked=true;throw Error(data.error||"No s’ha pogut desar");}
    revision=data.revision;state.revision=revision;state.updated_at=data.updated_at;saved=seq;localBackup();
    status(dirty===saved?`Desat al servidor · revisió ${revision}`:"Desant els darrers canvis…");
  } catch(e){message(e.message+" La còpia del navegador es conserva; pots exportar-la.");status("No s’ha desat al servidor",true);return false;}
  finally {saving=false;}
  if(dirty!==saved)return persist();return true;
}
function updateProgress() {
  const entries=Object.values(state.entries),approved=entries.filter(e=>["approved","corrected"].includes(e.reference.verdict)).length;
  const verdicts=entries.reduce((n,e)=>n+Object.values(e.detectors).filter(d=>d.verdict!=="pending").length,0);
  $("progress").textContent=`${entries.length}/${B.frames.length} fotogrames amb decisions · ${approved} anotacions aprovades/corregides · ${verdicts} valoracions de YOLO`;
}
function applyFilter(preferred=current?.key) {
  const scope=$("scope").value,video=$("video").value,search=$("frameSearch").value.trim();
  filtered=B.frames.filter(f=>(video==="all"||f.case_id===video)&&(!search||String(f.frame_index).includes(search))&&
    (scope==="all"||scope==="priority"&&f.priority||scope==="excluded"&&f.reference.state!=="visible"||scope==="gains"&&f.gain||scope==="reviewed"&&state.entries[f.key]||scope==="unreviewed"&&!state.entries[f.key]));
  position=Math.max(0,filtered.findIndex(f=>f.key===preferred));
  if(filtered.length){document.querySelector("aside").hidden=false;$("canvasViewport").hidden=false;$("variants").hidden=false;showFrame(filtered[position]);}else{image=null;loadVersion++;document.querySelector("aside").hidden=true;$("canvasViewport").hidden=true;$("variants").hidden=true;$("frameTitle").textContent="Cap fotograma amb aquest filtre";$("frameInfo").textContent="Canvia el filtre per continuar.";$("previous").disabled=$("next").disabled=$("saveNext").disabled=true;}
}
function showFrame(frame) {
  current=frame;drawMode=false;drag=null;$("draw").classList.remove("active");canvas.classList.remove("drawing");
  const e=entry(),decision=e.detectors[detector];
  selected=decision?.candidate_id??null;
  if(selected===null&&frame.reference.bbox_xyxy&&boxes().length)selected=[...boxes()].sort((a,b)=>overlap(b.bbox_xyxy,frame.reference.bbox_xyxy)-overlap(a.bbox_xyxy,frame.reference.bbox_xyxy)||b.confidence-a.confidence)[0].det_id;
  $("showOthers").checked=!frame.reference.bbox_xyxy;$("originalOnly").checked=false;
  $("frameTitle").textContent=`${frame.case_id} · f${frame.frame_index}`;
  $("frameInfo").textContent=`${position+1}/${filtered.length} del filtre · ${frame.timestamp_s.toFixed(3)} s · ${frame.partition==="reserved"?"reserva temporal":"desenvolupament"} · ${frame.width}×${frame.height}`;
  $("previous").disabled=position===0;$("next").disabled=$("saveNext").disabled=position===filtered.length-1;
  canvas.width=frame.width;canvas.height=frame.height;setZoom();image=null;const token=++loadVersion;
  $("imageStatus").textContent="Carregant original…";
  const img=new Image();img.onload=()=>{if(token!==loadVersion)return;image=img;$("imageStatus").textContent="";paint();};
  img.onerror=()=>{if(token===loadVersion){$("imageStatus").textContent="No s’ha pogut carregar la imatge";message("Obre la pàgina des del servidor de revisió per carregar els originals.");}};
  img.src=frame.image;$("notes").value=e.notes;renderControls();paint();
  try{localStorage.setItem(CURSOR,frame.key);storeNavigation();}catch(e){}
}
function renderControls() {
  const e=entry(),v=current.variants[detector],ref=e.reference,decision=e.detectors[detector]||{verdict:"pending",candidate_id:null};
  $("presence").value=e.presence;
  $("referenceInfo").textContent=current.reference.bbox_xyxy?`Original d’IA: ${current.reference.bbox_xyxy.join(", ")} · ${current.reference.state}`:`Original d’IA: ${current.reference.state}; sense caixa. Pots validar YOLO i dibuixar-ne una.`;
  $("referenceVerdict").textContent=VERDICTS[ref.verdict]+(ref.bbox_xyxy?` · [${ref.bbox_xyxy.map(x=>Math.round(x*10)/10).join(", ")}]`:"");
  document.querySelectorAll("[data-reference]").forEach(b=>{b.setAttribute("aria-pressed",b.dataset.reference===ref.verdict);b.disabled=b.dataset.reference==="approved"&&!current.reference.bbox_xyxy;});
  $("detectorInfo").textContent=`Confiança ${B.detectors[detector].confidence} · ${v.boxes.length} caixes de persona. IoU original: ${v.evaluation.max_iou===null?"no avaluada":v.evaluation.max_iou.toFixed(3)}.`;
  $("candidate").replaceChildren(new Option("— Escull una caixa —",""));
  const target=ref.bbox_xyxy||current.reference.bbox_xyxy;
  const sorted=[...boxes()].sort((a,b)=>overlap(b.bbox_xyxy,target)-overlap(a.bbox_xyxy,target)||b.confidence-a.confidence);
  for(const b of sorted)$("candidate").add(new Option(`#${b.det_id} · score ${b.confidence.toPrecision(3)}${target?` · IoU ${overlap(b.bbox_xyxy,target).toFixed(3)}`:""}`,String(b.det_id)));
  $("candidate").value=selected===null?"":String(selected);
  const c=candidate();$("candidateInfo").textContent=c?`Caixa #${c.det_id}: [${c.bbox_xyxy.map(x=>x.toFixed(1)).join(", ")}]. El score no és una probabilitat calibrada.`:"Encara no has seleccionat cap detecció.";
  $("adopt").disabled=!c;
  document.querySelectorAll("[data-detector]").forEach(b=>{b.setAttribute("aria-pressed",b.dataset.detector===decision.verdict&&(["pending","absent"].includes(decision.verdict)||decision.candidate_id===selected));b.disabled=["sufficient","partial","incorrect"].includes(b.dataset.detector)&&!c;});
  $("detectorVerdict").textContent=VERDICTS[decision.verdict]+(decision.candidate_id!==null?` · candidata #${decision.candidate_id}`:"");
  for(const b of $("variants").children)b.setAttribute("aria-pressed",b.dataset.id===detector);
}
function storeNavigation(){try{localStorage.setItem(NAV,JSON.stringify({video:$("video").value,scope:$("scope").value,search:$("frameSearch").value,detector,zoom:$("zoom").value}));}catch(e){}}
function setZoom(){
  storeNavigation();
  const viewport=$("canvasViewport"),fit=Math.min(viewport.clientWidth,viewport.clientHeight*current.width/current.height),scale=fit*Number($("zoom").value)/current.width;
  canvas.style.width=`${Math.floor(current.width*scale)}px`;
  requestAnimationFrame(()=>{const target=entry().reference.bbox_xyxy||current.reference.bbox_xyxy||candidate()?.bbox_xyxy;if(target&&Number($("zoom").value)>1){viewport.scrollLeft=canvas.offsetLeft+(target[0]+target[2])/2*scale-viewport.clientWidth/2;viewport.scrollTop=(target[1]+target[3])/2*scale-viewport.clientHeight/2;}else{viewport.scrollLeft=0;viewport.scrollTop=0;}});
}
function rectangle(box,color,width=3,dash=[]) {ctx.strokeStyle=color;ctx.lineWidth=width;ctx.setLineDash(dash);ctx.strokeRect(box[0],box[1],box[2]-box[0],box[3]-box[1]);ctx.setLineDash([]);}
function paint() {
  ctx.clearRect(0,0,canvas.width,canvas.height);if(image)ctx.drawImage(image,0,0);if($("originalOnly").checked)return;
  const e=entry();
  if($("showOthers").checked)for(const b of boxes())if(b.det_id!==selected)rectangle(b.bbox_xyxy,"#b0c4d355",1);
  if($("showReference").checked&&current.reference.bbox_xyxy)rectangle(current.reference.bbox_xyxy,"#ffd43b",3,[10,5]);
  if(candidate())rectangle(candidate().bbox_xyxy,"#5ee7ff",4);
  if(e.reference.verdict==="corrected")rectangle(e.reference.bbox_xyxy,"#ff84d9",4);
  if(drag)rectangle([Math.min(drag.x,drag.toX),Math.min(drag.y,drag.toY),Math.max(drag.x,drag.toX),Math.max(drag.y,drag.toY)],"#ff84d9",3);
}
function point(event){const r=canvas.getBoundingClientRect();return {x:Math.max(0,Math.min(canvas.width,(event.clientX-r.left)*canvas.width/r.width)),y:Math.max(0,Math.min(canvas.height,(event.clientY-r.top)*canvas.height/r.height))};}
canvas.addEventListener("pointerdown",e=>{if(!image)return;const p=point(e);if(drawMode){drag={...p,toX:p.x,toY:p.y};canvas.setPointerCapture(e.pointerId);}else{const hits=boxes().filter(b=>p.x>=b.bbox_xyxy[0]&&p.x<=b.bbox_xyxy[2]&&p.y>=b.bbox_xyxy[1]&&p.y<=b.bbox_xyxy[3]).sort((a,b)=>(a.bbox_xyxy[2]-a.bbox_xyxy[0])*(a.bbox_xyxy[3]-a.bbox_xyxy[1])-(b.bbox_xyxy[2]-b.bbox_xyxy[0])*(b.bbox_xyxy[3]-b.bbox_xyxy[1]));if(hits.length){const n=hits.findIndex(b=>b.det_id===selected);selected=hits[(n+1)%hits.length].det_id;renderControls();paint();}}});
canvas.addEventListener("pointermove",e=>{if(drag){const p=point(e);drag.toX=p.x;drag.toY=p.y;paint();}});
canvas.addEventListener("pointerup",e=>{if(!drag)return;const p=point(e),box=[Math.round(Math.min(drag.x,p.x)),Math.round(Math.min(drag.y,p.y)),Math.round(Math.max(drag.x,p.x)),Math.round(Math.max(drag.y,p.y))];drag=null;if(box[2]-box[0]>=2&&box[3]-box[1]>=2){changed(v=>{v.presence="visible";v.reference={verdict:"corrected",bbox_xyxy:box,source:"manual",candidate:null};});drawMode=false;$("draw").classList.remove("active");canvas.classList.remove("drawing");}paint();});
canvas.addEventListener("pointercancel",()=>{drag=null;paint();});
$("draw").onclick=()=>{drawMode=!drawMode;$("draw").classList.toggle("active",drawMode);canvas.classList.toggle("drawing",drawMode);$("originalOnly").checked=false;paint();};
$("adopt").onclick=()=>{const c=candidate();if(c)changed(e=>{e.presence="visible";e.reference={verdict:"corrected",bbox_xyxy:clone(c.bbox_xyxy),source:"detector",candidate:{detector,det_id:c.det_id}};});};
$("referenceActions").onclick=event=>{const verdict=event.target.dataset.reference;if(!verdict)return;changed(e=>{e.reference={verdict,bbox_xyxy:verdict==="approved"?clone(current.reference.bbox_xyxy):null,source:verdict==="approved"?"original":"none",candidate:null};if(verdict==="approved")e.presence="visible";});};
$("detectorActions").onclick=event=>{const verdict=event.target.dataset.detector;if(!verdict)return;changed(e=>{e.detectors[detector]={verdict,candidate_id:["pending","absent"].includes(verdict)?null:selected};if(["sufficient","partial"].includes(verdict))e.presence="visible";});};
$("presence").onchange=()=>changed(e=>{e.presence=$("presence").value;if(e.presence!=="visible"){e.reference={verdict:e.presence==="absent"?"rejected":e.presence==="uncertain"?"uncertain":"pending",bbox_xyxy:null,source:"none",candidate:null};for(const [d,v] of Object.entries(e.detectors))if(["sufficient","partial"].includes(v.verdict))e.detectors[d]={verdict:"pending",candidate_id:null};}});
$("notes").oninput=()=>changed(e=>{e.notes=$("notes").value;});
$("candidate").onchange=()=>{selected=$("candidate").value===""?null:Number($("candidate").value);renderControls();paint();};
for(const id of ["showReference","showOthers","originalOnly"])$(id).onchange=paint;
$("zoom").onchange=setZoom;
window.addEventListener("resize",setZoom);
$("previous").onclick=()=>{if(position>0)showFrame(filtered[--position]);};
$("next").onclick=()=>{if(position<filtered.length-1)showFrame(filtered[++position]);};
$("saveNext").onclick=async()=>{if(saving){status("S’està desant; espera un moment");return;}const ok=await persist();if(!online||ok)$("next").click();};
for(const id of ["video","scope"])$(id).onchange=()=>applyFilter();
$("frameSearch").oninput=()=>applyFilter();
$("reviewer").onchange=()=>{state.reviewer=$("reviewer").value.trim()||"usuari";dirty++;localBackup();persist();};
function download(){const blob=new Blob([JSON.stringify(state,null,2)+"\n"],{type:"application/json"}),url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;a.download=`gymnast-review-${B.run_signature.slice(0,10)}-r${state.revision}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function validateImported(incoming){
  const known=new Map(B.frames.map(f=>[f.key,f]));
  for(const [key,e] of Object.entries(incoming.entries)){
    const f=known.get(key),r=e?.reference;
    if(!f||!e||typeof e!=="object"||!["pending","visible","absent","uncertain"].includes(e.presence)||typeof e.notes!=="string"||typeof e.updated_at!=="string"||!r||!e.detectors||typeof e.detectors!=="object"||Array.isArray(e.detectors))throw Error("Hi ha una decisió de fotograma incompleta o desconeguda");
    if(!["pending","approved","rejected","missing","corrected","uncertain"].includes(r.verdict)||!["original","manual","detector","none"].includes(r.source))throw Error("Veredicte d’anotació desconegut");
    if(r.bbox_xyxy!==null&&(!Array.isArray(r.bbox_xyxy)||r.bbox_xyxy.length!==4||r.bbox_xyxy.some(x=>typeof x!=="number"||!Number.isFinite(x))||!(0<=r.bbox_xyxy[0]&&r.bbox_xyxy[0]<r.bbox_xyxy[2]&&r.bbox_xyxy[2]<=f.width&&0<=r.bbox_xyxy[1]&&r.bbox_xyxy[1]<r.bbox_xyxy[3]&&r.bbox_xyxy[3]<=f.height)))throw Error("Caixa corregida fora de la imatge");
    if(["approved","corrected"].includes(r.verdict)&&(e.presence!=="visible"||r.bbox_xyxy===null))throw Error("L’anotació aprovada necessita un gimnasta visible i una caixa");
    if(r.verdict==="approved"&&(r.source!=="original"||JSON.stringify(r.bbox_xyxy)!==JSON.stringify(f.reference.bbox_xyxy)))throw Error("L’anotació aprovada és diferent de l’original");
    if(r.source==="detector"&&(!r.candidate||!f.variants[r.candidate.detector]?.boxes.some(c=>c.det_id===r.candidate.det_id&&JSON.stringify(c.bbox_xyxy)===JSON.stringify(r.bbox_xyxy))))throw Error("La candidata usada com anotació no existeix");
    for(const [d,v] of Object.entries(e.detectors)){
      if(!f.variants[d]||!v||!["pending","sufficient","partial","incorrect","absent"].includes(v.verdict))throw Error("Valoració de detector desconeguda");
      if(["sufficient","partial","incorrect"].includes(v.verdict)&&!f.variants[d].boxes.some(c=>c.det_id===v.candidate_id))throw Error("La candidata valorada no existeix");
      if(["sufficient","partial"].includes(v.verdict)&&e.presence!=="visible")throw Error("Una detecció útil necessita un gimnasta visible");
    }
  }
}
$("export").onclick=download;$("import").onclick=()=>$("importFile").click();
$("importFile").onchange=async()=>{try{const incoming=JSON.parse(await $("importFile").files[0].text());if(incoming.bundle_sha256!==INITIAL.bundle_sha256||incoming.run_signature!==B.run_signature||incoming.schema_version!=="1.0"||!incoming.entries||typeof incoming.entries!=="object")throw Error("El fitxer no correspon a aquesta prova");validateImported(incoming);if(!confirm("Importar les decisions? Les dels mateixos fotogrames substituiran les locals. La resta es conservarà."))return;state.entries={...state.entries,...incoming.entries};dirty++;localBackup();renderControls();$("notes").value=entry().notes;updateProgress();paint();await persist();}catch(e){message("No s’ha pogut importar: "+e.message);}finally{$("importFile").value="";}};
window.addEventListener("beforeunload",e=>{if(online&&dirty!==saved){e.preventDefault();e.returnValue="";}});
document.addEventListener("keydown",e=>{if(["INPUT","SELECT","TEXTAREA","BUTTON"].includes(document.activeElement.tagName))return;if(e.key==="ArrowRight")$("next").click();if(e.key==="ArrowLeft")$("previous").click();});
async function start(){
  for(const cid of new Set(B.frames.map(f=>f.case_id)))$("video").add(new Option(cid,cid));
  for(const [id,settings] of Object.entries(B.detectors)){const b=document.createElement("button");b.dataset.id=id;b.textContent=`YOLO ${settings.confidence} · ${B.roles[id]==="primary"?"principal":"control"}`;b.onclick=()=>{detector=id;showFrame(current);};$("variants").append(b);}
  let local=null;try{local=JSON.parse(localStorage.getItem(STORE));}catch(e){}
  if(location.protocol!=="file:")try{const response=await fetch("/api/state");if(response.ok){const server=await response.json();if(server.bundle_sha256===INITIAL.bundle_sha256){state=server;revision=server.revision;online=true;}}}catch(e){}
  if(online){
    status(`Desat al servidor · revisió ${revision}`);$("storageHelp").textContent="Cada canvi es desa automàticament a review-state.json del servidor. Exporta també una còpia quan acabis.";
    if(local?.bundle_sha256===INITIAL.bundle_sha256&&JSON.stringify(local.entries)!==JSON.stringify(state.entries))message("Hi ha una còpia local diferent de la del servidor. La còpia antiga es conserva com a còpia de recuperació al navegador; exporta-la des del botó que apareix a continuació si la necessites.");
  }else{
    if(local?.bundle_sha256===INITIAL.bundle_sha256)state=local;
    status("Mode navegador · exporta les decisions");$("storageHelp").textContent="Aquí els canvis només es desen en aquest navegador. Exporta el JSON i envia’l a l’agent; o obre la pàgina amb el servidor de revisió per desar al projecte.";
    message("Mode sense desat al servidor: fes «Exporta decisions» quan acabis. L’agent no pot llegir el localStorage del teu navegador.");
  }
  let recovery=null;
  try{
    if(online&&local?.bundle_sha256===INITIAL.bundle_sha256&&JSON.stringify(local.entries)!==JSON.stringify(state.entries))localStorage.setItem(STORE+":recovery",JSON.stringify(local));
    recovery=JSON.parse(localStorage.getItem(STORE+":recovery"));
  }catch(e){}
  if(recovery?.bundle_sha256===INITIAL.bundle_sha256){
    const recover=document.createElement("button");recover.textContent="Exporta còpia local de recuperació";recover.onclick=()=>{const active=state;state=recovery;download();state=active;};document.querySelector(".save-panel > div").append(recover);
  }
  $("reviewer").value=state.reviewer;let preferred;try{preferred=localStorage.getItem(CURSOR);}catch(e){}
  try{const nav=JSON.parse(localStorage.getItem(NAV));if(nav){for(const [id,value] of [["video",nav.video],["scope",nav.scope],["zoom",nav.zoom]])if([...$(id).options].some(o=>o.value===value))$(id).value=value;$("frameSearch").value=typeof nav.search==="string"?nav.search:"";if(B.detectors[nav.detector])detector=nav.detector;}}catch(e){}
  applyFilter(preferred);updateProgress();
}
start();
