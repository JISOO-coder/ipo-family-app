// 서비스 워커: 앱 설치 + 푸시 알림.
// 알림 내용은 서버가 보낸 '오늘 일정'에 이 폰에 저장된 선택(내 증권사, 청약함/패스)을 합쳐서 만듭니다.
self.addEventListener("install", function () { self.skipWaiting(); });
self.addEventListener("activate", function (e) { e.waitUntil(self.clients.claim()); });
self.addEventListener("fetch", function () { /* 기본 동작 그대로 */ });

// 앱 화면이 저장해 둔 값 읽기 (IndexedDB 'ipo-family' / 'kv')
function readKV(key) {
  return new Promise(function (resolve) {
    try {
      const rq = indexedDB.open("ipo-family", 1);
      rq.onupgradeneeded = function () { rq.result.createObjectStore("kv"); };
      rq.onerror = function () { resolve({}); };
      rq.onsuccess = function () {
        try {
          const g = rq.result.transaction("kv", "readonly").objectStore("kv").get(key);
          g.onsuccess = function () { resolve(g.result || {}); };
          g.onerror = function () { resolve({}); };
        } catch (e) { resolve({}); }
      };
    } catch (e) { resolve({}); }
  });
}

function brokerText(ev, sel) {
  const all = ev.brokers || [];
  if (all.length === 1) return all[0];
  const mine = (sel[ev.key] || []).filter(function (b) { return all.indexOf(b) >= 0; });
  if (mine.length) return "내 증권사 " + mine[0];
  return "증권사 미선택(" + all.join(", ") + ")";
}

function buildDaily(data, sel, status) {
  const lines = [];
  (data.events || []).forEach(function (ev) {
    const st = status[ev.key];
    if (st === "skip") return;                                   // 패스한 종목은 알리지 않음
    if (ev.kind === "sub_start") lines.push("🔔 " + ev.name + " 청약 시작 · " + brokerText(ev, sel));
    if (ev.kind === "sub_end" && st !== "joined") lines.push("🔥 " + ev.name + " 오늘 청약 마감 · " + brokerText(ev, sel));
    if (ev.kind === "listing") lines.push("📈 " + ev.name + " 오늘 상장 · " + brokerText(ev, sel));
  });
  if (!lines.length) {
    // 브라우저 규칙상 알림을 아예 안 띄울 수는 없어서, 소리 없이 조용히 표시
    return { title: "오늘 공모주 일정", body: "확인할 일정이 없어요 (패스했거나 청약을 마친 종목만 있어요)", silent: true };
  }
  return { title: "오늘 공모주 일정 " + lines.length + "건", body: lines.join("\n"), silent: false };
}

self.addEventListener("push", function (e) {
  let data = {};
  try { data = e.data ? e.data.json() : {}; } catch (x) {}
  e.waitUntil(Promise.all([readKV("selections"), readKV("status")]).then(function (r) {
    const msg = data.type === "daily"
      ? buildDaily(data, r[0], r[1])
      : { title: "공모주 알림 테스트", body: "알림이 잘 와요! 이제 청약·상장일 아침에 알려 드릴게요.", silent: false };
    return self.registration.showNotification(msg.title, {
      body: msg.body, silent: msg.silent, icon: "icon-192.png", badge: "icon-192.png",
      tag: "ipo-" + (data.date || "test"), data: { url: "./" }
    });
  }));
});

// 알림을 누르면 앱 열기 (이미 열려 있으면 그 창으로)
self.addEventListener("notificationclick", function (e) {
  e.notification.close();
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (list) {
    for (let i = 0; i < list.length; i++) {
      if ("focus" in list[i]) return list[i].focus();
    }
    return self.clients.openWindow(e.notification.data && e.notification.data.url || "./");
  }));
});
