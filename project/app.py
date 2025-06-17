from flask import Flask, request, render_template, Response, stream_with_context
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time
import json

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/compare-stream')
def compare_stream():
    usernames = request.args.getlist('user')
    if len(usernames) < 2:
        return Response("data: ERROR: Provide at least two usernames.\n\n", content_type='text/event-stream')

    def generate():
        user_watchlists = {}

        for username in usernames:
            options = Options()
            options.add_argument('--headless')
            options.add_argument('--disable-gpu')
            options.add_argument("--window-size=1920,1080")

            driver = webdriver.Chrome(options=options)
            films = []
            page = 1
            yield f"data: Starting scrape for {username}...\n\n"

            try:
                while True:
                    url = f'https://letterboxd.com/{username}/watchlist/page/{page}/'
                    driver.get(url)
                    time.sleep(2)
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)

                    soup = BeautifulSoup(driver.page_source, 'html.parser')
                    film_items = soup.select('ul.poster-list li')

                    if not film_items:
                        yield f"data: {username} done scraping. {len(films)} films collected.\n\n"
                        break

                    for li in film_items:
                        a_tag = li.find('a', class_='frame')
                        if not a_tag:
                            continue

                        title = a_tag.get('data-original-title')
                        href = a_tag.get('href')
                        poster = None

                        img_tag = li.find('img')
                        if img_tag:
                            poster = img_tag.get('data-src') or img_tag.get('src')
                            if poster and poster.startswith('//'):
                                poster = 'https:' + poster
                            if '?v=' in poster:
                                poster = poster.split('?v=')[0]

                        if title and href and poster:
                            films.append({
                                'title': title.strip(),
                                'link': f"https://letterboxd.com{href}",
                                'poster': poster
                            })

                    yield f"data: {username} Page {page} ✅ \n\n"
                    page += 1

                user_watchlists[username] = {film['title']: film for film in films}

            finally:
                driver.quit()

        if len(user_watchlists) >= 2:
            common_titles = set.intersection(*(set(d.keys()) for d in user_watchlists.values()))
            common_films = [user_watchlists[usernames[0]][title] for title in sorted(common_titles)]
            yield f"data: COMPARISON_RESULT:{json.dumps(common_films)}\n\n"
        else:
            yield f"data: ERROR: Not enough data to compare.\n\n"

    return Response(stream_with_context(generate()), content_type='text/event-stream')

if __name__ == '__main__':
    app.run(debug=True)
