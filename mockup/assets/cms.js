/* CMS chuyên gia biên soạn (mockup, data giả trong bộ nhớ).
   (1) Nhập/sửa MỤC LỤC theo cấu trúc file ma trận (Mạch → Đơn vị kiến thức).
   (2) Tải file SÁCH rồi dùng AI nạp nội dung tự động.
   (3) Chỉnh sửa nội dung 4 phần (Khái niệm/Minh họa/Ví dụ) + hướng dẫn dạy.
   Bài kiểm tra nhanh: KHÓA (sinh theo ma trận). Preview mở LessonView với data đang soạn. */
(function(){
"use strict";
var $=function(s,r){return (r||document).querySelector(s);};

var _id=0; function uid(){return "u"+(++_id);}
// TOC editable = bản sao từ CURRICULUM (đã bám TOAN_6_HK1.docx), gắn id ổn định.
var toc=CURRICULUM.map(function(m){
  return {mach:m.mach, em:m.em, dv:m.dv.map(function(d){return {t:d.t, st:d.st, prime:d.prime, id:uid()};})};
});
var STORE={}, mode="struct", cur={mi:0,di:0};

function seedContent(mach,t,prime){ return prime?lessonPrime(mach,t):lessonGeneric(mach,t); }
function stripHtml(h){ return (h||"").replace(/<\/p>\s*<p>/g,"\n\n").replace(/<br\s*\/?>/g,"\n").replace(/<[^>]+>/g,"").trim(); }
function getDoc(dv,mach){
  if(!STORE[dv.id]){
    var L=seedContent(mach,dv.t,dv.prime);
    STORE[dv.id]={
      khai_niem:stripHtml(L.khai_niem),
      minh_hoa:L.minh_hoa.map(function(m){return {type:(m.type==="video"?"video":"image"),url:m.url||"",caption:m.caption||""};}),
      vi_du:L.vi_du.map(function(e){return {de:e.de,giai:e.giai};}),
      day:L.day?JSON.parse(JSON.stringify(L.day)):{muc_tieu:"",thoi_luong:"",luu_y:"",goi_y:{}},
      status:"nhap", ai:false
    };
  }
  return STORE[dv.id];
}
function completeness(d){
  var parts=[!!(d.khai_niem&&d.khai_niem.trim()), d.minh_hoa.length>0, d.vi_du.length>0, true];
  var names=["Khái niệm","Minh họa","Ví dụ","Kiểm tra"];
  return {done:parts.filter(Boolean).length,total:4,miss:names.filter(function(_,i){return !parts[i];})};
}
function docToLesson(mach,dv,d){
  return {
    mach:mach, dv:dv.t,
    khai_niem:(d.khai_niem||"").split(/\n{2,}/).map(function(p){return "<p>"+p.replace(/\n/g,"<br>")+"</p>";}).join(""),
    minh_hoa:d.minh_hoa, vi_du:d.vi_du.map(function(e){return {de:e.de,giai:e.giai};}),
    quiz:seedContent(mach,dv.t,dv.prime).quiz, day:d.day
  };
}
function toast(msg){var t=$("#toast");t.textContent=msg;t.classList.add("show");clearTimeout(toast._t);toast._t=setTimeout(function(){t.classList.remove("show");},2000);}

/* ---- helpers form ---- */
function field(label,node){var f=el("div","field");f.appendChild(el("label",null,label));f.appendChild(node);return f;}
function input(val,ph){var i=el("input");i.value=val||"";if(ph)i.placeholder=ph;return i;}
function textarea(val,ph){var t=el("textarea");t.value=val||"";if(ph)t.placeholder=ph;return t;}

/* ---- Sidebar mục lục (chọn đơn vị để biên soạn) ---- */
function renderToc(){
  var box=$("#toc"); box.innerHTML="";
  toc.forEach(function(m,mi){
    var wrap=el("div","mach"+(mi===cur.mi?" open":""));
    var b=el("button","mach-b",'<span class="mach-em">'+(m.em||"📘")+'</span> '+m.mach+'<span class="chev">›</span>');
    b.onclick=function(){wrap.classList.toggle("open");};
    var list=el("div","dv-list");
    m.dv.forEach(function(d,di){
      var c=completeness(getDoc(d,m.mach));
      var active=(mi===cur.mi&&di===cur.di);
      var db=el("button","dv-b"+(active?" active":""),
        d.t+'<span class="frac'+(c.done===c.total?" full":"")+'">'+c.done+'/'+c.total+'</span>');
      db.onclick=function(){cur={mi:mi,di:di};mode="edit";render();};
      list.appendChild(db);
    });
    wrap.appendChild(b);wrap.appendChild(list);box.appendChild(wrap);
  });
}

function renderTabs(){
  var t=$("#tabs"); t.innerHTML="";
  [["struct","📚 Cấu trúc & Nạp sách"],["edit","✍️ Biên soạn nội dung"]].forEach(function(d){
    var b=el("button","tab",d[1]); b.setAttribute("aria-selected",mode===d[0]);
    b.onclick=function(){mode=d[0];render();}; t.appendChild(b);
  });
}

/* ============ TAB 1: Cấu trúc & Nạp sách ============ */
function renderStruct(){
  var v=$("#editor"); v.innerHTML="";
  v.appendChild(el("div",null,'<div class="crumb">Chuyên gia · <b>Cấu trúc chương trình & nguồn</b></div><h1 class="lesson-title">Mục lục & Nạp sách</h1>'));

  /* --- A. Nhập mục lục theo file ma trận --- */
  var sA=el("section","sec"); sA.appendChild(el("div","sec-h",'<span>🗂️</span> Mục lục (theo cấu trúc file ma trận)'));
  var bA=el("div","sec-b");
  var imp=el("div","cms-actions");
  var bImport=el("button","btn accent","📄 Nhập từ file ma trận (.docx)");
  bImport.onclick=function(){ toast("Đã đọc TOAN_6_HK1.docx → 4 mạch nội dung. (mock)"); };
  imp.appendChild(bImport);
  imp.appendChild(el("span","mini","Cấu trúc: Mạch nội dung → Đơn vị kiến thức — đúng như file Word."));
  bA.appendChild(imp);

  var tocBox=el("div"); tocBox.style.marginTop="12px";
  function drawToc(){
    tocBox.innerHTML="";
    toc.forEach(function(m,mi){
      var card=el("div","item");
      var h=el("div","item-h");
      var emo=input(m.em); emo.style.maxWidth="50px"; emo.oninput=function(){m.em=emo.value;};
      var nm=input(m.mach,"Tên mạch nội dung"); nm.oninput=function(){m.mach=nm.value;}; nm.onchange=renderToc;
      var rm=el("button","rm","Xoá mạch"); rm.onclick=function(){toc.splice(mi,1);if(cur.mi>=toc.length)cur.mi=0;drawToc();renderToc();};
      h.appendChild(el("span","t","Mạch "+(mi+1))); h.appendChild(rm);
      card.appendChild(h);
      var r=el("div","row"); r.appendChild(emo); var g=el("div");g.style.flex="4";g.appendChild(nm); r.appendChild(g);
      card.appendChild(r);
      var dvl=el("div"); dvl.style.marginTop="8px";
      m.dv.forEach(function(d,di){
        var row=el("div","row"); row.style.marginBottom="6px";
        var ti=input(d.t,"Đơn vị kiến thức"); ti.oninput=function(){d.t=ti.value;}; ti.onchange=renderToc;
        var x=el("button","rm","×"); x.style.flex="none"; x.onclick=function(){m.dv.splice(di,1);drawToc();renderToc();};
        var wrap=el("div");wrap.style.flex="1";wrap.appendChild(ti);
        row.appendChild(wrap); row.appendChild(x); dvl.appendChild(row);
      });
      var add=el("button","add-btn","＋ Thêm đơn vị kiến thức");
      add.onclick=function(){m.dv.push({t:"",st:"chua",id:uid()});drawToc();renderToc();};
      card.appendChild(dvl); card.appendChild(add);
      tocBox.appendChild(card);
    });
    var addM=el("button","add-btn","＋ Thêm mạch nội dung"); addM.style.marginTop="4px";
    addM.onclick=function(){toc.push({mach:"",em:"📘",dv:[]});drawToc();renderToc();};
    tocBox.appendChild(addM);
  }
  drawToc();
  bA.appendChild(tocBox); sA.appendChild(bA); v.appendChild(sA);

  /* --- B. Nạp sách bằng AI --- */
  var sB=el("section","sec"); sB.appendChild(el("div","sec-h",'<span>🤖</span> Nạp sách bằng AI'));
  var bB=el("div","sec-b");
  var files=[];
  var dz=el("div","dropzone","⬆️ Tải file sách nguồn (PDF / DOCX / ảnh trang) — có thể nhiều nguồn");
  var fileList=el("div");
  function drawFiles(){
    fileList.innerHTML="";
    files.forEach(function(f,i){
      var it=el("div","item"); var h=el("div","item-h");
      h.innerHTML='<span class="t">📄 '+f+"</span>";
      var rm=el("button","rm","Xoá");rm.onclick=function(){files.splice(i,1);drawFiles();};
      h.appendChild(rm); it.appendChild(h); fileList.appendChild(it);
    });
  }
  var n=0;
  dz.onclick=function(){ n++; files.push("SGK_Toan6_nguon_"+n+".pdf"); drawFiles(); toast("Đã thêm file nguồn (mock)"); };

  var target=el("select");
  function fillTargets(){
    target.innerHTML="";
    var oAll=el("option",null,"Tất cả đơn vị kiến thức");oAll.value="all";target.appendChild(oAll);
    toc.forEach(function(m,mi){m.dv.forEach(function(d,di){var o=el("option",null,m.mach+" › "+(d.t||"(chưa đặt tên)"));o.value=mi+"_"+di;target.appendChild(o);});});
  }
  fillTargets();
  var run=el("button","btn accent","🤖 Nạp bằng AI");
  var resultBox=el("div"); resultBox.style.marginTop="10px";
  run.onclick=function(){
    if(!files.length){toast("Hãy tải ít nhất 1 file sách trước.");return;}
    run.disabled=true; run.textContent="⏳ Đang phân tích sách…";
    setTimeout(function(){
      var targets=[];
      if(target.value==="all"){toc.forEach(function(m,mi){m.dv.forEach(function(d,di){targets.push([mi,di]);});});}
      else{var p=target.value.split("_");targets.push([+p[0],+p[1]]);}
      var filled=0;
      targets.forEach(function(t){
        var m=toc[t[0]],d=m.dv[t[1]]; if(!d)return;
        var doc=getDoc(d,m.mach);
        var ex=aiExtract(m.mach,d.t||"đơn vị");
        doc.khai_niem=ex.khai_niem; doc.vi_du=ex.vi_du; doc.ai=true; filled++;
      });
      run.disabled=false; run.textContent="🤖 Nạp bằng AI";
      resultBox.innerHTML='<div class="locked-card"><span class="lk">✅</span><div><b>AI đã nạp xong.</b><br><span class="mini">Trích &amp; gán nội dung Khái niệm + Ví dụ cho '+filled+' đơn vị từ '+files.length+' file nguồn. Chuyên gia rà soát &amp; chỉnh ở tab “Biên soạn”.</span></div></div>';
      renderToc(); toast("AI đã nạp nội dung cho "+filled+" đơn vị");
    },1200);
  };
  bB.appendChild(dz); bB.appendChild(fileList);
  bB.appendChild(field("Nạp vào",target));
  var actB=el("div","cms-actions"); actB.appendChild(run); bB.appendChild(actB);
  bB.appendChild(resultBox);
  sB.appendChild(bB); v.appendChild(sB);

  v.appendChild(el("div","foot","CMS mockup · dữ liệu giả trong bộ nhớ — tải lại trang sẽ về mẫu ban đầu."));
}

// Nội dung "AI trích" giả lập
function aiExtract(mach,t){
  return {
    khai_niem:"（AI trích từ sách nguồn đã tải）\n\nKhái niệm về “"+t+"”: định nghĩa ngắn gọn, đúng chuẩn chương trình, do AI tổng hợp từ tài liệu. Chuyên gia rà soát lại trước khi duyệt.",
    vi_du:[
      {de:"（AI）Ví dụ mẫu cho “"+t+"”.",giai:"（AI）Lời giải từng bước do AI đề xuất."},
      {de:"（AI）Ví dụ vận dụng.",giai:"（AI）Hướng dẫn giải."}
    ]
  };
}

/* ============ TAB 2: Biên soạn nội dung ============ */
function renderEdit(){
  var m=toc[cur.mi]; if(!m){cur={mi:0,di:0};m=toc[0];}
  var dv=m.dv[cur.di]; if(!dv){ if(m.dv.length===0){emptyEdit();return;} cur.di=0; dv=m.dv[0]; }
  var d=getDoc(dv,m.mach);
  var v=$("#editor"); v.innerHTML="";

  var head=el("div","cms-head");
  var left=el("div","grow");
  left.innerHTML='<div class="crumb">'+m.mach+' › <b>Đơn vị kiến thức</b>'+(d.ai?' · <span style="color:var(--warn)">✨ có nội dung AI</span>':'')+'</div><h1 class="lesson-title">'+(dv.t||"(chưa đặt tên)")+'</h1>';
  var cmpl=el("div","cmpl"); left.appendChild(cmpl);
  var actions=el("div","cms-actions");
  var sel=el("select","status-sel");
  [["nhap","● Nháp"],["duyet","● Chờ duyệt"],["xong","● Đã duyệt"]].forEach(function(o){var op=el("option",null,o[1]);op.value=o[0];if(d.status===o[0])op.selected=true;sel.appendChild(op);});
  sel.onchange=function(){d.status=sel.value;toast("Trạng thái: "+sel.options[sel.selectedIndex].text.replace("● ",""));};
  var bHS=el("button","btn","👁 Xem như học sinh"); bHS.onclick=function(){preview(false);};
  var bGV=el("button","btn","🎓 Xem như giáo viên"); bGV.onclick=function(){preview(true);};
  var bSave=el("button","btn accent","💾 Lưu"); bSave.onclick=function(){toast("Đã lưu (mock)");renderToc();};
  [sel,bHS,bGV,bSave].forEach(function(x){actions.appendChild(x);});
  head.appendChild(left);head.appendChild(actions); v.appendChild(head);

  function refreshCmpl(){var c=completeness(d);
    cmpl.innerHTML='<div class="bar-track"><div class="bar-fill" style="width:'+Math.round(100*c.done/c.total)+'%"></div></div><span class="tnum" style="font-weight:700">'+c.done+'/'+c.total+'</span>'+(c.miss.length?'<span class="miss">Thiếu: '+c.miss.join(", ")+'</span>':'<span class="ok">✓ Đủ 4 phần</span>');}
  refreshCmpl();

  // 1. Khái niệm — CHỈNH SỬA ĐƯỢC + gợi ý AI
  var s1=el("section","sec"); s1.appendChild(el("div","sec-h",'<span class="sec-n">1</span><span>📖</span> Khái niệm, định nghĩa'));
  var b1=el("div","sec-b");
  var ta=textarea(d.khai_niem,"Nhập/sửa khái niệm (thuần văn bản; xuống dòng đúp để tách đoạn)…");
  var cc=el("div","charc",d.khai_niem.length+" ký tự");
  ta.oninput=function(){d.khai_niem=ta.value;cc.textContent=ta.value.length+" ký tự";refreshCmpl();renderToc();};
  var aiBtn=el("button","btn","🤖 Gợi ý bằng AI");
  aiBtn.onclick=function(){var ex=aiExtract(m.mach,dv.t||"đơn vị");d.khai_niem=ex.khai_niem;ta.value=ex.khai_niem;cc.textContent=ex.khai_niem.length+" ký tự";d.ai=true;refreshCmpl();renderToc();toast("AI đã gợi ý nội dung khái niệm");};
  b1.appendChild(field("Nội dung (chỉnh sửa)",ta));
  var r1=el("div","cms-actions"); r1.appendChild(aiBtn); r1.appendChild(cc); b1.appendChild(r1);
  s1.appendChild(b1); v.appendChild(s1);

  // 2. Minh hoạ
  var s2=el("section","sec"); s2.appendChild(el("div","sec-h",'<span class="sec-n">2</span><span>🎬</span> Minh họa'));
  var b2=el("div","sec-b");
  var dz=el("div","dropzone","⬆️ Kéo-thả hoặc bấm để tải ảnh / video minh hoạ");
  var mediaList=el("div");
  function drawMedia(){
    mediaList.innerHTML="";
    d.minh_hoa.forEach(function(mm,i){
      var it=el("div","item"); var h=el("div","item-h");
      h.innerHTML='<span class="t">'+(mm.type==="video"?"🎬 Video":"🖼️ Hình ảnh")+" "+(i+1)+"</span>";
      var rm=el("button","rm","Xoá");rm.onclick=function(){d.minh_hoa.splice(i,1);drawMedia();refreshCmpl();renderToc();};
      h.appendChild(rm); it.appendChild(h);
      var row=el("div","row");
      var ts=el("select");["image","video"].forEach(function(x){var o=el("option",null,x==="image"?"Hình ảnh":"Video");o.value=x;if(mm.type===x)o.selected=true;ts.appendChild(o);});
      ts.onchange=function(){mm.type=ts.value;drawMedia();};
      var url=input(mm.url,"URL/đường dẫn file"); url.oninput=function(){mm.url=url.value;};
      row.appendChild(ts);row.appendChild(url); it.appendChild(row);
      var cap=input(mm.caption,"Chú thích"); cap.oninput=function(){mm.caption=cap.value;};
      it.appendChild(field("Chú thích",cap)); mediaList.appendChild(it);
    });
  }
  dz.onclick=function(){d.minh_hoa.push({type:"image",url:"",caption:"Ảnh mới tải lên"});drawMedia();refreshCmpl();renderToc();toast("Đã thêm ảnh (mock)");};
  drawMedia(); b2.appendChild(dz); b2.appendChild(mediaList); s2.appendChild(b2); v.appendChild(s2);

  // 3. Ví dụ
  var s3=el("section","sec"); s3.appendChild(el("div","sec-h",'<span class="sec-n">3</span><span>✏️</span> Ví dụ'));
  var b3=el("div","sec-b"); var vdList=el("div");
  function drawVd(){
    vdList.innerHTML="";
    d.vi_du.forEach(function(e,i){
      var it=el("div","item"); var h=el("div","item-h");
      h.innerHTML='<span class="t">Ví dụ '+(i+1)+"</span>";
      var rm=el("button","rm","Xoá");rm.onclick=function(){d.vi_du.splice(i,1);drawVd();refreshCmpl();renderToc();};
      h.appendChild(rm); it.appendChild(h);
      var de=textarea(e.de,"Đề bài"); de.oninput=function(){e.de=de.value;};
      var gi=textarea(e.giai,"Lời giải"); gi.oninput=function(){e.giai=gi.value;};
      it.appendChild(field("Đề bài",de)); it.appendChild(field("Lời giải",gi)); vdList.appendChild(it);
    });
  }
  drawVd();
  var addVd=el("button","add-btn","＋ Thêm ví dụ"); addVd.onclick=function(){d.vi_du.push({de:"",giai:""});drawVd();refreshCmpl();renderToc();};
  b3.appendChild(vdList); b3.appendChild(addVd); s3.appendChild(b3); v.appendChild(s3);

  // 4. Kiểm tra nhanh (khoá)
  var s4=el("section","sec"); s4.appendChild(el("div","sec-h",'<span class="sec-n">4</span><span>✅</span> Bài kiểm tra nhanh'));
  var b4=el("div","sec-b");
  b4.appendChild(el("div","locked-card",'<span class="lk">🔒</span><div><b>Sinh tự động theo ma trận đặc tả.</b><br><span class="mini">Bám yêu cầu cần đạt + mức độ của đơn vị — không nhập tay.</span></div>'));
  s4.appendChild(b4); v.appendChild(s4);

  // 5. Hướng dẫn giảng dạy
  var s5=el("section","sec"); s5.appendChild(el("div","sec-h",'<span class="sec-n">🎓</span> Hướng dẫn giảng dạy (cho giáo viên)'));
  var b5=el("div","sec-b");
  var mt=textarea(d.day.muc_tieu,"Mục tiêu bài học"); mt.oninput=function(){d.day.muc_tieu=mt.value;};
  var tl=input(d.day.thoi_luong,"vd: 1 tiết · ~45 phút"); tl.oninput=function(){d.day.thoi_luong=tl.value;};
  var lu=textarea(d.day.luu_y,"Lỗi thường gặp / lưu ý khi dạy"); lu.oninput=function(){d.day.luu_y=lu.value;};
  b5.appendChild(field("Mục tiêu",mt)); b5.appendChild(field("Thời lượng",tl)); b5.appendChild(field("Lưu ý",lu));
  s5.appendChild(b5); v.appendChild(s5);

  v.appendChild(el("div","foot","Chọn đơn vị khác ở mục lục bên trái · tab “Cấu trúc & Nạp sách” để sửa mục lục hoặc nạp AI."));
}
function emptyEdit(){
  var v=$("#editor"); v.innerHTML="";
  v.appendChild(el("div","locked-card",'<span class="lk">📄</span><div>Mạch này chưa có đơn vị kiến thức. Sang tab <b>📚 Cấu trúc & Nạp sách</b> để thêm.</div>'));
}

/* ---- Preview ---- */
function preview(teacher){
  var m=toc[cur.mi], dv=m.dv[cur.di]; if(!dv)return;
  var d=getDoc(dv,m.mach);
  var ov=el("div","cms-preview");
  var bar=el("div","pv-bar"); bar.innerHTML='<span class="t">👁 Xem trước — '+(teacher?"Giáo viên":"Học sinh")+'</span>';
  var sp=el("div");sp.style.flex="1";bar.appendChild(sp);
  var close=el("button","btn","✕ Đóng"); bar.appendChild(close); ov.appendChild(bar);
  var sc=el("div","scroll"),wrap=el("div","wrap"); sc.appendChild(wrap); ov.appendChild(sc);
  document.body.appendChild(ov);
  renderLessonObj(wrap, docToLesson(m.mach,dv,d), teacher);
  close.onclick=function(){ov.remove();};
}

/* ---- render dispatcher ---- */
function render(){ renderToc(); renderTabs(); if(mode==="struct")renderStruct(); else renderEdit(); }

initTheme($("#theme"));
render();
})();
