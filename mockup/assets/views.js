/* Các view render vào 1 phần tử gốc (root). Dùng chung cho trang tổng hợp
   (index.html) lẫn các trang lẻ (bai-hoc / tien-do / slide-gv). */

function section(n,title,icon,body){
  var s=el("section","sec");
  s.appendChild(el("div","sec-h",'<span class="sec-n">'+n+'</span><span>'+icon+'</span> '+title));
  var b=el("div","sec-b"); if(typeof body==="string")b.innerHTML=body; else b.appendChild(body);
  s.appendChild(b); return s;
}

function quizNode(items, onRetry){
  var wrap=el("div"); var ans={}; var done=false;
  items.forEach(function(q,qi){
    var box=el("div","q");
    box.appendChild(el("div","q-cau","Câu "+(qi+1)+". "+q.q+'<span class="lv '+q.lv+'">'+({de:"Dễ",trung_binh:"TB",kho:"Khó"})[q.lv]+"</span>"));
    var opts=el("div","opts");
    q.o.forEach(function(op,oi){
      var b=el("button","opt",'<span class="k">'+String.fromCharCode(65+oi)+"</span> "+op);
      b.onclick=function(){ if(done)return; ans[qi]=oi;
        Array.prototype.forEach.call(opts.children,function(c,ci){c.classList.toggle("picked",ci===oi);});
        submit.disabled=Object.keys(ans).length<items.length; };
      opts.appendChild(b);
    });
    box.appendChild(opts); wrap.appendChild(box);
  });
  var submit=el("button","btn accent","Nộp bài"); submit.disabled=true;
  var res=el("div","result");
  submit.onclick=function(){
    done=true; var sc=0;
    Array.prototype.forEach.call(wrap.querySelectorAll(".q"),function(qb,qi){
      qb.querySelectorAll(".opt").forEach(function(o,oi){
        o.disabled=true;
        if(oi===items[qi].a)o.classList.add("correct");
        if(ans[qi]===oi&&oi!==items[qi].a)o.classList.add("wrong");
      });
      if(ans[qi]===items[qi].a)sc++;
    });
    submit.style.display="none";
    res.innerHTML="Kết quả: <b>&nbsp;"+sc+"/"+items.length+"</b> câu đúng";
    var again=el("button","btn","Làm lại"); again.onclick=function(){ if(onRetry)onRetry(); };
    res.appendChild(again);
  };
  wrap.appendChild(submit); wrap.appendChild(res);
  wrap.appendChild(el("div","gen-note","※ Ở bản thật, bộ câu hỏi được sinh tự động theo ma trận đặc tả (yêu cầu cần đạt + mức độ)."));
  return wrap;
}

function teachNote(sec,text){
  if(!text)return sec;
  var b=sec.querySelector(".sec-b");
  b.appendChild(el("div","teach",'<span class="teach-tag">🎓 Cách dạy</span> '+text));
  return sec;
}

function renderLesson(root,mi,di,teacher){
  renderLessonObj(root,lessonFor(mi,di),teacher);
}
// Render bài học từ 1 OBJECT nội dung — dùng cho preview CMS (data đang soạn).
function renderLessonObj(root,L,teacher){
  root.innerHTML="";
  root.appendChild(el("div",null,'<div class="crumb">'+L.mach+' › <b>Đơn vị kiến thức</b></div><h1 class="lesson-title">'+L.dv+"</h1>"));
  var chips='<span class="chip">Bám ma trận đặc tả</span><span class="chip">4 phần cố định</span><span class="chip">Không trích dẫn số trang</span>';
  if(teacher)chips+='<span class="chip">🎓 Chế độ giáo viên</span>';
  root.appendChild(el("div","note",chips));

  // Giáo viên: khối HƯỚNG DẪN GIẢNG DẠY tổng quan trước khi vào 4 phần.
  if(teacher&&L.day){
    var g=el("div","guide");
    g.innerHTML='<div class="guide-h">🎓 Hướng dẫn giảng dạy</div>'
      +'<div class="guide-grid">'
      +'<div><span class="guide-l">Mục tiêu</span>'+L.day.muc_tieu+'</div>'
      +'<div><span class="guide-l">Thời lượng</span>'+L.day.thoi_luong+'</div>'
      +'<div><span class="guide-l">Lưu ý</span>'+L.day.luu_y+'</div>'
      +'</div>';
    root.appendChild(g);
  }
  var gy=(teacher&&L.day)?L.day.goi_y:{};

  root.appendChild(teachNote(section(1,"Khái niệm, định nghĩa","📖","<div>"+L.khai_niem+"</div>"),gy.khai_niem));

  var media=el("div","media");
  L.minh_hoa.forEach(function(m){
    var fig=el("figure");
    if(m.type==="sieve")fig.innerHTML=sieveSVG();
    else if(m.type==="video")fig.innerHTML='<div class="vid"><div class="play">▶</div><div>Video minh hoạ</div></div>';
    else fig.innerHTML='<div class="vid"><div style="font-size:30px">🖼️</div><div>Hình ảnh minh hoạ</div></div>';
    fig.appendChild(el("figcaption",null,m.caption)); media.appendChild(fig);
  });
  root.appendChild(teachNote(section(2,"Minh họa","🎬",media),gy.minh_hoa));

  var vd=el("div");
  L.vi_du.forEach(function(e,i){
    var box=el("div","vd");
    box.innerHTML='<div class="vd-h">Ví dụ '+(i+1)+'</div><div>'+e.de+'</div><button class="link">Xem lời giải</button><div class="vd-giai">'+e.giai+"</div>";
    box.querySelector(".link").onclick=function(){
      box.classList.toggle("open");
      box.querySelector(".link").textContent=box.classList.contains("open")?"Ẩn lời giải":"Xem lời giải";
    };
    vd.appendChild(box);
  });
  root.appendChild(teachNote(section(3,"Ví dụ","✏️",vd),gy.vi_du));

  root.appendChild(teachNote(section(4,"Bài kiểm tra nhanh","✅",quizNode(L.quiz,function(){renderLessonObj(root,L,teacher);})),gy.kiem_tra));
}

function renderProgress(root){
  root.innerHTML="";
  var all=PROGRESS.reduce(function(a,m){return a.concat(m.ycd);},[]);
  var overall=pct(all),
      dat=all.filter(function(x){return x.st==="dat";}).length,
      dang=all.filter(function(x){return x.st==="dang";}).length;
  root.appendChild(el("div",null,'<div class="crumb">Học sinh · <b>Nguyễn Minh An</b></div><h1 class="lesson-title">Tiến độ học tập</h1>'));
  var cards=el("div","pcards");
  var ring=el("div","pcard"); ring.style.cssText="display:flex;align-items:center;gap:14px";
  ring.innerHTML='<div class="ring" style="--p:'+overall+'"><span>'+overall+'%</span></div><div><div class="l" style="margin:0">Hoàn thành</div><div class="v tnum" style="font-size:20px">'+dat+"/"+all.length+'</div><div class="l">yêu cầu cần đạt</div></div>';
  cards.appendChild(ring);
  cards.appendChild(pcardEl(dang,"Đang học"));
  cards.appendChild(pcardEl(all.length-dat-dang,"Chưa bắt đầu"));
  root.appendChild(cards);
  PROGRESS.forEach(function(m){
    var p=pct(m.ycd),box=el("div","pmach");
    var h=el("div","pmach-h");
    h.innerHTML='<div class="tt" style="min-width:130px">'+m.mach+'</div><div class="bar-track"><div class="bar-fill" style="width:'+p+'%"></div></div><div class="tnum" style="font-weight:700;width:44px;text-align:right">'+p+"%</div>";
    box.appendChild(h);
    var yc=el("div","ycd");
    m.ycd.forEach(function(x){var r=el("div","ycd-row");r.innerHTML='<span class="badge '+ST[x.st][1]+'">'+ST[x.st][2]+"</span><span>"+x.t+"</span>";yc.appendChild(r);});
    box.appendChild(yc); root.appendChild(box);
  });
}
function pcardEl(v,l){var c=el("div","pcard");c.innerHTML='<div class="v tnum">'+v+'</div><div class="l">'+l+"</div>";return c;}

function renderSlides(root,mi,di){
  var L=lessonFor(mi,di); root.innerHTML="";
  var slides=[{cover:true,kicker:L.mach,h:L.dv,body:"Bài giảng tạo tự động từ nội dung đã nhập · Gia sư DTP"}];
  slides.push({kicker:"Khái niệm",h:"Khái niệm & định nghĩa",html:L.khai_niem});
  L.minh_hoa.forEach(function(m,i){slides.push({kicker:"Minh hoạ",h:"Minh hoạ "+(i+1),media:m});});
  slides.push({kicker:"Ví dụ",h:"Ví dụ minh hoạ",list:L.vi_du.map(function(e){return e.de;})});
  var idx=0;
  root.appendChild(el("div",null,'<div class="crumb">Giáo viên · <b>Render slide</b></div><h1 class="lesson-title">'+L.dv+'</h1><div class="note" style="margin-top:8px"><span class="chip">Sinh từ data đã input</span><span class="chip">'+slides.length+' slide</span></div>'));
  var deck=el("div","deck"),stage=el("div"); deck.appendChild(stage);
  var bar=el("div","deck-bar");
  var prev=el("button","btn","‹ Trước"),next=el("button","btn accent","Sau ›"),count=el("div","count"),dots=el("div","dots");
  bar.appendChild(prev);bar.appendChild(next);bar.appendChild(count);bar.appendChild(dots);
  deck.appendChild(bar); root.appendChild(deck);
  function draw(){
    var s=slides[idx],inner='<div class="kicker">'+s.kicker+'</div><h2>'+s.h+"</h2>";
    if(s.cover)inner+='<div class="body">'+s.body+"</div>";
    else if(s.html)inner+='<div class="body">'+s.html+"</div>";
    else if(s.list)inner+="<ul>"+s.list.map(function(x){return "<li>"+x+"</li>";}).join("")+"</ul>";
    else if(s.media)inner+= s.media.type==="sieve"?"<div>"+sieveSVG()+"</div>":'<div class="body">'+s.media.caption+"</div>";
    stage.className="slide"+(s.cover?" cover":""); stage.innerHTML=inner;
    count.textContent="Slide "+(idx+1)+"/"+slides.length;
    dots.innerHTML=slides.map(function(_,i){return '<i class="'+(i===idx?"on":"")+'"></i>';}).join("");
    prev.disabled=idx===0; next.disabled=idx===slides.length-1;
  }
  prev.onclick=function(){if(idx>0){idx--;draw();}};
  next.onclick=function(){if(idx<slides.length-1){idx++;draw();}};
  document.addEventListener("keydown",function(e){
    if(!document.body.contains(deck))return;      // deck đã bị thay -> bỏ qua
    if(e.key==="ArrowLeft")prev.onclick();
    if(e.key==="ArrowRight")next.onclick();
  });
  draw();
}
