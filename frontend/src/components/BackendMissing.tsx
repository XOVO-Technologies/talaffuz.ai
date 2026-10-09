import { REPO, REPO_URL } from "../config";
import { GithubStars } from "./GithubStars";

/** Shown when the page loads but the local backend does not answer, for example on a published copy of this front end. */
export function BackendMissing({ detail }: { detail: string }) {
  const folder = REPO.split("/")[1];
  const setup = `git clone ${REPO_URL}.git\ncd ${folder}\n./setup.ps1\n./start.ps1`;

  return (
    <main className="offline">
      <div className="offline-head">
        <h2>The app is not running here</h2>
        <p>
          Talaffuz.ai processes recordings on your own computer. A web page cannot do that on its own, so a published copy
          of this page is only a guide. Clone the project and run it yourself.
        </p>
      </div>

      <div className="offline-grid">
        <section className="card">
          <h3>Already installed?</h3>
          <p>Start it from the project folder, then reload this page. It opens at http://127.0.0.1:8000.</p>
          <pre>./start.ps1</pre>
          <button className="primary" onClick={() => location.reload()}>
            Reload
          </button>
        </section>

        <section className="card">
          <h3>Not installed yet?</h3>
          <p>Clone the project and run the setup once. You need Git, uv and Node.js on Windows 10 or 11.</p>
          <pre>{setup}</pre>
          <a className="button" href={REPO_URL} target="_blank" rel="noopener noreferrer">
            Open the guide on GitHub
          </a>
        </section>
      </div>

      <div className="offline-star">
        <span>If this project saves you time, a star on GitHub helps other people find it.</span>
        <GithubStars />
      </div>

      <p className="hint">Technical detail: {detail}</p>
    </main>
  );
}
