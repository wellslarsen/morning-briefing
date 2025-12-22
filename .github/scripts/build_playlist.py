import os, base64, requests, datetime, time, sys
from zoneinfo import ZoneInfo

CLIENT_ID = os.environ["SPOTIFY_CLIENT_ID"]
CLIENT_SECRET = os.environ["SPOTIFY_CLIENT_SECRET"]
REFRESH = os.environ["SPOTIFY_REFRESH_TOKEN"]
PLAYLIST_ID = os.environ["SPOTIFY_PLAYLIST_ID"]

# Use stable show IDs in the exact order you want.
SHOWS = [
    ("5ylaiuoDj7YOVSdyVJMDR7", "Cyber Security Headlines CISO Series"),
    ("4orGHEysjCAWvGEbHzeL9A", "SANS Internet Stormcenter's Daily"),
    ("44BcTpDWnfhcn02ADzs7iB", "WSJ Minute Breifing"),
    ("59176gU8vcFho6Sc1dm3Lu", "WSJ What’s News"),
    ("51MrXc7hJQBE2WJf2g4aWN", "WSJ Tech News Briefing"),
    ("1alpjXkCUjn3Y9fR5xl8fZ", "Reuters World News"),
    ("0pymDUChxmrkH41tOT33Uc", "The Headlines The New York Times"),
    ("1xGSLDgVYxLybmXpui6wwo", "CNN 5 Things"),
    ("6BRSvIBNQnB68GuoXJRCnQ", "NPR News Now"),
]

TZ = "America/Chicago"
SESSION = requests.Session()
SESSION.headers["Content-Type"] = "application/json"

def _basic_auth():
    return base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()

def get_access_token_from_refresh():
    data = {"grant_type": "refresh_token", "refresh_token": REFRESH}
    headers = {"Authorization": f"Basic {_basic_auth()}",
               "Content-Type": "application/x-www-form-urlencoded"}
    r = requests.post("https://accounts.spotify.com/api/token",
                      data=data, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]

def api_get(url, params=None, retries=3):
    for attempt in range(retries):
        r = SESSION.get(url, params=params, timeout=30)
        if r.status_code == 429 and attempt < retries - 1:
            time.sleep(int(r.headers.get("Retry-After", "1")))
            continue
        r.raise_for_status()
        return r

def latest_episode(show_id, only_today=True):
    url = f"https://api.spotify.com/v1/shows/{show_id}/episodes"
    r = api_get(url, params={"limit": 5, "market": "US"})
    items = r.json().get("items", [])
    if not items:
        return None
    today = datetime.datetime.now(ZoneInfo(TZ)).date()

    # Prefer an episode released today; otherwise take newest
    for ep in items:
        rel = ep.get("release_date")
        d = None
        try:
            if rel:
                d = datetime.date.fromisoformat(rel)
        except ValueError:
            pass
        if only_today and d == today:
            return ep
    return items[0]

def replace_playlist(uris):
    url = f"https://api.spotify.com/v1/playlists/{PLAYLIST_ID}/tracks"
    r = SESSION.put(url, json={"uris": uris}, timeout=30)
    r.raise_for_status()

def main():
    access = get_access_token_from_refresh()
    SESSION.headers["Authorization"] = f"Bearer {access}"

    # Who am I / who owns the target playlist?
    me = api_get("https://api.spotify.com/v1/me").json()
    pl = api_get(f"https://api.spotify.com/v1/playlists/{PLAYLIST_ID}").json()
    print(f"Acting as: {me.get('id')} ({me.get('display_name')})  |  "
          f"Playlist owner: {pl.get('owner', {}).get('id')}  |  "
          f"Playlist name: {pl.get('name')}")

    # Resolve shows (IDs already known); fetch names for accurate logging
    resolved = []
    for sid, display in SHOWS:
        info = api_get(f"https://api.spotify.com/v1/shows/{sid}", params={"market": "US"}).json()
        resolved.append({
            "id": sid,
            "name": info.get("name", display),
            "publisher": info.get("publisher", ""),
        })

    print("Resolved shows (in order):")
    for s in resolved:
        print(f"- {s['name']} ({s['publisher']}) -> {s['id']}")

    # Collect episode URIs (prefer today's releases)
    chosen = []
    for s in resolved:
        ep = latest_episode(s["id"], only_today=True)
        if ep:
            chosen.append(ep)

    # Fallback: if none published today, take newest so the playlist isn't empty
    if not chosen:
        for s in resolved:
            ep = latest_episode(s["id"], only_today=False)
            if ep:
                chosen.append(ep)

    if not chosen:
        print("No episodes found; aborting.", file=sys.stderr)
        sys.exit(1)

    print("\nLineup to write to playlist:")
    for i, ep in enumerate(chosen, 1):
        print(f"{i}. {ep['name']}  |  released: {ep.get('release_date')}  |  uri: {ep['uri']}")

    replace_playlist([ep["uri"] for ep in chosen])
    print(f"\nUpdated playlist {PLAYLIST_ID} with {len(chosen)} episode(s).")

if __name__ == "__main__":
    main()
