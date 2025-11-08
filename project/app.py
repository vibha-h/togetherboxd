from flask import Flask, request, render_template, Response, stream_with_context
from bs4 import BeautifulSoup
import time
import json
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

# Simple in-memory cache that lives for the lifetime of the application process.
# Structure: USER_CACHE[username] = {'films': [...], 'ts': <unix timestamp>}
USER_CACHE = {}
# Set to a number (seconds) to enable automatic expiry, or None to keep cached until process restart
CACHE_TTL_SECONDS = None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/compare-stream')
def compare_stream():
    usernames = request.args.getlist('user')

    def scrape_user(username, max_pages=200):
        ua = {'User-Agent': 'Mozilla/5.0'}
        films = []
        try:
            for page in range(1, max_pages + 1):
                url = f'https://letterboxd.com/{username}/watchlist/page/{page}/'
                r = requests.get(url, headers=ua, timeout=10)
                if r.status_code == 404:
                    return {'error': f'user {username} was not found'}
                soup = BeautifulSoup(r.text, 'html.parser')
                items = soup.select('div.react-component[data-component-class="LazyPoster"]')
                if not items:
                    break
                for d in items:
                    title = d.get('data-item-name')
                    href = d.get('data-item-link')
                    img = d.select_one('img')
                    poster = None
                    if img:
                        poster = img.get('data-src') or img.get('src')
                        if poster and poster.startswith('//'):
                            poster = 'https:' + poster
                        if poster and '?v=' in poster:
                            poster = poster.split('?v=')[0]
                    if href and href.startswith('/'):
                        href = 'https://letterboxd.com' + href
                    if title and href:
                        films.append({'title': title.strip(), 'link': href, 'poster': poster})
                # small polite delay to avoid hammering the site
                time.sleep(0.2)
        except requests.RequestException as e:
            return {'error': f'network error for {username}: {str(e)}'}

        # If no films found, return a specific error
        if not films:
            return {'error': f"user {username}'s watchlist is empty"}

        # store in cache
        try:
            USER_CACHE[username] = {'films': films, 'ts': time.time()}
        except Exception:
            pass

        return {'films': films}

    def generate():
        # stream validation as SSE messages so frontend receives them
        if len(usernames) < 2:
            yield "data: ERROR: Provide at least two usernames\n\n"
            return
        if len(set(usernames)) < 2:
            yield "data: Please enter two distinct usernames\n\n"
            return

        user_watchlists = {}

        # Use cached results when available to avoid unnecessary scraping
        to_scrape = []
        for u in usernames:
            cached = USER_CACHE.get(u)
            if cached:
                if CACHE_TTL_SECONDS is None or (time.time() - cached['ts'] <= CACHE_TTL_SECONDS):
                    user_watchlists[u] = {film['title']: film for film in cached['films']}
                    # yield f"data: Using cached watchlist for {u}. {len(cached['films'])} films.\n\n"
                    continue
            to_scrape.append(u)

        # Run scrapes in parallel for users not in cache
        if to_scrape:
            with ThreadPoolExecutor(max_workers=min(4, len(to_scrape))) as ex:
                futures = {ex.submit(scrape_user, u): u for u in to_scrape}

                # # inform frontend that tasks started
                # for u in to_scrape:
                #     yield f"data: Starting scrape for {u}...\n\n"

                for fut in as_completed(futures):
                    username = futures[fut]
                    try:
                        result = fut.result()
                    except Exception as e:
                        yield f"data: ERROR scraping {username}: {str(e)}\n\n"
                        continue

                    if 'error' in result:
                        yield f"data: ERROR: {result['error']}.\n\n"
                        continue

                    films = result.get('films', [])
                    # yield f"data: {username} done scraping. {len(films)} films collected.\n\n"
                    user_watchlists[username] = {film['title']: film for film in films}

        # compute intersection
        if len(user_watchlists) >= 2:
            common_titles = set.intersection(*(set(d.keys()) for d in user_watchlists.values()))
            # build common films list from the first user in the dict to preserve consistent film objects
            first_user = list(user_watchlists.keys())[0]
            common_films = [user_watchlists[first_user][title] for title in sorted(common_titles)]
            yield f"data: COMPARISON_RESULT:{json.dumps(common_films)}\n\n"
        else:
            yield f"data: ERROR: Not enough valid users to compare.\n\n"

    return Response(stream_with_context(generate()), content_type='text/event-stream')

if __name__ == '__main__':
    app.run(debug=True)
