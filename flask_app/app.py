from flask import Flask, request, render_template
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

def get_watchlist(username):
    url = f"https://letterboxd.com/{username}/watchlist/"
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')
    watchlist = [movie['data-film-name'] for movie in soup.find_all('li', class_='poster-container')]
    return watchlist

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/compare', methods=['POST'])
def compare():
    user1 = request.form['username1']
    user2 = request.form['username2']
    
    watchlist1 = get_watchlist(user1)
    watchlist2 = get_watchlist(user2)
    
    common_movies = set(watchlist1).intersection(set(watchlist2))
    
    return render_template('result.html', common_movies=common_movies)

if __name__ == '__main__':
    app.run(debug=True)
