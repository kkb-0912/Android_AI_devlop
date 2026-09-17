// 아주 단순한 서비스 워커: 안드로이드 "홈 화면에 추가" 요구 조건 충족용.
// 오프라인 사용을 위한 것이 아니라, 정적 자원 캐시만 가볍게 수행합니다.
const CACHE_NAME = "ai-assistant-shell-v1";
const SHELL_FILES = ["/static/style.css", "/static/app.js", "/static/manifest.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_FILES)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  // 채팅 API 등 동적 요청은 항상 네트워크로. 정적 파일만 캐시 우선.
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  if (!url.pathname.startsWith("/static/")) return;

  event.respondWith(
    caches.match(event.request).then((cached) => {
      return (
        cached ||
        fetch(event.request).then((resp) => {
          const copy = resp.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
          return resp;
        })
      );
    })
  );
});
