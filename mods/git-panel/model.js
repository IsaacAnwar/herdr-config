// Git emits NUL-separated fields so spaces and tabs in names stay intact.
export const LOG_FORMAT = "%H%x00%h%x00%P%x00%an%x00%aI%x00%s%x00%D%x00";
export const REF_FORMAT = "%(refname)%00%(refname:short)%00%(objectname:short)%00%(committerdate:iso-strict)%00%(subject)%00%(upstream:short)%00%(upstream:track)%00%(HEAD)%00";

function records(text, size) {
  const fields = String(text).split("\0");
  const out = [];
  for (let i = 0; i + size <= fields.length; i += size) {
    const row = fields.slice(i, i + size);
    row[0] = row[0].replace(/^\n+/, "");
    if (row[0]) out.push(row);
  }
  return out;
}

export function commits(text) {
  return records(text, 7).map(([oid, short, parents, author, date, subject, refs]) =>
    ({ oid, short, parents: parents.split(" ").filter(Boolean), author, date, subject, refs }));
}

export function branches(text) {
  return records(text, 8).map(([ref, name, oid, date, subject, upstream, track, head]) =>
    ({ ref, name, oid, date, subject, upstream, track, current: head === "*", remote: ref.startsWith("refs/remotes/") }))
    .filter(b => !(b.remote && b.ref.endsWith("/HEAD")));
}

export function status(text) {
  const lines = text.split("\n");
  const field = name => lines.find(line => line.startsWith(`# branch.${name} `))?.slice(name.length + 10);
  const [ahead, behind] = (field("ab") ?? "+0 -0").split(" ").map(v => Math.abs(Number(v)) || 0);
  return { branch: field("head") ?? "Detached HEAD", unborn: field("oid") === "(initial)", ahead, behind };
}

export function commitInfo(text, stats) {
  const [oid, author, date, parents, ...body] = text.split("\0");
  const files = stats.split("\0").filter(Boolean).map(entry => {
    const [add, del, ...path] = entry.replace(/^\n+/, "").split("\t");
    return { path: path.join("\t"), add: add === "-" ? null : Number(add) || 0, del: del === "-" ? null : Number(del) || 0 };
  }).filter(f => f.path);
  return { oid, author, date, parents: (parents ?? "").split(" ").filter(Boolean), message: body.join("\0").trim().slice(0, 24000), files };
}

export function relativeTime(date) {
  const seconds = Math.max(0, (Date.now() - Date.parse(date)) / 1000);
  if (!Number.isFinite(seconds)) return "";
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 2592000) return `${Math.floor(seconds / 86400)}d ago`;
  return date.slice(0, 10);
}

export function githubURL(remote) {
  const match = String(remote).trim().match(/^(?:git@github\.com:|https:\/\/github\.com\/|ssh:\/\/git@github\.com\/)([^/]+)\/([^/]+?)(?:\.git)?$/);
  return match ? `https://github.com/${match[1]}/${match[2]}` : null;
}

export function checkSummary(checks = []) {
  let failed = 0, pending = 0;
  for (const c of checks ?? []) {
    const state = c.conclusion || c.state || c.status;
    if (["FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE"].includes(state)) failed++;
    else if (["PENDING", "QUEUED", "IN_PROGRESS", "WAITING", "REQUESTED", "EXPECTED"].includes(state)) pending++;
  }
  return { total: checks?.length ?? 0, failed, pending };
}
