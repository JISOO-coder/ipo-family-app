// 서비스 워커 (앱 설치와 이후 푸시 알림용). 지금은 아무것도 가로채지 않습니다.
self.addEventListener("install", function () { self.skipWaiting(); });
self.addEventListener("activate", function (e) { e.waitUntil(self.clients.claim()); });
self.addEventListener("fetch", function () { /* 기본 동작 그대로 */ });
