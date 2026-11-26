// @ts-nocheck

import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const dir = path.join(process.env.PI_CODING_AGENT_DIR || path.join(os.homedir(), ".pi", "agent"), "herdr-side-chat");
const file = path.join(dir, `${process.pid}.json`);

function record(ctx) {
  try {
    const sessionFile = ctx?.sessionManager?.getSessionFile?.();
    const sessionId = ctx?.sessionManager?.getSessionId?.();
    if (typeof sessionFile !== "string" || !path.isAbsolute(sessionFile)) return;
    fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
    const tmp = `${file}.${Date.now()}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify({
      pid: process.pid, ppid: process.ppid, sessionId, sessionFile, cwd: ctx?.cwd ?? process.cwd(),
    }), { mode: 0o600 });
    fs.renameSync(tmp, file);
  } catch {}
}

export default function (pi) {
  let active = false;
  pi.on("session_start", (_event, ctx) => {
    if (ctx?.mode !== "tui") return;
    active = true;
    record(ctx);
  });
  pi.on("agent_start", (_event, ctx) => {
    if (active) record(ctx);
  });
  pi.on("session_shutdown", (event) => {
    if (active && event?.reason === "quit") {
      try { fs.unlinkSync(file); } catch {}
    }
  });
}
