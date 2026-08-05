/* DATA GIẢ (mock) dùng chung cho các trang mockup. Thay bằng API thật sau:
   CURRICULUM -> GET /curriculum ; lesson* -> GET /lessons/{topic_id} ;
   PROGRESS   -> GET /progress/me (yêu cầu cần đạt lấy từ blueprint_cells). */

var SIEVE = { primes: new Set([2,3,5,7,11,13,17,19,23,29,31,37,41,43,47]) };

function lessonPrime(mach, dv){
  return {
    mach, dv,
    khai_niem:[
      "<b>Số nguyên tố</b> là số tự nhiên lớn hơn 1, chỉ có <b>đúng hai</b> ước là 1 và chính nó.",
      "<b>Hợp số</b> là số tự nhiên lớn hơn 1 và có <b>nhiều hơn hai</b> ước.",
      "<blockquote>Lưu ý: số 0 và 1 không phải số nguyên tố, cũng không phải hợp số.</blockquote>"
    ].join(""),
    minh_hoa:[
      {type:"sieve",caption:"Sàng Eratosthenes: các số nguyên tố ≤ 50 được tô đậm."},
      {type:"video",caption:"Video: cách kiểm tra một số có phải số nguyên tố."}
    ],
    vi_du:[
      {de:"Số 7 là số nguyên tố hay hợp số?",giai:"7 chỉ có hai ước là 1 và 7 → <b>7 là số nguyên tố</b>."},
      {de:"Xét số 12.",giai:"12 có các ước 1, 2, 3, 4, 6, 12 (nhiều hơn hai ước) → <b>12 là hợp số</b>."}
    ],
    quiz:[
      {q:"Số nào sau đây là số nguyên tố?",o:["9","15","13","21"],a:2,lv:"de"},
      {q:"Số 1 là:",o:["Số nguyên tố","Hợp số","Không phải cả hai"],a:2,lv:"de"},
      {q:"Có bao nhiêu số nguyên tố nhỏ hơn 10?",o:["3","4","5","6"],a:1,lv:"trung_binh"}
    ],
    day:{
      muc_tieu:"HS nhận biết số nguyên tố, hợp số; giải thích được vì sao 0 và 1 không thuộc hai loại này.",
      thoi_luong:"1 tiết · ~45 phút",
      goi_y:{
        khai_niem:"Mở bài bằng câu hỏi “số nào chỉ chia hết cho 1 và chính nó?”. Cho HS liệt kê ước của vài số rồi tự rút ra định nghĩa.",
        minh_hoa:"Dùng Sàng Eratosthenes: cho HS lần lượt gạch bội của 2, 3, 5, 7 để thấy các số nguyên tố “còn lại”.",
        vi_du:"Làm mẫu ví dụ số 7, rồi để HS tự xét số 12; nhấn mạnh thao tác “đếm số ước”.",
        kiem_tra:"Cho làm cá nhân 2 phút; chữa nhanh câu HS sai nhiều nhất."
      },
      luu_y:"Lỗi thường gặp: HS nhầm số 1 là số nguyên tố, hoặc tưởng mọi số chẵn đều là hợp số (quên số 2)."
    }
  };
}
function lessonGeneric(mach, dv){
  return {
    mach, dv,
    khai_niem:`<p>Phần <b>Khái niệm, định nghĩa</b> của “${dv}” sẽ do chuyên gia DTP biên soạn dưới dạng văn bản thuần, ngắn gọn, đúng chuẩn chương trình.</p><p>Nội dung có thể tổng hợp từ nhiều nguồn — không bắt buộc một cuốn sách.</p>`,
    minh_hoa:[{type:"img",caption:"Hình minh hoạ (ảnh do chuyên gia cung cấp)."},{type:"video",caption:"Video minh hoạ (tuỳ chọn)."}],
    vi_du:[{de:`Ví dụ minh hoạ cho “${dv}”.`,giai:"Lời giải từng bước hiển thị khi học sinh bấm “Xem lời giải”."}],
    quiz:[
      {q:`Câu hỏi kiểm tra nhanh cho “${dv}”.`,o:["Phương án A","Phương án B","Phương án C","Phương án D"],a:1,lv:"de"},
      {q:"Câu hỏi mức trung bình (sinh theo ma trận).",o:["A","B","C","D"],a:2,lv:"trung_binh"}
    ],
    day:{
      muc_tieu:`Sau bài, HS đạt yêu cầu cần đạt của “${dv}” theo ma trận đặc tả.`,
      thoi_luong:"1 tiết · ~45 phút",
      goi_y:{
        khai_niem:"Nêu định nghĩa ngắn gọn, gắn với ví dụ quen thuộc; kiểm tra HS nhắc lại bằng lời của mình.",
        minh_hoa:"Chiếu hình/video minh hoạ, hỏi HS mô tả điều quan sát được trước khi chốt.",
        vi_du:"Làm mẫu 1 ví dụ, sau đó cho HS làm 1 ví dụ tương tự tại chỗ.",
        kiem_tra:"Giao bài kiểm tra nhanh, chữa và ghi nhận HS còn vướng."
      },
      luu_y:"Nhấn mạnh phần HS hay nhầm; liên hệ đơn vị kiến thức kế tiếp."
    }
  };
}

// Mục lục BÁM SÁT ma trận TOAN_6_HK1.docx (đã chuẩn hoá & khử trùng OCR):
// 4 mạch nội dung của học kỳ 1.
var CURRICULUM = [
  {mach:"Số tự nhiên", em:"🔢", dv:[
    {t:"Số tự nhiên và tập hợp các số tự nhiên. Thứ tự trong tập hợp các số tự nhiên", st:"dat"},
    {t:"Các phép tính với số tự nhiên. Phép tính luỹ thừa với số mũ tự nhiên", st:"dang"},
    {t:"Tính chia hết trong tập hợp các số tự nhiên. Số nguyên tố. Ước chung và bội chung", st:"dang", prime:true},
  ]},
  {mach:"Số nguyên", em:"➖", dv:[
    {t:"Số nguyên âm và tập hợp các số nguyên. Thứ tự trong tập hợp các số nguyên", st:"chua"},
    {t:"Các phép tính với số nguyên. Tính chia hết trong tập hợp các số nguyên", st:"chua"},
  ]},
  {mach:"Các hình phẳng trong thực tiễn", em:"📐", dv:[
    {t:"Tam giác đều, hình vuông, lục giác đều", st:"chua"},
    {t:"Hình chữ nhật, hình thoi, hình bình hành, hình thang cân", st:"chua"},
  ]},
  {mach:"Tính đối xứng của hình phẳng trong thế giới tự nhiên", em:"🔷", dv:[
    {t:"Hình có trục đối xứng", st:"chua"},
    {t:"Hình có tâm đối xứng", st:"chua"},
    {t:"Vai trò của đối xứng trong thế giới tự nhiên", st:"chua"},
  ]},
];

// Tiến độ theo yêu cầu cần đạt — khớp 4 mạch của TOAN_6_HK1 (nguồn thật: blueprint_cells).
var PROGRESS = [
  {mach:"Số tự nhiên", ycd:[
    {t:"Nhận biết tập hợp và thứ tự các số tự nhiên", st:"dat"},
    {t:"Thực hiện các phép tính; luỹ thừa với số mũ tự nhiên", st:"dang"},
    {t:"Nhận biết số nguyên tố, hợp số; tìm ƯC, BC, ƯCLN, BCNN", st:"dang"},
    {t:"Vận dụng dấu hiệu chia hết cho 2, 3, 5, 9", st:"chua"},
  ]},
  {mach:"Số nguyên", ycd:[
    {t:"Nhận biết số nguyên âm, tập hợp và thứ tự các số nguyên", st:"chua"},
    {t:"Thực hiện cộng, trừ, nhân, chia số nguyên; tính chia hết", st:"chua"},
  ]},
  {mach:"Các hình phẳng trong thực tiễn", ycd:[
    {t:"Nhận biết tam giác đều, hình vuông, lục giác đều", st:"chua"},
    {t:"Nhận biết hình chữ nhật, hình thoi, hình bình hành, hình thang cân", st:"chua"},
  ]},
  {mach:"Tính đối xứng của hình phẳng trong thế giới tự nhiên", ycd:[
    {t:"Nhận biết hình có trục đối xứng, tâm đối xứng", st:"chua"},
    {t:"Nhận biết vai trò của đối xứng trong tự nhiên và nghệ thuật", st:"chua"},
  ]},
];

/* helpers dùng chung */
function el(t,c,h){var e=document.createElement(t);if(c)e.className=c;if(h!=null)e.innerHTML=h;return e;}
var ST={dat:["st-dat","b-dat","Đạt"],dang:["st-dang","b-dang","Đang học"],chua:["st-chua","b-chua","Chưa học"]};
function pct(arr){return Math.round(100*arr.filter(function(x){return x.st==="dat";}).length/arr.length);}
function lessonFor(mi,di){var m=CURRICULUM[mi],d=m.dv[di];return d.prime?lessonPrime(m.mach,d.t):lessonGeneric(m.mach,d.t);}

function sieveSVG(){
  var cell=34,cols=10,w=cols*cell,h=5*cell,cells="";
  for(var n=1;n<=50;n++){
    var i=n-1,x=(i%cols)*cell,y=Math.floor(i/cols)*cell,p=SIEVE.primes.has(n);
    cells+='<rect x="'+(x+1)+'" y="'+(y+1)+'" width="'+(cell-2)+'" height="'+(cell-2)+'" rx="6" fill="'+(p?'var(--brand)':'var(--surface-2)')+'" stroke="var(--border)"/>'
      +'<text x="'+(x+cell/2)+'" y="'+(y+cell/2+4)+'" text-anchor="middle" font-size="12" font-weight="700" fill="'+(p?'#fff':'var(--ink-3)')+'">'+n+'</text>';
  }
  return '<svg viewBox="0 0 '+w+' '+h+'" width="100%" role="img" aria-label="Sàng số nguyên tố đến 50">'+cells+'</svg>';
}

/* Nút đổi sáng/tối */
function initTheme(btn){
  if(!btn)return;
  btn.addEventListener("click",function(){
    var root=document.documentElement;
    var dark=root.getAttribute("data-theme")==="dark" ||
      (!root.getAttribute("data-theme")&&matchMedia("(prefers-color-scheme:dark)").matches);
    root.setAttribute("data-theme",dark?"light":"dark");
  });
}
