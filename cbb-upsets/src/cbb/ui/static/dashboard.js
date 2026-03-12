const input = document.querySelector("[data-team-search]");

if (input instanceof HTMLInputElement) {
  const targetId = input.dataset.teamSearchTarget;
  const results = targetId ? document.getElementById(targetId) : null;
  let timer = 0;

  input.addEventListener("input", () => {
    window.clearTimeout(timer);
    const query = input.value.trim();
    if (!results) {
      return;
    }
    if (!query) {
      results.innerHTML = "";
      return;
    }
    timer = window.setTimeout(async () => {
      const response = await fetch(`/api/teams/search?q=${encodeURIComponent(query)}`);
      if (!response.ok) {
        return;
      }
      const payload = await response.json();
      results.innerHTML = payload
        .map(
          (team) =>
            `<a class="search-result-link" href="${team.url}"><div><strong>${team.team_name}</strong>${team.match_hint ? `<p class="muted team-card-hint">${team.match_hint}</p>` : ""}</div><span class="team-card-key">${team.team_key}</span></a>`
        )
        .join("");
    }, 160);
  });
}

const pendingDashboard = document.querySelector("[data-refresh-dashboard]");

if (pendingDashboard instanceof HTMLElement) {
  window.setTimeout(() => {
    window.location.reload();
  }, 3500);
}
