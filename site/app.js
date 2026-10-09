(() => {
  const cfg = window.SITE_CONFIG;
  if (!cfg) {
    console.warn("site/config.js did not load, so the links and star count are disabled.");
    return;
  }
  const $ = (selector, root = document) => root.querySelector(selector);

  // On GitHub Pages (owner.github.io/repo/) the owner and repository come from the address, so a fork's page
  // links to that fork without any edits. Everywhere else, such as Vercel, site/config.js is used.
  let owner = cfg.owner;
  let name = cfg.repo;
  if (location.hostname.endsWith(".github.io")) {
    const first = location.pathname.split("/").filter(Boolean)[0];
    owner = location.hostname.split(".")[0];
    if (first && !/\.html?$/i.test(first)) name = first;
  }
  const repo = `${owner}/${name}`;
  const repoUrl = `https://github.com/${repo}`;
  const links = {
    repo: repoUrl,
    issues: `${repoUrl}/issues`,
    guide: `${repoUrl}#using-the-app`,
    zip: `${repoUrl}/archive/refs/heads/${cfg.branch}.zip`,
    colab: `https://colab.research.google.com/github/${repo}/blob/${cfg.branch}/${cfg.notebook}`,
  };
  document.querySelectorAll("[data-link]").forEach((a) => {
    a.href = links[a.dataset.link];
  });

  // Fill {{placeholders}} in command blocks so they always match the config.
  const vars = { cloneUrl: `${repoUrl}.git`, repoName: name };
  document.querySelectorAll("[data-fill]").forEach((el) => {
    el.textContent = el.textContent.replace(/\{\{(\w+)\}\}/g, (_, key) => vars[key] ?? "");
  });

  const prompt = $("#claude-prompt");
  const openClaude = $("#open-claude");
  if (prompt && openClaude) openClaude.href = `https://claude.ai/new?q=${encodeURIComponent(prompt.textContent.trim())}`;

  // Copy buttons
  document.querySelectorAll("[data-copy]").forEach((btn) => {
    const label = btn.textContent;
    btn.addEventListener("click", async () => {
      const target = $(btn.dataset.copy);
      try {
        await navigator.clipboard.writeText(target?.textContent.trim() ?? "");
        btn.textContent = "Copied";
      } catch {
        btn.textContent = "Press Ctrl+C";
        const range = document.createRange();
        range.selectNodeContents(target);
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
      }
      setTimeout(() => (btn.textContent = label), 1800);
    });
  });

  // ---- "Where do you want to run it?" dropdown ----
  const ddBtn = $("#run-dd-btn");
  const ddList = $("#run-dd-list");
  const options = [...ddList.querySelectorAll('[role="option"]')];
  const panels = { colab: $("#panel-colab"), claude: $("#panel-claude"), codex: $("#panel-codex"), windows: $("#panel-windows") };
  let current = "colab";
  let active = 0;

  function paintButton() {
    const o = options.find((opt) => opt.dataset.run === current);
    $(".dd-icon", ddBtn).innerHTML = $(".dd-icon", o).innerHTML;
    $(".dd-title", ddBtn).textContent = $("strong", o).textContent;
    $(".dd-sub", ddBtn).textContent = $("small", o).textContent;
  }

  function choose(name) {
    if (!panels[name]) name = "colab";
    current = name;
    options.forEach((o) => o.setAttribute("aria-selected", String(o.dataset.run === name)));
    Object.entries(panels).forEach(([key, el]) => (el.hidden = key !== name));
    paintButton();
  }

  function setActive(index) {
    active = (index + options.length) % options.length;
    options.forEach((o, i) => o.classList.toggle("active", i === active));
    ddList.setAttribute("aria-activedescendant", options[active].id);
  }
  function openList() {
    ddList.hidden = false;
    ddBtn.setAttribute("aria-expanded", "true");
    setActive(options.findIndex((o) => o.dataset.run === current));
    ddList.focus();
  }
  function closeList(returnFocus = true) {
    if (ddList.hidden) return;
    ddList.hidden = true;
    ddBtn.setAttribute("aria-expanded", "false");
    if (returnFocus) ddBtn.focus();
  }

  ddBtn.addEventListener("click", () => (ddList.hidden ? openList() : closeList()));
  ddBtn.addEventListener("keydown", (e) => {
    if (["ArrowDown", "ArrowUp"].includes(e.key)) {
      e.preventDefault();
      openList();
    }
  });
  ddList.addEventListener("keydown", (e) => {
    const moves = { ArrowDown: () => setActive(active + 1), ArrowUp: () => setActive(active - 1), Home: () => setActive(0), End: () => setActive(options.length - 1) };
    if (moves[e.key]) {
      e.preventDefault();
      moves[e.key]();
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      choose(options[active].dataset.run);
      closeList();
    } else if (e.key === "Escape") {
      e.preventDefault();
      closeList();
    } else if (e.key === "Tab") {
      closeList(false);
    }
  });
  options.forEach((o, i) => {
    o.addEventListener("click", () => {
      choose(o.dataset.run);
      closeList();
    });
    o.addEventListener("mousemove", () => setActive(i));
  });

  // ---- Header "Get started" menu: the same three choices ----
  const menuBtn = $("#start-menu-btn");
  const menuList = $("#start-menu-list");
  options.forEach((o) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "menu-item";
    item.setAttribute("role", "menuitem");
    item.dataset.run = o.dataset.run;
    const icon = document.createElement("span");
    icon.className = "dd-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.innerHTML = $(".dd-icon", o).innerHTML;
    const text = document.createElement("span");
    text.className = "dd-text";
    const title = document.createElement("strong");
    title.textContent = $("strong", o).textContent;
    const sub = document.createElement("small");
    sub.textContent = o.dataset.short || "";
    text.append(title, sub);
    item.append(icon, text);
    menuList.append(item);
  });
  const menuItems = [...menuList.children];

  function openMenu() {
    menuList.hidden = false;
    menuBtn.setAttribute("aria-expanded", "true");
    menuItems[0].focus();
  }
  function closeMenu(returnFocus = false) {
    if (menuList.hidden) return;
    menuList.hidden = true;
    menuBtn.setAttribute("aria-expanded", "false");
    if (returnFocus) menuBtn.focus();
  }
  menuBtn.addEventListener("click", () => (menuList.hidden ? openMenu() : closeMenu()));
  menuBtn.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      openMenu();
    }
  });
  menuList.addEventListener("keydown", (e) => {
    const i = menuItems.indexOf(document.activeElement);
    if (e.key === "ArrowDown") {
      e.preventDefault();
      menuItems[(i + 1) % menuItems.length].focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      menuItems[(i - 1 + menuItems.length) % menuItems.length].focus();
    } else if (e.key === "Escape") {
      e.preventDefault();
      closeMenu(true);
    } else if (e.key === "Tab") {
      closeMenu();
    }
  });
  menuItems.forEach((item) =>
    item.addEventListener("click", () => {
      choose(item.dataset.run);
      closeMenu();
      $("#run").scrollIntoView({ behavior: "smooth" });
    }),
  );

  document.addEventListener("click", (e) => {
    if (!e.target.closest("#start-menu")) closeMenu();
    if (!e.target.closest("#run-dd")) closeList(false);
  });

  // Deep links: #run=colab, #run=claude, #run=windows (or ?run=...). Colab is the default.
  function fromLocation() {
    const wanted = (location.hash.match(/^#run=(\w+)/) || location.search.match(/[?&]run=(\w+)/) || [])[1];
    choose(wanted && panels[wanted] ? wanted : "colab");
    if (wanted) {
      $("#run").scrollIntoView();
      history.replaceState(null, "", location.pathname);
    }
  }
  window.addEventListener("hashchange", fromLocation);
  fromLocation();

  document.addEventListener("click", (e) => {
    const link = e.target.closest('a[href^="#"]');
    const id = link && link.getAttribute("href").slice(1);
    if (!id) return;
    e.preventDefault();
    if (id === "top") window.scrollTo({ top: 0, behavior: "smooth" });
    else document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
  });

  // ---- Live GitHub star count. If the request fails the star button keeps the last count, or shows none. ----
  const KEY = "udc:stars";
  const short = (n) => (n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1).replace(/\.0$/, "")}k` : String(n));
  const show = (n) =>
    document.querySelectorAll("[data-stars]").forEach((el) => {
      el.textContent = short(n);
      el.hidden = false;
    });
  // Show the last known count at once, and ask GitHub again only when it is older than ten minutes.
  try {
    const cached = JSON.parse(localStorage.getItem(KEY) || "null");
    if (cached && cached.repo === repo && typeof cached.n === "number") {
      show(cached.n);
      if (Date.now() - cached.t < 600000) return;
    }
  } catch {
    /* storage can be blocked */
  }
  fetch(`https://api.github.com/repos/${repo}`, { headers: { Accept: "application/vnd.github+json" } })
    .then((r) => (r.ok ? r.json() : Promise.reject()))
    .then((d) => {
      if (typeof d.stargazers_count !== "number") return;
      show(d.stargazers_count);
      try {
        localStorage.setItem(KEY, JSON.stringify({ repo, n: d.stargazers_count, t: Date.now() }));
      } catch {
        /* ignore */
      }
    })
    .catch(() => {});
})();

(() => {
  const button = document.getElementById("to-top");
  if (!button) return;
  button.hidden = false;
  const update = () => button.classList.toggle("show", window.scrollY > 500);
  window.addEventListener("scroll", update, { passive: true });
  button.addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));
  update();
})();

(() => {
  const items = [...document.querySelectorAll(".faq details")];
  items.forEach((item) =>
    item.addEventListener("toggle", () => {
      if (!item.open) return;
      items.forEach((other) => {
        if (other !== item) other.open = false;
      });
    }),
  );
})();
