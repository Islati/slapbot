import pprint

import pytest

from slapbot.spotify import SpotifyWrapper


@pytest.fixture
def artist():
    yield SpotifyWrapper().get_artist("spotify:artist:1kxPoYW6CuTlFE3b3xwSxR")


def test_spotify_search_artist():
    search = SpotifyWrapper().search_for_artist("artist:Islati")
    assert search is not None, search
    assert len(search['artists']['items']) > 0, search['artists']['items']

    artist = search['artists']['items'][1]
    assert artist['name'] == 'Islati', artist['name']
    assert artist['uri'] == 'spotify:artist:1kxPoYW6CuTlFE3b3xwSxR', artist['uri']


def test_spotify_get_artist(artist):
    assert artist is not None, artist
    assert artist['name'] == 'Islati', artist['name']
    assert artist['uri'] == 'spotify:artist:1kxPoYW6CuTlFE3b3xwSxR', artist['uri']
    assert artist['id'] == "1kxPoYW6CuTlFE3b3xwSxR", artist
    assert artist['followers']['total'] > 0, artist['followers']['total']


def test_get_artist_albums(artist):
    albums = SpotifyWrapper().get_artist_albums(artist)
    assert albums is not None, albums
    assert len(albums) > 0, albums
    assert albums[0]['name'] is not None, albums[0]['name']


def test_get_discography(artist):
    discography = SpotifyWrapper().get_discography(artist)
    pprint.pprint(discography['albums'][0]['tracks'][0])
    assert discography is not None, discography
    assert len(discography['albums']) > 0, discography['albums']


# @pytest.mark.skip()
def test_get_artists_collaborated_with(artist):
    artists_collab_map = SpotifyWrapper().get_artists_collaborated_with(artist)
    assert artists_collab_map is not None, artists_collab_map
    assert len(artists_collab_map.keys()) > 0, artists_collab_map.keys()


def test_get_artists_singles(artist):
    singles = SpotifyWrapper().get_artist_singles(artist)
    assert singles is not None, singles
    assert len(singles) > 0, singles

def test_get_track_info():
    track = SpotifyWrapper().get_track("spotify:track:0AazjLIcU2Zu3YqQ1kLyql")
    assert track is not None
    assert track['name'] == 'Late Night', track['name']
