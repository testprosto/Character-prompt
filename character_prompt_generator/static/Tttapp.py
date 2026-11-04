let selected = null;
let currentProfile = null;
const $ = id => document.getElementById(id);
const val = id => $(id).value.trim();
const set = (id, value) => $(id).value = Array.isArray(value) ? value.join(", ") : (value || "");
function toast(message){const t=$("toast");t.textContent=message;t.classList.add("show");setTimeout(()=>t.classList.remove("show"),2200)}
async function post(url, body){
  const r=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  const data=await r.json();if(!r.ok)throw new Error(data.error||"Request failed");return data;
}
$("searchBtn").onclick=async()=>{
  const name=val("name"),anime=val("anime");if(!name){toast("Введите имя персонажа");return}
  $("searchBtn").disabled=true;$("searchStatus").textContent="Ищу в AniList и Shikimori…";$("results").innerHTML="";
  try{
    const data=await post("/api/search",{name,anime});
    $("searchStatus").textContent=data.results.length?`Найдено вариантов: ${data.results.length}. Выбери правильного персонажа.`:"Ничего не найдено. Попробуй другое написание.";
    if(data.warnings?.length)$("searchStatus").textContent+=" Предупреждения: "+data.warnings.join(" | ");
    data.results.forEach((item,i)=>{
      const b=document.createElement("button");b.className="result-card";
      const img=document.createElement("img");img.src=item.image||"";img.alt="";
      const info=document.createElement("span");const title=document.createElement("b");title.textContent=item.name;
      const small=document.createElement("small");small.textContent=item.source+" · "+(item.anime||anime||"Anime character");
      info.append(title,small);b.append(img,info);b.onclick=()=>selectCharacter(item,b);$("results").append(b);
    });
  }catch(e){$("searchStatus").textContent=e.message}
  finally{$("searchBtn").disabled=false}
};
function selectCharacter(item,button){
  selected=item;document.querySelectorAll(".result-card").forEach(x=>x.classList.remove("selected"));button.classList.add("selected");
  $("workspace").classList.remove("hidden");$("characterImage").src=item.image||"";$("characterName").textContent=item.name;
  $("characterAnime").textContent=item.anime||val("anime")||"Произведение не определено";
  $("characterLink").href=item.url||"#";$("sourceLabel").textContent=item.source.toUpperCase();
  $("analysisStatus").textContent="Персонаж выбран. Нажми «Собрать данные и теги».";
  $("workspace").scrollIntoView({behavior:"smooth",block:"start"});
}
$("analyzeBtn").onclick=async()=>{
  if(!selected)return;
  $("analyzeBtn").disabled=true;$("analysisStatus").textContent="Запрашиваю Danbooru, собираю safe-rated изображения и теги…";
  try{
    const p=await post("/api/analyze",{character:selected});currentProfile=p;fillProfile(p);
    $("analysisStatus").textContent=p.booru?.posts?.length?`Получено изображений: ${p.booru.posts.length}. Проверь признаки — теги могут быть неточными.`:"Профиль создан, но изображения/теги Danbooru не найдены. Заполни поля вручную.";
    renderGallery(p.booru?.posts||[], p.mudae?.images||[]);renderPrompts();
  }catch(e){$("analysisStatus").textContent=e.message}
  finally{$("analyzeBtn").disabled=false}
};
function fillProfile(p){
  set("appearance",p.appearance);set("skin",p.colors?.skin);set("hair",p.colors?.hair);set("eyes",p.colors?.eyes);
  set("clothing",p.clothing);set("accessories",p.accessories);set("traits",p.special_traits);
  set("personality",p.personality);set("abilities",p.abilities);set("history",p.history);
}
function renderGallery(posts, mudaeImages=[]){
  $("gallery").innerHTML="";
  posts.forEach(p=>{
    const a=document.createElement("a");a.href=p.image;a.target="_blank";a.rel="noopener";
    const img=document.createElement("img");img.src=p.preview||p.image;img.loading="lazy";
    const tags=document.createElement("div");tags.className="tags";tags.textContent=(p.tags||"").split(" ").slice(0,12).join(", ");
    a.append(img,tags);$("gallery").append(a);
  });
  mudaeImages.forEach(url=>{
    const a=document.createElement("a");a.href=url;a.target="_blank";a.rel="noopener";
    const img=document.createElement("img");img.src=url;img.loading="lazy";
    const tags=document.createElement("div");tags.className="tags";tags.textContent="Mudae reference";
    a.append(img,tags);$("gallery").append(a);
  });
}
function collectProfile(){
  return {character:selected||{name:val("name"),anime:val("anime")},appearance:val("appearance").split(",").map(x=>x.trim()).filter(Boolean),
    colors:{skin:val("skin").split(",").map(x=>x.trim()).filter(Boolean),hair:val("hair").split(",").map(x=>x.trim()).filter(Boolean),eyes:val("eyes").split(",").map(x=>x.trim()).filter(Boolean)},
    clothing:val("clothing").split(",").map(x=>x.trim()).filter(Boolean),accessories:val("accessories").split(",").map(x=>x.trim()).filter(Boolean),
    special_traits:val("traits").split(",").map(x=>x.trim()).filter(Boolean),personality:val("personality"),abilities:val("abilities"),history:val("history")};
}
function renderPrompts(){
  const p=collectProfile();const tags=[p.character.name,p.character.anime,...p.appearance,...p.colors.skin,...p.colors.hair,...p.colors.eyes,...p.clothing,...p.accessories,...p.special_traits].filter(Boolean);
  $("positive").value=[...new Set(tags)].join(", ");
  $("negative").value="low quality, worst quality, lowres, blurry, bad anatomy, bad hands, extra fingers, missing fingers, deformed, mutated, poorly drawn face, text, watermark, logo";
}
$("regenerateBtn").onclick=()=>{renderPrompts();toast("Промпты обновлены")};
["appearance","skin","hair","eyes","clothing","accessories","traits"].forEach(id=>$(id).addEventListener("input",renderPrompts));
document.querySelectorAll("[data-copy]").forEach(b=>b.onclick=async()=>{await navigator.clipboard.writeText($(b.dataset.copy).value);toast("Скопировано в буфер обмена")});
$("exportBtn").onclick=()=>{
  const data={...collectProfile(),prompts:{positive:$("positive").value,negative:$("negative").value},references:currentProfile?.booru?.posts||[]};
  const blob=new Blob([JSON.stringify(data,null,2)],{type:"application/json"});const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=(selected?.name||"character").replace(/[^a-z0-9_-]/gi,"_")+".json";a.click();URL.revokeObjectURL(a.href);
};
