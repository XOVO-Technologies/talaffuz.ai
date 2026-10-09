(() => {
  const stage = document.getElementById("voice-stage");
  if (!stage) return;
  document.documentElement.classList.add("js");

  const voice = stage.querySelector(".voice");
  const page = stage.querySelector(".page");
  const sentences = [...stage.querySelectorAll(".lines-src li")].map((li) => li.textContent.trim());
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");

  const BARS = 41;
  const ROWS = 7;
  const SPEAK = 4800;
  const FLATTEN = 900;
  const WRITE = 5200;
  const RESTORE = 800;
  const LOOP = SPEAK + FLATTEN + WRITE + RESTORE;
  const FLOOR = 0.02;

  const bars = [];
  for (let i = 0; i < BARS; i++) {
    const bar = document.createElement("span");
    bar.className = "bar";
    voice.append(bar);
    bars.push(bar);
  }

  for (let r = 0; r < ROWS; r++) {
    const k = r - (ROWS - 1) / 2;
    const row = document.createElement("div");
    row.className = "line-row";
    row.style.setProperty("--k", k);
    row.style.setProperty("--dist", Math.abs(k));
    row.style.setProperty("--t", `${Math.round(sentences.length * (3.6 + ((r * 7) % 5) * 0.6))}s`);
    const track = document.createElement("div");
    track.className = "track";
    for (let copy = 0; copy < 2; copy++) {
      for (let s = 0; s < sentences.length; s++) {
        const item = document.createElement("span");
        item.lang = "ur";
        item.dir = "rtl";
        item.textContent = sentences[(s + r * 2) % sentences.length];
        track.append(item);
      }
    }
    row.append(track);
    page.append(row);
  }

  const ease = (x) => x * x * (3 - 2 * x);

  function amplitude(t) {
    if (t < SPEAK) return 1;
    if (t < SPEAK + FLATTEN) return 1 - ease((t - SPEAK) / FLATTEN);
    if (t < SPEAK + FLATTEN + WRITE) return 0;
    return ease((t - SPEAK - FLATTEN - WRITE) / RESTORE);
  }

  let clock = 0;
  let last = 0;
  let raf = 0;
  let inView = true;

  function frame(now) {
    clock += last ? Math.min(now - last, 100) : 0;
    last = now;
    const t = clock % LOOP;
    const s = clock / 1000;
    const phase = t >= SPEAK && t < SPEAK + FLATTEN + WRITE ? "write" : "speak";
    if (stage.dataset.phase !== phase) stage.dataset.phase = phase;

    const a = amplitude(t);
    const word = Math.abs(Math.sin(s * 5.1) * Math.sin(s * 1.3 + 0.6));
    const gate = 0.18 + 0.82 * Math.min(1, word * 1.7);
    for (let i = 0; i < BARS; i++) {
      const shape = 0.3 + 0.7 * Math.sin((Math.PI * (i + 0.5)) / BARS);
      const wobble = Math.abs(Math.sin(s * 9 + i * 0.85) * Math.sin(s * 4.3 - i * 0.41));
      const h = FLOOR + (1 - FLOOR) * Math.min(1, a * shape * gate * (0.3 + 0.7 * wobble) * 1.3);
      bars[i].style.transform = `scaleY(${h.toFixed(3)})`;
    }
    raf = requestAnimationFrame(frame);
  }

  function play() {
    if (raf || reduce.matches || !inView || document.hidden) return;
    last = 0;
    stage.classList.remove("is-paused");
    raf = requestAnimationFrame(frame);
  }

  function pause() {
    cancelAnimationFrame(raf);
    raf = 0;
    stage.classList.add("is-paused");
  }

  function settle() {
    if (reduce.matches) {
      pause();
      stage.classList.add("is-static");
      stage.dataset.phase = "write";
    } else {
      stage.classList.remove("is-static");
      play();
    }
  }

  new IntersectionObserver(
    ([entry]) => {
      inView = entry.isIntersecting;
      if (inView) play();
      else pause();
    },
    { threshold: 0.05 },
  ).observe(stage);
  document.addEventListener("visibilitychange", () => (document.hidden ? pause() : play()));
  reduce.addEventListener("change", settle);
  settle();
})();
