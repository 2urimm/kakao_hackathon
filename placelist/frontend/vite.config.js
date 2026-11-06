import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// npm run dev   → http://localhost:5173  (API는 파이썬 서버 8000으로 프록시)
// npm run build → ../web 에 정적 파일 생성 → python server.py 가 그대로 서비스
export default defineConfig({
  plugins: [react()],
  build: { outDir: "../web", emptyOutDir: true },
  // placelist 파이썬 서버 주소. 채팅 서버와 같은 PC라 8000이 겹치면: PLACELIST_SERVER=http://localhost:8200 npm run dev
  server: { proxy: {
    "/api": process.env.PLACELIST_SERVER || "http://localhost:8000",
    // config.js 의 CHAT_API_BASE "/chat" → 채팅 저장 서버 (빌드본에서는 server.py 가 같은 일을 함)
    "/chat": { target: process.env.CHAT_SERVER_URL || "http://localhost:8000", rewrite: p => p.replace(/^\/chat/, "") },
  } },
});
