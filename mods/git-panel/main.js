import { View, div, svg } from "gpui-kit";
import { v_flex, h_flex, InputState, Input, TextView, Scrollbar } from "gpui-base";
import { spaces, panes, focused, exec, theme, props, layout, run, shared, setShared, pickFolder, window } from "herdr";
import { LOG_FORMAT, REF_FORMAT, commits, branches, status, commitInfo, relativeTime, githubURL, checkSummary } from "./model.js";

const MOD = "git-panel";
const FOLDERS = "git-panel.folders";
const READ = ["--no-optional-locks", "-c", "core.fsmonitor=false", "-c", "diff.autoRefreshIndex=false"];
const icon = (name, size = 14) => svg(`mods/${MOD}/${name}.svg`).size(size).flex_none();
const base = path => (path ?? "").replace(/[\\/]+$/, "").split(/[\\/]/).pop();
const errorText = e => String(e?.message ?? e).replace(/\x1b\[[0-9;]*m/g, "").trim().slice(0, 350);

function find(node, id) {
  if (node?.id === id) return node;
  for (const child of node?.children ?? []) { const match = find(child, id); if (match) return match; }
  return null;
}

function visible() {
  const panel = find(layout(), "panel"), body = find(layout(), "panel-body");
  return panel && !panel.hidden && body?.active === "git";
}

function location() {
  const space = spaces().find(s => s.active), f = focused();
  const pane = f?.pane ? panes().find(p => p.pane === f.pane) : null;
  const selected = shared(FOLDERS)?.[space?.id];
  return { space: space?.id ?? null, cwd: selected || pane?.cwd || f?.cwd || space?.folder || null, on: space?.machine ?? null, pinned: Boolean(selected) };
}
const contextKey = () => JSON.stringify(location());

export default class GitPanel extends View {
  init(_props, cx) {
    if (props()?.button) {
      const enabled = shared("workspace.panels") ?? ["files", "changes"];
      if (!enabled.includes("git")) setShared("workspace.panels", [...enabled, "git"]);
      return;
    }
    this.view = localStorage.getItem("view") ?? "history";
    if (!["history", "branches", "prs"].includes(this.view)) this.view = "history";
    this.scope = ""; this.branchKind = "local"; this.prState = "open"; this.limit = 100;
    this.commits = []; this.branches = []; this.prs = []; this.searchText = "";
    this.loadSeq = 0; this.prSeq = 0; this.detailSeq = 0;
    this.search = InputState.new({ placeholder: "Filter commits, branches, or PRs" });
    this.search.on("change", (_e, cx) => { this.searchText = this.search.value(); cx.notify(); });
    cx.timer.every(15000, cx => {
      if (visible()) this.refresh(cx);
    });
  }

  git(args, repo = this.repo, on = this.on) {
    return exec("git", [...READ, ...args], { cwd: repo, on, timeout: 20000 });
  }

  adopt(loc) {
    const key = JSON.stringify(loc);
    if (key === this.context) return;
    this.context = key; this.loc = loc; this.repo = null; this.on = loc.on;
    this.loaded = false; this.loading = false; this.prLoading = false; this.prLoaded = false;
    this.commits = []; this.branches = []; this.prs = []; this.repoInfo = null; this.webURL = null;
    this.error = null; this.historyError = null; this.prError = null; this.note = null;
    this.scope = ""; this.limit = 100; this.selected = null; this.detail = null; this.detailLoading = false;
    this.loadSeq++; this.prSeq++; this.detailSeq++;
  }

  refresh(cx, forcePR = false) {
    this.adopt(location());
    if (this.loading) return;
    const loc = this.loc, context = this.context, sequence = ++this.loadSeq;
    if (!loc.cwd) { this.loaded = true; this.error = "No folder selected."; return; }
    const scope = this.scope, limit = this.limit;
    const current = () => this.context === context && contextKey() === context && this.loadSeq === sequence;
    this.loading = true;
    cx.spawn(async cx => {
      try {
        const top = await this.git(["rev-parse", "--show-toplevel"], loc.cwd, loc.on);
        if (!current()) return;
        if (top.code !== 0) {
          this.repo = null;
          this.error = /not a git repository/i.test(top.stderr) ? "This space is not in a Git repository." : errorText(top.stderr || "Cannot read this folder.");
          return;
        }
        const repo = top.stdout.trim();
        const [state, refs, log, remote] = await Promise.all([
          this.git(["status", "--porcelain=v2", "--branch", "--untracked-files=no"], repo, loc.on),
          this.git(["for-each-ref", "--sort=-committerdate", `--format=${REF_FORMAT}`, "refs/heads", "refs/remotes"], repo, loc.on),
          this.git(["log", "--no-color", "--decorate=short", `--format=${LOG_FORMAT}`, `--max-count=${limit + 1}`, ...(scope === "--all" ? ["--all"] : scope ? [scope] : []), "--"], repo, loc.on),
          this.git(["remote", "get-url", "origin"], repo, loc.on),
        ]);
        if (!current()) return;
        if (state.code !== 0 || refs.code !== 0) throw new Error(state.stderr || refs.stderr);
        this.repo = repo; this.repoInfo = status(state.stdout); this.branches = branches(refs.stdout);
        this.webURL = this.webURL || githubURL(remote.stdout);
        const history = log.code === 0 ? commits(log.stdout) : [];
        this.commits = history.slice(0, limit); this.more = history.length > limit;
        this.historyError = log.code !== 0 && !this.repoInfo.unborn ? errorText(log.stderr) : null;
        this.error = null;
      } catch (e) { if (current()) this.error = errorText(e); }
      finally {
        if (current()) {
          this.loading = false; this.loaded = true;
          if (this.repo && this.view === "prs" && (forcePR || !this.prLoaded || Date.now() - (this.prAt ?? 0) > 60000)) this.loadPRs(cx, forcePR);
          cx.notify();
        }
      }
    });
  }

  loadPRs(cx, force = false) {
    if (!this.repo || this.prLoading || (!force && this.prLoaded && Date.now() - this.prAt < 60000)) return;
    const repo = this.repo, on = this.on, context = this.context, state = this.prState, sequence = ++this.prSeq;
    const current = () => this.context === context && contextKey() === context && this.prSeq === sequence && this.prState === state;
    this.prLoading = true; this.prError = null;
    cx.spawn(async cx => {
      try {
        const remote = await exec("gh", ["repo", "view", "--json", "nameWithOwner,url"], { cwd: repo, on, timeout: 20000 });
        if (remote.code !== 0) throw new Error(remote.stderr || "GitHub repository unavailable.");
        const github = JSON.parse(remote.stdout);
        const result = await exec("gh", ["pr", "list", "--repo", github.url, "--state", state, "--limit", "100", "--json", "number,title,state,isDraft,author,headRefName,baseRefName,updatedAt,url,reviewDecision"], { cwd: repo, on, timeout: 30000 });
        if (result.code !== 0) throw new Error(result.stderr);
        if (!current()) return;
        this.prs = JSON.parse(result.stdout); this.webURL = github.url;
      } catch (e) {
        if (current()) { this.prError = errorText(e); this.prs = []; }
      } finally {
        if (current()) { this.prLoading = false; this.prLoaded = true; this.prAt = Date.now(); cx.notify(); }
      }
    });
  }

  switchTab(view, cx) {
    this.view = view; localStorage.setItem("view", view);
    this.selected = null; this.detail = null; this.detailSeq++;
    this.searchText = ""; this.search.set_value("");
    if (view === "prs") this.loadPRs(cx);
    cx.notify();
  }

  setScope(scope, cx) {
    this.scope = scope; this.limit = 100; this.view = "history"; localStorage.setItem("view", "history");
    this.selected = null; this.detail = null; this.detailSeq++; this.searchText = ""; this.search.set_value("");
    // Invalidate any older log request, including a poll already in flight.
    this.loadSeq++; this.loading = false; this.refresh(cx); cx.notify();
  }

  chooseFolder(cx, follow = false) {
    const space = spaces().find(s => s.active);
    if (!space || space.machine) return;
    if (follow) {
      const folders = { ...(shared(FOLDERS) ?? {}) }; delete folders[space.id]; setShared(FOLDERS, folders);
      this.refresh(cx); cx.notify(); return;
    }
    cx.spawn(async cx => {
      const folder = await pickFolder({ prompt: "Choose a Git repository" });
      if (folder) setShared(FOLDERS, { ...(shared(FOLDERS) ?? {}), [space.id]: folder });
      this.refresh(cx); cx.notify();
    });
  }

  selectCommit(commit, cx) {
    if (!/^[0-9a-f]{40,64}$/i.test(commit.oid)) return;
    const repo = this.repo, on = this.on, context = this.context, sequence = ++this.detailSeq;
    const current = () => context === this.context && contextKey() === context && sequence === this.detailSeq;
    this.selected = { kind: "commit", value: commit }; this.detail = null; this.detailError = null; this.detailLoading = true;
    cx.spawn(async cx => {
      try {
        const [meta, files] = await Promise.all([
          this.git(["show", "--no-patch", "--format=%H%x00%an%x00%aI%x00%P%x00%B", commit.oid, "--"], repo, on),
          this.git(["show", "--format=", "--numstat", "-z", "--no-renames", "--first-parent", "--no-ext-diff", "--no-textconv", commit.oid, "--"], repo, on),
        ]);
        if (meta.code !== 0 || files.code !== 0) throw new Error(meta.stderr || files.stderr);
        if (current()) this.detail = commitInfo(meta.stdout, files.stdout);
      } catch (e) { if (current()) this.detailError = errorText(e); }
      finally { if (current()) { this.detailLoading = false; cx.notify(); } }
    });
    cx.notify();
  }

  selectPR(pr, cx) {
    const repo = this.repo, on = this.on, context = this.context, sequence = ++this.detailSeq, url = pr.url;
    const current = () => context === this.context && contextKey() === context && sequence === this.detailSeq;
    this.selected = { kind: "pr", value: pr }; this.detail = null; this.detailError = null; this.detailLoading = true;
    cx.spawn(async cx => {
      try {
        const r = await exec("gh", ["pr", "view", url, "--json", "number,title,body,url,state,isDraft,author,headRefName,baseRefName,additions,deletions,changedFiles,reviewDecision,mergeable,commits,statusCheckRollup,files"], { cwd: repo, on, timeout: 30000 });
        if (r.code !== 0) throw new Error(r.stderr);
        if (current()) this.detail = JSON.parse(r.stdout);
      } catch (e) { if (current()) this.detailError = errorText(e); }
      finally { if (current()) { this.detailLoading = false; cx.notify(); } }
    });
    cx.notify();
  }

  openURL(url, cx) {
    if (!/^https:\/\//i.test(url ?? "")) return;
    cx.spawn(async cx => {
      try {
        const platform = window().platform;
        const r = platform === "windows"
          ? await exec("rundll32.exe", ["url.dll,FileProtocolHandler", url])
          : await exec(platform === "macos" ? "open" : "xdg-open", [url]);
        if (r.code !== 0) this.note = errorText(r.stderr || "Could not open the browser.");
      } catch (e) { this.note = errorText(e); }
      cx.notify();
    });
  }

  button(id, label, action, t, active = false) {
    return div().id(id).h(26).px(8).rounded(5).flex().items_center().justify_center().text_size(11.5)
      .bg(active ? t.selected : t.background).text_color(active ? t.foreground : t.muted).cursor_pointer()
      .hover(s => s.bg(t.hover)).on_click(action).child(label);
  }

  tool(id, glyph, title, action, t) {
    return div().id(id).size(25).rounded(5).flex().items_center().justify_center().text_color(t.muted)
      .tooltip(title).cursor_pointer().hover(s => s.bg(t.hover)).on_click(action).child(icon(glyph));
  }

  badge(text, t, color = t.muted) {
    return div().flex_none().px(5).py(1).rounded(4).bg(t.raised).text_size(10).text_color(color).child(text);
  }

  empty(text, t) { return div().p(16).text_size(12).text_color(t.dim).whitespace_normal().child(text); }
  scroller(id) { return v_flex().id(id).overflow_y_scroll().p(7).gap(3); }
  scrollFrame(id, content) {
    return div().flex_1().min_h(0).relative()
      .child(content.absolute().inset_0())
      .child(Scrollbar.vertical(id).absolute().inset_0());
  }
  matches(...values) { const q = this.searchText.trim().toLowerCase(); return !q || values.some(v => String(v ?? "").toLowerCase().includes(q)); }

  history(t) {
    const filtered = this.commits.filter(c => this.matches(c.subject, c.author, c.short, c.refs));
    const list = this.scroller("git-history");
    if (this.historyError) list.child(this.empty(this.historyError, t));
    if (!filtered.length && !this.historyError) list.child(this.empty(this.loading ? "Loading commits…" : this.searchText ? "No matching commits." : "No commits yet.", t));
    for (const c of filtered) {
      list.child(h_flex().id(`git-commit-${c.oid}`).gap(9).p(8).rounded(6).cursor_pointer().hover(s => s.bg(t.hover))
        .on_click((_e, cx) => this.selectCommit(c, cx))
        .child(div().pt(3).text_color(t.dim).child(icon("commit", 13)))
        .child(v_flex().flex_1().min_w(0).gap(5)
          .child(div().truncate().text_size(12).child(c.subject || "Untitled commit"))
          .when(Boolean(c.refs), e => e.child(div().truncate().text_size(10.5).text_color(t.accent).child(c.refs)))
          .child(h_flex().gap(7).text_size(10.5).text_color(t.dim)
            .child(div().text_color(t.muted).child(c.short)).child(div().flex_1().truncate().child(c.author))
            .child(div().flex_none().child(relativeTime(c.date))))));
    }
    if (this.more) list.child(this.button("git-more", `Load ${this.limit < 1000 ? "more commits" : "latest 1,000 commits"}`, (_e, cx) => {
      if (this.limit < 1000) { this.limit += 100; this.loadSeq++; this.loading = false; this.refresh(cx); cx.notify(); }
    }, t));
    return v_flex().flex_1().min_h(0)
      .child(h_flex().flex_none().px(8).py(5).gap(4)
        .child(this.button("git-current", "Current branch", (_e, cx) => this.setScope("", cx), t, !this.scope))
        .child(this.button("git-all", "All branches", (_e, cx) => this.setScope("--all", cx), t, this.scope === "--all")))
      .when(this.scope && this.scope !== "--all", e => e.child(div().px(14).pb(6).truncate().text_size(11).text_color(t.accent).child(this.scope.replace(/^refs\/(heads|remotes)\//, ""))))
      .child(this.scrollFrame("git-history", list));
  }

  branchList(t) {
    const filtered = this.branches.filter(b => (this.branchKind === "all" || b.remote === (this.branchKind === "remote")) && this.matches(b.name, b.subject, b.upstream));
    const list = this.scroller("git-branches");
    for (const b of filtered) {
      list.child(v_flex().id(`git-ref-${b.ref}`).p(8).gap(5).rounded(6).cursor_pointer().hover(s => s.bg(t.hover))
        .tooltip("View commits on this branch")
        .on_click((_e, cx) => this.setScope(b.ref, cx))
        .child(h_flex().gap(7).items_center().text_color(b.current ? t.accent : t.foreground)
          .child(icon("branch")).child(div().flex_1().min_w(0).truncate().child(b.name))
          .when(b.current, e => e.child(this.badge("current", t, t.accent))))
        .child(div().truncate().text_size(11).text_color(t.muted).child(b.subject))
        .child(h_flex().gap(6).text_size(10.5).text_color(t.dim)
          .child(div().child(b.oid)).child(div().flex_1().truncate().child([b.upstream, b.track.replace(/[\[\]]/g, "")].filter(Boolean).join(" · ")))
          .child(div().flex_none().child(relativeTime(b.date)))));
    }
    if (!filtered.length) list.child(this.empty("No matching branches.", t));
    return v_flex().flex_1().min_h(0)
      .child(h_flex().flex_none().px(8).py(5).gap(4).children(["local", "remote", "all"].map(kind =>
        this.button(`git-branches-${kind}`, kind[0].toUpperCase() + kind.slice(1), (_e, cx) => { this.branchKind = kind; cx.notify(); }, t, this.branchKind === kind))))
      .when(this.branchKind !== "local", e => e.child(div().px(14).pb(5).text_size(10.5).text_color(t.dim).child("Remote branches reflect your last fetch.")))
      .child(this.scrollFrame("git-branches", list));
  }

  prColor(pr, t) { return pr.isDraft ? t.dim : pr.state === "MERGED" ? t.ansi5 : pr.state === "CLOSED" ? t.ansi1 : t.ansi2; }

  pullRequests(t) {
    const list = this.scroller("git-prs");
    if (this.prError) list.child(this.empty(`Pull requests unavailable. ${this.prError}`, t));
    const filtered = this.prs.filter(p => this.matches(p.title, p.number, p.author?.login, p.headRefName, p.baseRefName));
    if (!filtered.length && !this.prError) list.child(this.empty(this.prLoading ? "Loading pull requests…" : "No matching pull requests.", t));
    for (const p of filtered) {
      list.child(h_flex().id(`git-pr-${p.number}`).gap(8).p(8).rounded(6).cursor_pointer().hover(s => s.bg(t.hover))
        .on_click((_e, cx) => this.selectPR(p, cx))
        .child(div().pt(2).text_color(this.prColor(p, t)).child(icon("pull-request")))
        .child(v_flex().flex_1().min_w(0).gap(5)
          .child(div().truncate().text_size(12).child(p.title))
          .child(div().truncate().text_size(10.5).text_color(t.dim).child(`${p.headRefName} → ${p.baseRefName}`))
          .child(h_flex().gap(7).text_size(10.5).text_color(t.dim)
            .child(div().text_color(this.prColor(p, t)).child(`#${p.number}${p.isDraft ? " · Draft" : ""}`))
            .child(div().flex_1().truncate().child(p.author?.login ?? ""))
            .child(div().flex_none().child(relativeTime(p.updatedAt))))));
    }
    return v_flex().flex_1().min_h(0)
      .child(h_flex().flex_none().px(8).py(5).gap(4).children(["open", "merged", "all"].map(state =>
        this.button(`git-prs-${state}`, state[0].toUpperCase() + state.slice(1), (_e, cx) => {
          this.prState = state; this.prSeq++; this.prLoading = false; this.prs = []; this.prLoaded = false;
          this.loadPRs(cx, true); cx.notify();
        }, t, this.prState === state))))
      .child(this.scrollFrame("git-prs", list))
      .when(this.prs.length === 100, e => e.child(div().px(14).py(5).text_size(10.5).text_color(t.dim).child("Showing the latest 100 pull requests.")));
  }

  details(t) {
    const d = this.detail, selected = this.selected;
    const content = this.scroller("git-details").p(14).gap(12);
    if (this.detailLoading) content.child(this.empty("Loading details…", t));
    else if (this.detailError) content.child(this.empty(this.detailError, t));
    else if (d && selected.kind === "commit") {
      const totals = d.files.reduce((sum, f) => ({ add: sum.add + (f.add ?? 0), del: sum.del + (f.del ?? 0) }), { add: 0, del: 0 });
      content.child(div().font_semibold().whitespace_normal().child(selected.value.subject))
        .child(div().text_size(11).text_color(t.muted).child(`${d.author} · ${d.date.replace("T", " ").slice(0, 19)}`))
        .child(div().text_size(10.5).text_color(t.dim).whitespace_normal().child(d.oid))
        .child(div().text_size(12).whitespace_normal().child(d.message))
        .child(h_flex().gap(8).items_center().child(div().flex_1().font_semibold().child(`${d.files.length} files changed`))
          .child(div().text_color(t.ansi2).child(`+${totals.add}`)).child(div().text_color(t.ansi1).child(`−${totals.del}`)));
      d.files.slice(0, 300).forEach((f, i) => content.child(h_flex().id(`git-commit-file-${i}`).gap(7).py(4).items_center()
        .child(div().flex_1().min_w(0).truncate().tooltip(f.path).text_size(11.5).child(f.path))
        .child(div().text_size(10.5).text_color(t.ansi2).child(f.add == null ? "binary" : `+${f.add}`))
        .when(f.del != null, e => e.child(div().text_size(10.5).text_color(t.ansi1).child(`−${f.del}`)))));
      if (d.files.length > 300) content.child(this.empty("Showing the first 300 files.", t));
      if (d.parents.length) content.child(div().text_size(10.5).text_color(t.dim).whitespace_normal().child(`Parents: ${d.parents.map(p => p.slice(0, 8)).join(", ")}`));
      if (this.webURL) content.child(this.button("git-commit-web", "Open commit on GitHub", (_e, cx) => this.openURL(`${this.webURL}/commit/${d.oid}`, cx), t));
    } else if (d) {
      const checks = checkSummary(d.statusCheckRollup);
      const review = { APPROVED: "Approved", CHANGES_REQUESTED: "Changes requested", REVIEW_REQUIRED: "Review required" }[d.reviewDecision] ?? "No review decision";
      content.child(div().font_semibold().whitespace_normal().child(d.title))
        .child(h_flex().gap(7).items_center().child(this.badge(d.isDraft ? "Draft" : d.state.toLowerCase(), t, this.prColor(d, t)))
          .child(div().text_size(11).text_color(t.muted).child(`#${d.number} · ${d.author?.login ?? ""}`)))
        .child(div().text_size(11).text_color(t.muted).whitespace_normal().child(`${d.headRefName} → ${d.baseRefName}`))
        .child(div().text_size(11.5).text_color(d.reviewDecision === "CHANGES_REQUESTED" ? t.ansi3 : t.muted).child(review))
        .child(div().text_size(11.5).text_color(checks.failed ? t.ansi1 : checks.pending ? t.ansi3 : t.muted)
          .child(`${checks.total} checks · ${checks.failed} failed · ${checks.pending} pending${d.mergeable === "CONFLICTING" ? " · Merge conflicts" : ""}`))
        .child(h_flex().gap(9).text_size(11.5).child(div().text_color(t.muted).child(`${d.changedFiles} files`))
          .child(div().text_color(t.ansi2).child(`+${d.additions}`)).child(div().text_color(t.ansi1).child(`−${d.deletions}`)))
        .child(this.button("git-pr-web", "Open pull request on GitHub", (_e, cx) => this.openURL(d.url, cx), t))
        .child(TextView.markdown(`git-pr-body-${d.number}`, (d.body || "No description.").slice(0, 24000)).selectable(true).w_full());
      if (d.commits?.length) {
        content.child(div().font_semibold().child(`${d.commits.length} commits`));
        d.commits.slice(0, 30).forEach((c, i) => content.child(div().id(`git-pr-commit-${i}`).text_size(11).whitespace_normal().text_color(t.muted).child(`${c.oid.slice(0, 8)} · ${c.messageHeadline}`)));
      }
      if (d.files?.length) {
        content.child(div().font_semibold().child("Changed files"));
        d.files.slice(0, 100).forEach((f, i) => content.child(div().id(`git-pr-file-${i}`).text_size(11).text_color(t.muted).truncate().tooltip(f.path).child(f.path)));
      }
    }
    return v_flex().flex_1().min_h(0)
      .child(h_flex().flex_none().px(8).py(5).gap(5).items_center()
        .child(this.button("git-back", "← Back", (_e, cx) => { this.selected = null; this.detail = null; this.detailSeq++; cx.notify(); }, t))
        .child(div().text_size(11).text_color(t.dim).child(selected.kind === "commit" ? "Commit details" : "Pull request")))
      .child(this.scrollFrame("git-details", content));
  }

  renderButton(t) {
    const active = visible();
    return h_flex().size_full().items_center().justify_start().bg(t.chrome).border_b(1).border_color(t.border)
      .child(h_flex().id("git-panel-button").h(26).px(8).gap(5).flex_none().rounded(6).items_center().text_size(12)
        .on_size_change(size => {
          const width = Math.ceil(size.width) + 4;
          if (this.buttonWidth !== width) { this.buttonWidth = width; run("layout.resize", { id: "git-button", px: width }); }
        })
        .bg(active ? t.selected : t.chrome).text_color(active ? t.foreground : t.muted).cursor_pointer().hover(s => s.bg(t.hover))
        .on_mouse_down("left", (_e, cx) => cx.stop_propagation())
        .on_click(() => { if (active) run("layout.hide", { id: "panel" }); else { run("layout.select", { stack: "panel-body", child: "git" }); run("layout.show", { id: "panel" }); } })
        .child(icon("branch")).child("Git"));
  }

  render(cx) {
    const t = theme();
    if (props()?.button) return this.renderButton(t);
    if (visible() && (!this.loaded || this.context !== contextKey())) this.refresh(cx);
    const root = v_flex().id("git-panel").size_full().min_h(0).rounded(10).overflow_hidden().bg(t.background)
      .border_1().border_color(t.border).text_color(t.foreground).text_size(12.5);
    root.child(h_flex().h(42).flex_none().px(12).gap(7).items_center().border_b(1).border_color(t.border)
      .child(icon("branch", 15)).child(div().font_semibold().child("Git"))
      .child(div().flex_1().min_w(0).truncate().text_size(11).text_color(t.dim).tooltip(this.repo || this.loc?.cwd || "").child(base(this.repo)))
      .when(this.loading || this.prLoading, e => e.child(svg("mods/workspace-chrome/spinner.svg").size(12).text_color(t.dim).spin(900)))
      .when(!this.loc?.on, e => e.child(this.tool("git-folder", "folder", "Choose repository for this space", (_e, cx) => this.chooseFolder(cx), t)))
      .child(this.tool("git-refresh", "refresh", "Refresh Git and pull requests", (_e, cx) => this.refresh(cx, true), t))
      .child(this.tool("git-hide", "close", "Close panel", () => run("layout.hide", { id: "panel" }), t)));
    if (!this.repo) {
      return root.child(this.empty(this.error || (this.loading ? "Finding repository…" : "Open a repository in this space, or choose a folder."), t))
        .when(!this.loc?.on, e => e.child(div().px(12).child(this.button("git-choose-repo", "Choose repository", (_e, cx) => this.chooseFolder(cx), t))));
    }
    root.child(h_flex().px(12).py(8).gap(7).flex_none().items_center().text_size(11)
      .child(div().flex_1().min_w(0).truncate().text_color(t.accent).child(this.repoInfo?.branch || "Detached HEAD"))
      .when(this.repoInfo?.ahead > 0, e => e.child(this.badge(`↑${this.repoInfo.ahead}`, t, t.ansi2)))
      .when(this.repoInfo?.behind > 0, e => e.child(this.badge(`↓${this.repoInfo.behind}`, t, t.ansi3)))
      .when(this.loc?.pinned, e => e.child(this.button("git-follow", "Follow space", (_e, cx) => this.chooseFolder(cx, true), t))));
    root.child(h_flex().flex_none().px(8).pb(6).gap(3).children([
      ["history", "History"], ["branches", "Branches"], ["prs", "Pull requests"],
    ].map(([id, label]) => this.button(`git-tab-${id}`, label, (_e, cx) => this.switchTab(id, cx), t, this.view === id))));
    if (this.selected) root.child(this.details(t));
    else {
      root.child(div().flex_none().mx(12).mb(4).h(30).px(8).rounded(6).border_1().border_color(t.border)
        .child(Input.new(this.search).h_full().text_size(11.5).text_color(t.foreground)));
      root.child(this.view === "branches" ? this.branchList(t) : this.view === "prs" ? this.pullRequests(t) : this.history(t));
    }
    if (this.error || this.note) root.child(div().flex_none().px(12).py(6).text_size(10.5).text_color(t.ansi3).whitespace_normal().child(this.error || this.note));
    return root;
  }
}
