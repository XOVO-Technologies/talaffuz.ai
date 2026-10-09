import { useEffect, useState } from "react";
import { REPO, REPO_URL } from "../config";
import { GithubIcon, StarIcon } from "./icons";

const CACHE_KEY = "urdu-dataset:stars";
const FRESH_MS = 10 * 60 * 1000;

function cached(): { n: number; fresh: boolean } | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const { repo, n, t } = JSON.parse(raw);
    if (repo !== REPO || typeof n !== "number") return null;
    return { n, fresh: Date.now() - t < FRESH_MS };
  } catch {
    return null;
  }
}

const short = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1).replace(/\.0$/, "")}k` : String(n));

/**
 * Link to the repository with a live star count. The last known count shows at once, and the browser asks GitHub for a
 * fresh one when that count is older than ten minutes. If GitHub cannot be reached the button shows without a number.
 */
export function GithubStars() {
  const [stars, setStars] = useState<number | null>(() => cached()?.n ?? null);

  useEffect(() => {
    if (cached()?.fresh) return;
    const ctrl = new AbortController();
    fetch(`https://api.github.com/repos/${REPO}`, { signal: ctrl.signal, headers: { Accept: "application/vnd.github+json" } })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => {
        if (typeof d.stargazers_count !== "number") return;
        setStars(d.stargazers_count);
        try {
          localStorage.setItem(CACHE_KEY, JSON.stringify({ repo: REPO, n: d.stargazers_count, t: Date.now() }));
        } catch {
          /* storage can be blocked */
        }
      })
      .catch(() => {
        /* offline, rate limited or repository not public yet: keep whatever count is already shown */
      });
    return () => ctrl.abort();
  }, []);

  return (
    <a className="button sm gh" href={REPO_URL} target="_blank" rel="noopener noreferrer" title="Star this project on GitHub">
      <GithubIcon />
      <span>Star</span>
      {stars !== null && (
        <span className="gh-count">
          <StarIcon />
          {short(stars)}
        </span>
      )}
    </a>
  );
}
